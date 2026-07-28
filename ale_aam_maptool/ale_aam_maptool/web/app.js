const $ = id => document.getElementById(id);

const state = {
  map: null,
  scenario: null,
  scenarioBounds: null,
  vectorRenderer: null,
  basemaps: [],
  basemap: 'offline',
  basemapLayer: null,
  basemapFailures: 0,
  layerControls: new Map(),
  demWasVisible: true,
  mode: 'inspect',
  waypoints: [],
  selectedWaypoint: null,
  waypointMarkers: [],
  routeLayer: null,
  locationMarker: null,
  localLayers: [],
};

async function request(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === 'object' && data ? data.detail : data;
    throw new Error(detail || response.statusText);
  }
  return data;
}

function setStatus(message, isError = false) {
  $('status').textContent = message;
  $('status').style.color = isError ? '#fca5a5' : '';
}

function toLatLng(coordinate) {
  return [Number(coordinate[1]), Number(coordinate[0])];
}

function toCoordinate(latlng) {
  return [Number(latlng.lng), Number(latlng.lat)];
}

function scenarioLeafletBounds() {
  const extent = state.scenario.extent;
  return L.latLngBounds([extent.south, extent.west], [extent.north, extent.east]);
}

function resetView() {
  if (state.map && state.scenarioBounds) {
    state.map.fitBounds(state.scenarioBounds, {padding: [24, 24], animate: false});
  }
}

function setMode(mode) {
  state.mode = mode;
  $('map').dataset.mode = mode;
  for (const name of ['inspect', 'draw', 'pan']) {
    $(`mode-${name}`).setAttribute('aria-pressed', String(name === mode));
  }
  const messages = {
    inspect: '查看模式：点击地图读取该位置的环境信息。',
    draw: '画航点模式：点击地图新增中间航点，也可拖动已有航点。',
    pan: '平移模式：拖动或缩放地图，不新增航点。',
  };
  if (state.scenario) setStatus(messages[mode]);
}

function addLayerToggle(layer, checked, onChange) {
  const row = document.createElement('label');
  row.className = `layer-item${layer.available === false ? ' unavailable' : ''}`;
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = checked;
  input.disabled = layer.available === false;
  input.addEventListener('change', () => onChange(input.checked));
  const name = document.createElement('span');
  name.textContent = layer.name;
  const kind = document.createElement('small');
  kind.textContent = layer.kind === 'raster' ? '栅格' : '矢量';
  row.append(input, name, kind);
  $('layers').appendChild(row);
  return {row, input};
}

function layerStyle(layerId) {
  if (layerId === 'buildings') {
    return {color: '#f59e0b', weight: 0.8, opacity: 0.9, fillColor: '#f59e0b', fillOpacity: 0.28,
      renderer: state.vectorRenderer, bubblingMouseEvents: false};
  }
  if (layerId === 'airspace') {
    return {color: '#ef4444', weight: 2, opacity: 0.95, dashArray: '7 5', fillColor: '#ef4444', fillOpacity: 0.2,
      renderer: state.vectorRenderer, bubblingMouseEvents: false};
  }
  return {color: '#fbbf24', weight: 2, opacity: 0.95, fillColor: '#ef4444', fillOpacity: 0.18,
    renderer: state.vectorRenderer, bubblingMouseEvents: false};
}

function featureTitle(layerId) {
  return {buildings: '3D 建筑', airspace: '空域管制区', emergency_sites: '应急起降点'}[layerId] || layerId;
}

function showFeatureProperties(feature, title) {
  const box = $('environment');
  box.textContent = '';
  const heading = document.createElement('strong');
  heading.textContent = title;
  const pre = document.createElement('pre');
  pre.textContent = JSON.stringify(feature.properties || {}, null, 2);
  box.append(heading, pre);
}

function geoJSONLayer(data, layerId, title) {
  return L.geoJSON(data, {
    renderer: state.vectorRenderer,
    style: () => layerStyle(layerId),
    pointToLayer: (_feature, latlng) => L.circleMarker(latlng, {
      renderer: state.vectorRenderer,
      radius: layerId === 'emergency_sites' ? 7 : 6,
      color: '#111827',
      weight: 1.5,
      fillColor: layerId === 'emergency_sites' ? '#facc15' : '#fb7185',
      fillOpacity: 0.95,
      bubblingMouseEvents: false,
    }),
    onEachFeature: (feature, leafletLayer) => {
      leafletLayer.on('click', event => {
        if (event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent);
        showFeatureProperties(feature, title);
      });
      const properties = JSON.stringify(feature.properties || {}, null, 2);
      leafletLayer.bindPopup(`<strong>${escapeHtml(title)}</strong><pre class="feature-popup">${escapeHtml(properties)}</pre>`, {
        maxWidth: 340,
      });
    },
  });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

async function ensureScenarioLayer(layerId) {
  const control = state.layerControls.get(layerId);
  if (!control || control.mapLayer || control.loadingPromise) return control?.loadingPromise;
  const definition = control.definition;
  if (definition.kind === 'raster') {
    control.mapLayer = L.imageOverlay(definition.preview_url, state.scenarioBounds, {
      opacity: layerId === 'dem' ? 0.82 : 0.58,
      interactive: false,
      pane: 'overlayPane',
    });
    return control.mapLayer;
  }
  control.row.classList.add('loading');
  control.loadingPromise = request(`/v1/layers/${encodeURIComponent(layerId)}`)
    .then(data => {
      control.mapLayer = geoJSONLayer(data, layerId, featureTitle(layerId));
      if (control.input.checked) control.mapLayer.addTo(state.map);
      return control.mapLayer;
    })
    .catch(error => {
      control.input.checked = false;
      setStatus(`${definition.name}加载失败：${error.message}`, true);
      return null;
    })
    .finally(() => {
      control.row.classList.remove('loading');
      control.loadingPromise = null;
    });
  return control.loadingPromise;
}

async function toggleScenarioLayer(layerId, visible) {
  const control = state.layerControls.get(layerId);
  if (!control) return;
  if (visible && !control.mapLayer) await ensureScenarioLayer(layerId);
  if (!control.mapLayer) return;
  if (visible) control.mapLayer.addTo(state.map);
  else control.mapLayer.removeFrom(state.map);
}

function renderScenarioLayers() {
  $('layers').textContent = '';
  state.layerControls.clear();
  const initiallyVisible = new Set(['dem', 'buildings', 'airspace', 'emergency_sites']);
  for (const definition of state.scenario.layers) {
    const visible = Boolean(definition.available && initiallyVisible.has(definition.id));
    const toggle = addLayerToggle(definition, visible, checked => toggleScenarioLayer(definition.id, checked));
    const control = {...toggle, definition, mapLayer: null, loadingPromise: null};
    state.layerControls.set(definition.id, control);
    if (visible) toggleScenarioLayer(definition.id, true);
  }
}

function updateDemForBasemap() {
  const control = state.layerControls.get('dem');
  if (!control) return;
  const tiledBasemap = state.basemap !== 'offline';
  if (tiledBasemap) {
    if (!control.input.disabled) state.demWasVisible = control.input.checked;
    control.input.checked = false;
    control.input.disabled = true;
    if (control.mapLayer) control.mapLayer.removeFrom(state.map);
  } else {
    control.input.disabled = false;
    control.input.checked = state.demWasVisible;
    if (state.demWasVisible) toggleScenarioLayer('dem', true);
  }
}

function setBasemap(providerId, quiet = false) {
  const definition = state.basemaps.find(item => item.id === providerId && item.available)
    || state.basemaps.find(item => item.id === 'offline');
  if (!definition || !state.map) return;
  if (state.basemapLayer) {
    state.basemapLayer.removeFrom(state.map);
    state.basemapLayer = null;
  }
  state.basemap = definition.id;
  state.basemapFailures = 0;
  $('map').dataset.basemap = definition.id === 'offline' ? 'scenario' : 'tiled';
  $('basemap').value = definition.id;
  $('basemap-attribution').textContent = definition.attribution;
  if (definition.id !== 'offline') {
    state.basemapLayer = L.tileLayer(
      `/v1/basemaps/${encodeURIComponent(definition.id)}/{z}/{x}/{y}.png`,
      {
        pane: 'tilePane',
        minNativeZoom: Number(definition.min_zoom || 0),
        maxNativeZoom: Number(definition.max_zoom),
        minZoom: 0,
        maxZoom: 20,
        keepBuffer: 3,
        updateWhenIdle: true,
        attribution: definition.attribution,
      },
    );
    state.basemapLayer.on('tileerror', () => {
      state.basemapFailures += 1;
      if (state.basemapFailures === 6 && definition.online) {
        setBasemap('offline', true);
        setStatus('在线底图暂时不可用，已回退到离线场景图层。', true);
      }
    });
    state.basemapLayer.addTo(state.map);
    state.basemapLayer.bringToBack();
  }
  updateDemForBasemap();
  if (!quiet) setStatus(`已切换到底图：${definition.name}。`);
}

async function loadBasemaps() {
  const select = $('basemap');
  try {
    const data = await request('/v1/basemaps');
    state.basemaps = data.providers;
    select.textContent = '';
    for (const provider of data.providers) {
      const option = document.createElement('option');
      option.value = provider.id;
      const mode = provider.online ? '在线' : (provider.id === 'offline' ? '场景图层' : '离线包');
      option.textContent = provider.available ? `${provider.name}（${mode}）` : `${provider.name}（未配置）`;
      option.disabled = !provider.available;
      select.appendChild(option);
    }
    select.disabled = data.providers.filter(provider => provider.available).length < 2;
    setBasemap(data.default, true);
  } catch (_) {
    state.basemaps = [{id: 'offline', name: '离线场景图层', online: false, available: true,
      attribution: 'ALE-AAM 场景数据', min_zoom: 0, max_zoom: 20}];
    select.disabled = true;
    setBasemap('offline', true);
  }
}

function waypointDefaults(coordinate) {
  const envelope = state.scenario.constraints.altitude_m_agl;
  return {
    coordinate: [...coordinate],
    altitude: Math.round((Number(envelope.min) + Number(envelope.max)) / 2),
    speed: Number(state.scenario.aircraft.cruise_speed_ms),
    terrain: null,
  };
}

async function sampleWaypoint(index) {
  const waypoint = state.waypoints[index];
  if (!waypoint) return;
  try {
    const data = await request(`/v1/environment?lon=${waypoint.coordinate[0]}&lat=${waypoint.coordinate[1]}`);
    waypoint.terrain = data.rasters.terrain_elevation_m_msl;
  } catch (_) {
    waypoint.terrain = null;
  }
}

function resetRoute() {
  const mission = state.scenario.mission;
  state.waypoints = [waypointDefaults(mission.start), waypointDefaults(mission.goal)];
  state.selectedWaypoint = 0;
  renderDraft();
  Promise.all([sampleWaypoint(0), sampleWaypoint(1)]).then(renderWaypointList);
  setStatus('已载入任务起点和终点；切换到“画航点”后点击地图添加中间航点。');
}

function renderWaypointList() {
  const container = $('waypoints');
  container.textContent = '';
  state.waypoints.forEach((waypoint, index) => {
    const item = document.createElement('div');
    item.className = 'waypoint-item';
    const head = document.createElement('div');
    head.className = 'waypoint-head';
    const title = document.createElement('strong');
    title.textContent = `航点 ${index + 1}`;
    const coordinate = document.createElement('span');
    coordinate.className = 'waypoint-coordinate';
    coordinate.textContent = `${waypoint.coordinate[0].toFixed(6)}, ${waypoint.coordinate[1].toFixed(6)}`;
    head.append(title, coordinate);
    if (state.waypoints.length > 2) {
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '删除';
      remove.addEventListener('click', () => {
        state.waypoints.splice(index, 1);
        state.selectedWaypoint = null;
        renderDraft();
      });
      head.appendChild(remove);
    }
    const fields = document.createElement('div');
    fields.className = 'waypoint-fields';
    const altitudeLabel = document.createElement('label');
    altitudeLabel.textContent = '高度 m AGL';
    const altitude = document.createElement('input');
    altitude.type = 'number';
    altitude.min = state.scenario.constraints.altitude_m_agl.min;
    altitude.max = state.scenario.constraints.altitude_m_agl.max;
    altitude.step = '1';
    altitude.value = waypoint.altitude;
    altitude.addEventListener('change', () => { waypoint.altitude = Number(altitude.value); });
    altitudeLabel.appendChild(altitude);
    const speedLabel = document.createElement('label');
    speedLabel.textContent = '速度 m/s';
    const speed = document.createElement('input');
    speed.type = 'number';
    speed.min = state.scenario.constraints.speed_ms.min;
    speed.max = state.scenario.constraints.speed_ms.max;
    speed.step = '0.5';
    speed.value = waypoint.speed;
    speed.addEventListener('change', () => { waypoint.speed = Number(speed.value); });
    speedLabel.appendChild(speed);
    fields.append(altitudeLabel, speedLabel);
    item.append(head, fields);
    item.addEventListener('click', event => {
      if (!['INPUT', 'BUTTON'].includes(event.target.tagName)) {
        state.selectedWaypoint = index;
        renderDraft();
      }
    });
    container.appendChild(item);
  });
  $('export').disabled = state.waypoints.length < 2;
}

function waypointIcon(index) {
  const selected = state.selectedWaypoint === index ? ' selected' : '';
  return L.divIcon({
    className: `waypoint-icon${selected}`,
    html: `<span class="waypoint-dot">${index + 1}</span>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

function updateRouteLine() {
  const latlngs = state.waypoints.map(item => toLatLng(item.coordinate));
  if (!state.routeLayer) {
    state.routeLayer = L.polyline(latlngs, {color: '#22d3ee', weight: 4, opacity: 0.95,
      renderer: state.vectorRenderer, bubblingMouseEvents: false}).addTo(state.map);
  } else {
    state.routeLayer.setLatLngs(latlngs);
  }
}

function renderDraft() {
  updateRouteLine();
  for (const marker of state.waypointMarkers) marker.removeFrom(state.map);
  state.waypointMarkers = state.waypoints.map((waypoint, index) => {
    const marker = L.marker(toLatLng(waypoint.coordinate), {
      icon: waypointIcon(index),
      draggable: true,
      keyboard: true,
      bubblingMouseEvents: false,
      title: `航点 ${index + 1}`,
      zIndexOffset: 500,
    }).addTo(state.map);
    marker.on('click', () => {
      state.selectedWaypoint = index;
      renderDraft();
    });
    marker.on('drag', event => {
      waypoint.coordinate = toCoordinate(event.target.getLatLng());
      updateRouteLine();
    });
    marker.on('dragend', async event => {
      waypoint.coordinate = toCoordinate(event.target.getLatLng());
      await sampleWaypoint(index);
      renderDraft();
    });
    return marker;
  });
  renderWaypointList();
}

function addWaypoint(coordinate) {
  const index = Math.max(1, state.waypoints.length - 1);
  state.waypoints.splice(index, 0, waypointDefaults(coordinate));
  state.selectedWaypoint = index;
  renderDraft();
  sampleWaypoint(index).then(renderWaypointList);
}

function showEnvironment(data, title = '场景环境') {
  const box = $('environment');
  box.textContent = '';
  const heading = document.createElement('strong');
  heading.textContent = `${title} · ${data.coordinate[0].toFixed(6)}, ${data.coordinate[1].toFixed(6)}`;
  const raster = document.createElement('div');
  const values = data.rasters;
  raster.textContent = `地形 ${values.terrain_elevation_m_msl ?? '无数据'} m MSL · 气象 ${values.weather_value ?? '无数据'} · 人口 ${values.population_density ?? '无数据'}`;
  box.append(heading, raster);
  for (const [name, features] of Object.entries(data.features)) {
    if (!features.length) continue;
    const pre = document.createElement('pre');
    pre.textContent = `${name}: ${JSON.stringify(features, null, 2)}`;
    box.appendChild(pre);
  }
}

async function inspectCoordinate(coordinate) {
  $('longitude').value = coordinate[0].toFixed(7);
  $('latitude').value = coordinate[1].toFixed(7);
  const data = await request(`/v1/environment?lon=${coordinate[0]}&lat=${coordinate[1]}`);
  showEnvironment(data);
}

function showLocation(coordinate) {
  const latlng = toLatLng(coordinate);
  if (state.locationMarker) state.locationMarker.removeFrom(state.map);
  state.locationMarker = L.circleMarker(latlng, {
    renderer: state.vectorRenderer,
    radius: 9,
    color: '#facc15',
    fillColor: '#facc15',
    fillOpacity: 0.12,
    weight: 3,
    bubblingMouseEvents: false,
  }).addTo(state.map);
  state.map.panTo(latlng);
}

async function geojsonFromZip(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const view = new DataView(bytes.buffer);
  const decoder = new TextDecoder('utf-8');
  let offset = 0;
  while (offset + 30 <= bytes.length && view.getUint32(offset, true) === 0x04034b50) {
    const flags = view.getUint16(offset + 6, true);
    const method = view.getUint16(offset + 8, true);
    const compressedSize = view.getUint32(offset + 18, true);
    const nameLength = view.getUint16(offset + 26, true);
    const extraLength = view.getUint16(offset + 28, true);
    const name = decoder.decode(bytes.slice(offset + 30, offset + 30 + nameLength));
    const dataStart = offset + 30 + nameLength + extraLength;
    if ((flags & 8) !== 0) throw new Error('ZIP 使用了数据描述符，当前离线导入不支持');
    if (/\.geojson$/i.test(name)) {
      if (method !== 0) throw new Error('请使用未压缩（Store）的 GeoJSON ZIP，或先解压再导入');
      return JSON.parse(decoder.decode(bytes.slice(dataStart, dataStart + compressedSize)));
    }
    offset = dataStart + compressedSize;
  }
  throw new Error('ZIP 中没有找到 .geojson 文件');
}

function normalizeGeoJSON(data) {
  if (data.type === 'FeatureCollection' && Array.isArray(data.features)) return data;
  if (data.type === 'Feature') return {type: 'FeatureCollection', features: [data]};
  if (data.type && data.coordinates) {
    return {type: 'FeatureCollection', features: [{type: 'Feature', geometry: data, properties: {}}]};
  }
  throw new Error('文件不是有效的 GeoJSON FeatureCollection、Feature 或 Geometry');
}

async function importFile(file) {
  const raw = file.name.toLowerCase().endsWith('.zip') ? await geojsonFromZip(file) : JSON.parse(await file.text());
  const data = normalizeGeoJSON(raw);
  const mapLayer = geoJSONLayer(data, 'local', file.name).addTo(state.map);
  const layer = {id: `local-${state.localLayers.length + 1}`, name: file.name, data, mapLayer};
  state.localLayers.push(layer);
  addLayerToggle({name: layer.name, kind: 'vector', available: true}, true, checked => {
    if (checked) mapLayer.addTo(state.map);
    else mapLayer.removeFrom(state.map);
  });
  setStatus(`已加载 ${file.name}：${data.features.length} 个要素。`);
}

function exportRoute() {
  const coordinates = state.waypoints.map(waypoint => waypoint.coordinate.map(value => Number(value.toFixed(7))));
  const waypoints = state.waypoints.map((waypoint, index) => {
    const item = {
      sequence: index + 1,
      longitude: coordinates[index][0],
      latitude: coordinates[index][1],
      altitude_m_agl: Number(waypoint.altitude),
      speed_ms: Number(waypoint.speed),
    };
    if (Number.isFinite(waypoint.terrain)) {
      item.altitude_m_msl = Number((waypoint.terrain + waypoint.altitude).toFixed(2));
    }
    return item;
  });
  const feature = {
    type: 'Feature',
    geometry: {type: 'LineString', coordinates},
    properties: {
      schema_version: '2.0',
      route_name: 'MANUAL',
      coordinate_order: '[longitude, latitude]',
      created_by: 'ALE-AAM interactive editor',
      waypoints,
    },
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(feature, null, 2)], {type: 'application/geo+json'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'ale-aam-route.geojson';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  setStatus(`已导出 ${waypoints.length} 个航点的 GeoJSON LineString。`);
}

function bindEvents() {
  $('basemap').addEventListener('change', event => setBasemap(event.target.value));
  $('mode-inspect').addEventListener('click', () => setMode('inspect'));
  $('mode-draw').addEventListener('click', () => setMode('draw'));
  $('mode-pan').addEventListener('click', () => setMode('pan'));
  $('reset-route').addEventListener('click', resetRoute);
  $('reset-view').addEventListener('click', resetView);
  $('export').addEventListener('click', exportRoute);
  $('locate').addEventListener('click', async () => {
    const coordinate = [Number($('longitude').value), Number($('latitude').value)];
    if (!coordinate.every(Number.isFinite)) return setStatus('请输入有效的经纬度。', true);
    showLocation(coordinate);
    try { await inspectCoordinate(coordinate); } catch (error) { setStatus(error.message, true); }
  });
  $('data-file').addEventListener('change', async event => {
    for (const file of event.target.files) {
      try { await importFile(file); } catch (error) { setStatus(`${file.name}: ${error.message}`, true); }
    }
    event.target.value = '';
  });
}

function initializeMap() {
  state.map = L.map('map', {
    zoomControl: true,
    attributionControl: false,
    minZoom: 2,
    maxZoom: 20,
    preferCanvas: true,
    wheelDebounceTime: 25,
  });
  state.map.zoomControl.setPosition('topright');
  state.vectorRenderer = L.canvas({padding: 0.5, tolerance: 5});
  state.map.on('click', async event => {
    if (!state.scenario || state.mode === 'pan') return;
    const coordinate = toCoordinate(event.latlng);
    if (state.mode === 'draw') {
      addWaypoint(coordinate);
      return;
    }
    try { await inspectCoordinate(coordinate); } catch (error) { setStatus(error.message, true); }
  });
}

async function initialize() {
  try {
    initializeMap();
    bindEvents();
    setMode('inspect');
    state.scenario = await request('/v1/scenario');
    state.scenarioBounds = scenarioLeafletBounds();
    resetView();
    renderScenarioLayers();
    await loadBasemaps();
    $('longitude').value = state.scenario.mission.start[0].toFixed(6);
    $('latitude').value = state.scenario.mission.start[1].toFixed(6);
    resetRoute();
    setStatus(`${state.scenario.mission.name} · ${state.scenario.shape[1]} × ${state.scenario.shape[0]} · ${state.scenario.resolution_m} m`);
  } catch (error) {
    setStatus(`场景加载失败：${error.message}`, true);
  }
}

initialize();
