const $ = id => document.getElementById(id);
const SVG_NS = 'http://www.w3.org/2000/svg';
const state = {
  scenario: null,
  world: {width: 1000, height: 700},
  fullView: {x: 0, y: 0, width: 1000, height: 700},
  view: {x: 0, y: 0, width: 1000, height: 700},
  mode: 'inspect',
  waypoints: [],
  selectedWaypoint: null,
  localLayers: [],
  pointer: null,
  draggingWaypoint: null,
  basemaps: [],
  basemap: 'offline',
  basemapGeneration: 0,
  basemapTimer: null,
  layerControls: new Map(),
  demWasVisible: true,
};

async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data;
}

function svgElement(name, attributes = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function setStatus(message, isError = false) {
  $('status').textContent = message;
  $('status').style.color = isError ? '#fca5a5' : '';
}

function toWorld(coordinate) {
  const e = state.scenario.extent;
  return {
    x: (coordinate[0] - e.west) / (e.east - e.west) * state.world.width,
    y: (e.north - coordinate[1]) / (e.north - e.south) * state.world.height,
  };
}

function toLonLat(point) {
  const e = state.scenario.extent;
  return [
    e.west + point.x / state.world.width * (e.east - e.west),
    e.north - point.y / state.world.height * (e.north - e.south),
  ];
}

function clientToWorld(event) {
  const rect = $('map').getBoundingClientRect();
  return {
    x: state.view.x + (event.clientX - rect.left) / rect.width * state.view.width,
    y: state.view.y + (event.clientY - rect.top) / rect.height * state.view.height,
  };
}

function applyView() {
  $('map').setAttribute('viewBox', `${state.view.x} ${state.view.y} ${state.view.width} ${state.view.height}`);
  scheduleBasemapRender();
}

function resetView() {
  state.view = {...state.fullView};
  applyView();
}

function zoom(factor, anchor) {
  const minWidth = state.fullView.width / 40;
  const maxWidth = state.fullView.width * 1.2;
  const nextWidth = Math.max(minWidth, Math.min(maxWidth, state.view.width * factor));
  const scale = nextWidth / state.view.width;
  const nextHeight = state.view.height * scale;
  const point = anchor || {x: state.view.x + state.view.width / 2, y: state.view.y + state.view.height / 2};
  state.view = {
    x: point.x - (point.x - state.view.x) * scale,
    y: point.y - (point.y - state.view.y) * scale,
    width: nextWidth,
    height: nextHeight,
  };
  applyView();
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function lonToTileX(longitude, zoomLevel) {
  return (longitude + 180) / 360 * (2 ** zoomLevel);
}

function latToTileY(latitude, zoomLevel) {
  const radians = clamp(latitude, -85.05112878, 85.05112878) * Math.PI / 180;
  return (1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2 * (2 ** zoomLevel);
}

function tileXToLon(x, zoomLevel) {
  return x / (2 ** zoomLevel) * 360 - 180;
}

function tileYToLat(y, zoomLevel) {
  return Math.atan(Math.sinh(Math.PI * (1 - 2 * y / (2 ** zoomLevel)))) * 180 / Math.PI;
}

function scheduleBasemapRender() {
  if (!state.scenario) return;
  clearTimeout(state.basemapTimer);
  state.basemapTimer = setTimeout(renderBasemapTiles, 60);
}

function visibleLonLatBounds() {
  const topLeft = toLonLat({x: state.view.x, y: state.view.y});
  const bottomRight = toLonLat({x: state.view.x + state.view.width, y: state.view.y + state.view.height});
  return {
    west: clamp(Math.min(topLeft[0], bottomRight[0]), -180, 180),
    south: clamp(Math.min(topLeft[1], bottomRight[1]), -85.05112878, 85.05112878),
    east: clamp(Math.max(topLeft[0], bottomRight[0]), -180, 180),
    north: clamp(Math.max(topLeft[1], bottomRight[1]), -85.05112878, 85.05112878),
  };
}

function tileRange(bounds, zoomLevel) {
  const limit = 2 ** zoomLevel;
  return {
    xMin: clamp(Math.floor(lonToTileX(bounds.west, zoomLevel)), 0, limit - 1),
    xMax: clamp(Math.floor(lonToTileX(bounds.east, zoomLevel)), 0, limit - 1),
    yMin: clamp(Math.floor(latToTileY(bounds.north, zoomLevel)), 0, limit - 1),
    yMax: clamp(Math.floor(latToTileY(bounds.south, zoomLevel)), 0, limit - 1),
  };
}

function renderBasemapTiles() {
  const group = $('basemap-tiles');
  group.textContent = '';
  const definition = state.basemaps.find(item => item.id === state.basemap);
  if (!state.scenario || state.basemap === 'offline' || !definition?.available) return;

  const bounds = visibleLonLatBounds();
  const widthPixels = Math.max(320, $('map').clientWidth || 1000);
  const longitudeSpan = Math.max(0.000001, bounds.east - bounds.west);
  let zoomLevel = clamp(Math.floor(Math.log2(360 * widthPixels / (longitudeSpan * 256))), 2, definition.max_zoom);
  let range = tileRange(bounds, zoomLevel);
  while ((range.xMax - range.xMin + 1) * (range.yMax - range.yMin + 1) > 80 && zoomLevel > 2) {
    zoomLevel -= 1;
    range = tileRange(bounds, zoomLevel);
  }

  const generation = ++state.basemapGeneration;
  let failures = 0;
  for (let x = range.xMin; x <= range.xMax; x += 1) {
    for (let y = range.yMin; y <= range.yMax; y += 1) {
      const northWest = toWorld([tileXToLon(x, zoomLevel), tileYToLat(y, zoomLevel)]);
      const southEast = toWorld([tileXToLon(x + 1, zoomLevel), tileYToLat(y + 1, zoomLevel)]);
      const image = svgElement('image', {
        class: 'basemap-tile',
        href: `/v1/basemaps/${encodeURIComponent(state.basemap)}/${zoomLevel}/${x}/${y}.png`,
        x: northWest.x,
        y: northWest.y,
        width: southEast.x - northWest.x,
        height: southEast.y - northWest.y,
        preserveAspectRatio: 'none',
      });
      image.addEventListener('error', () => {
        if (generation !== state.basemapGeneration) return;
        failures += 1;
        if (failures === 4) {
          setBasemap('offline', true);
          setStatus('在线底图暂时不可用，已自动回退到离线场景图层。', true);
        }
      });
      group.appendChild(image);
    }
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
    control.image?.setAttribute('visibility', 'hidden');
  } else {
    control.input.disabled = false;
    control.input.checked = state.demWasVisible;
    control.image?.setAttribute('visibility', state.demWasVisible ? 'visible' : 'hidden');
  }
}

function setBasemap(providerId, quiet = false) {
  const definition = state.basemaps.find(item => item.id === providerId && item.available)
    || state.basemaps.find(item => item.id === 'offline');
  if (!definition) return;
  state.basemap = definition.id;
  $('basemap').value = definition.id;
  $('basemap-attribution').textContent = definition.attribution;
  updateDemForBasemap();
  renderBasemapTiles();
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
      attribution: 'ALE-AAM 场景数据', max_zoom: 19}];
    select.disabled = true;
    setBasemap('offline', true);
  }
}

function setMode(mode) {
  state.mode = mode;
  $('map').dataset.mode = mode;
  for (const name of ['inspect', 'draw', 'pan']) {
    $(`mode-${name}`).setAttribute('aria-pressed', String(name === mode));
  }
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

function renderScenarioLayers() {
  const group = $('scenario-layers');
  group.textContent = '';
  $('layers').textContent = '';
  state.layerControls.clear();
  const initiallyVisible = new Set(['dem', 'buildings', 'airspace', 'emergency_sites']);
  for (const layer of state.scenario.layers) {
    const visible = layer.available && initiallyVisible.has(layer.id);
    let image = null;
    if (layer.available) {
      image = svgElement('image', {
        id: `layer-${layer.id}`,
        class: 'scenario-layer',
        href: layer.preview_url,
        x: 0, y: 0, width: state.world.width, height: state.world.height,
        preserveAspectRatio: 'none',
        visibility: visible ? 'visible' : 'hidden',
      });
      group.appendChild(image);
    }
    const control = addLayerToggle(layer, visible, checked => {
      if (image) image.setAttribute('visibility', checked ? 'visible' : 'hidden');
    });
    state.layerControls.set(layer.id, {...control, image});
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
    altitude.addEventListener('change', () => waypoint.altitude = Number(altitude.value));
    altitudeLabel.appendChild(altitude);
    const speedLabel = document.createElement('label');
    speedLabel.textContent = '速度 m/s';
    const speed = document.createElement('input');
    speed.type = 'number';
    speed.min = state.scenario.constraints.speed_ms.min;
    speed.max = state.scenario.constraints.speed_ms.max;
    speed.step = '0.5';
    speed.value = waypoint.speed;
    speed.addEventListener('change', () => waypoint.speed = Number(speed.value));
    speedLabel.appendChild(speed);
    fields.append(altitudeLabel, speedLabel);
    item.append(head, fields);
    item.addEventListener('click', event => {
      if (event.target.tagName !== 'INPUT' && event.target.tagName !== 'BUTTON') {
        state.selectedWaypoint = index;
        renderDraft();
      }
    });
    container.appendChild(item);
  });
  $('export').disabled = state.waypoints.length < 2;
}

function renderDraft() {
  const group = $('draft');
  group.textContent = '';
  if (state.waypoints.length > 1) {
    const points = state.waypoints.map(item => {
      const point = toWorld(item.coordinate);
      return `${point.x},${point.y}`;
    }).join(' ');
    group.appendChild(svgElement('polyline', {class: 'route-line', points}));
  }
  const radius = Math.max(5, state.view.width * 0.006);
  state.waypoints.forEach((waypoint, index) => {
    const point = toWorld(waypoint.coordinate);
    const circle = svgElement('circle', {
      class: `waypoint${state.selectedWaypoint === index ? ' selected' : ''}`,
      cx: point.x, cy: point.y, r: radius, 'data-index': index,
    });
    circle.addEventListener('pointerdown', event => {
      event.stopPropagation();
      state.selectedWaypoint = index;
      state.draggingWaypoint = index;
      $('map').setPointerCapture(event.pointerId);
      renderDraft();
    });
    const label = svgElement('text', {class: 'waypoint-label', x: point.x + radius * 1.4, y: point.y - radius * 1.2});
    label.textContent = String(index + 1);
    group.append(circle, label);
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
  const r = data.rasters;
  raster.textContent = `地形 ${r.terrain_elevation_m_msl ?? '无数据'} m MSL · 气象 ${r.weather_value ?? '无数据'} · 人口 ${r.population_density ?? '无数据'}`;
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
  const point = toWorld(coordinate);
  const radius = Math.max(7, state.view.width * 0.009);
  const group = $('location-marker');
  group.textContent = '';
  group.appendChild(svgElement('circle', {class: 'location-dot', cx: point.x, cy: point.y, r: radius}));
  state.view.x = point.x - state.view.width / 2;
  state.view.y = point.y - state.view.height / 2;
  applyView();
}

function geometryPath(geometry) {
  const line = coordinates => coordinates.map((coordinate, index) => {
    const point = toWorld(coordinate);
    return `${index ? 'L' : 'M'}${point.x},${point.y}`;
  }).join(' ');
  if (geometry.type === 'LineString') return line(geometry.coordinates);
  if (geometry.type === 'MultiLineString') return geometry.coordinates.map(line).join(' ');
  if (geometry.type === 'Polygon') return geometry.coordinates.map(ring => `${line(ring)} Z`).join(' ');
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.flatMap(polygon => polygon.map(ring => `${line(ring)} Z`)).join(' ');
  return '';
}

function renderLocalLayer(layer) {
  const group = svgElement('g', {'data-local-layer': layer.id});
  for (const feature of layer.data.features) {
    const geometry = feature.geometry || {};
    if (geometry.type === 'Point') {
      const point = toWorld(geometry.coordinates);
      const circle = svgElement('circle', {class: 'local-feature', cx: point.x, cy: point.y, r: 5});
      circle.addEventListener('pointerdown', event => event.stopPropagation());
      circle.addEventListener('pointerup', event => event.stopPropagation());
      circle.addEventListener('click', event => showLocalProperties(event, feature, layer.name));
      group.appendChild(circle);
      continue;
    }
    const pathData = geometryPath(geometry);
    if (!pathData) continue;
    const path = svgElement('path', {
      class: `local-feature${geometry.type.includes('Line') ? ' line' : ''}`,
      d: pathData,
      'fill-rule': 'evenodd',
    });
    path.addEventListener('pointerdown', event => event.stopPropagation());
    path.addEventListener('pointerup', event => event.stopPropagation());
    path.addEventListener('click', event => showLocalProperties(event, feature, layer.name));
    group.appendChild(path);
  }
  $('local-layers').appendChild(group);
  layer.node = group;
  addLayerToggle({name: layer.name, kind: 'vector', available: true}, true, checked => {
    group.setAttribute('visibility', checked ? 'visible' : 'hidden');
  });
}

function showLocalProperties(event, feature, name) {
  event.stopPropagation();
  const box = $('environment');
  box.textContent = '';
  const heading = document.createElement('strong');
  heading.textContent = name;
  const pre = document.createElement('pre');
  pre.textContent = JSON.stringify(feature.properties || {}, null, 2);
  box.append(heading, pre);
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
  if (data.type && data.coordinates) return {type: 'FeatureCollection', features: [{type: 'Feature', geometry: data, properties: {}}]};
  throw new Error('文件不是有效的 GeoJSON FeatureCollection、Feature 或 Geometry');
}

async function importFile(file) {
  const raw = file.name.toLowerCase().endsWith('.zip') ? await geojsonFromZip(file) : JSON.parse(await file.text());
  const data = normalizeGeoJSON(raw);
  const layer = {id: `local-${state.localLayers.length + 1}`, name: file.name, data};
  state.localLayers.push(layer);
  renderLocalLayer(layer);
  setStatus(`已加载 ${file.name}：${data.features.length} 个要素。`);
}

function exportRoute() {
  const coordinates = state.waypoints.map(waypoint => waypoint.coordinate.map(value => Number(value.toFixed(7))));
  const waypoints = state.waypoints.map((waypoint, index) => {
    const item = {
      sequence: index + 1,
      longitude: coordinates[index][0], latitude: coordinates[index][1],
      altitude_m_agl: Number(waypoint.altitude), speed_ms: Number(waypoint.speed),
    };
    if (Number.isFinite(waypoint.terrain)) item.altitude_m_msl = Number((waypoint.terrain + waypoint.altitude).toFixed(2));
    return item;
  });
  const feature = {
    type: 'Feature',
    geometry: {type: 'LineString', coordinates},
    properties: {
      schema_version: '2.0', route_name: 'MANUAL',
      coordinate_order: '[longitude, latitude]',
      created_by: 'ALE-AAM interactive editor', waypoints,
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
  $('zoom-in').addEventListener('click', () => zoom(0.7));
  $('zoom-out').addEventListener('click', () => zoom(1.4));
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

  const map = $('map');
  map.addEventListener('wheel', event => {
    event.preventDefault();
    zoom(event.deltaY < 0 ? 0.8 : 1.25, clientToWorld(event));
  }, {passive: false});
  map.addEventListener('pointerdown', event => {
    if (state.draggingWaypoint !== null || event.button !== 0) return;
    state.pointer = {id: event.pointerId, x: event.clientX, y: event.clientY, view: {...state.view}, dragged: false};
    map.setPointerCapture(event.pointerId);
  });
  map.addEventListener('pointermove', event => {
    if (state.draggingWaypoint !== null) {
      state.waypoints[state.draggingWaypoint].coordinate = toLonLat(clientToWorld(event));
      renderDraft();
      return;
    }
    if (!state.pointer || state.pointer.id !== event.pointerId || state.mode !== 'pan') return;
    const rect = map.getBoundingClientRect();
    const dx = event.clientX - state.pointer.x;
    const dy = event.clientY - state.pointer.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) state.pointer.dragged = true;
    state.view.x = state.pointer.view.x - dx / rect.width * state.pointer.view.width;
    state.view.y = state.pointer.view.y - dy / rect.height * state.pointer.view.height;
    map.dataset.panning = 'true';
    applyView();
  });
  map.addEventListener('pointerup', async event => {
    if (state.draggingWaypoint !== null) {
      const index = state.draggingWaypoint;
      state.draggingWaypoint = null;
      await sampleWaypoint(index);
      renderDraft();
      return;
    }
    if (!state.pointer || state.pointer.id !== event.pointerId) return;
    const pointer = state.pointer;
    state.pointer = null;
    map.dataset.panning = 'false';
    if (pointer.dragged || state.mode === 'pan') return;
    const coordinate = toLonLat(clientToWorld(event));
    if (state.mode === 'draw') addWaypoint(coordinate);
    else {
      try { await inspectCoordinate(coordinate); } catch (error) { setStatus(error.message, true); }
    }
  });
  map.addEventListener('pointercancel', () => {
    state.pointer = null;
    state.draggingWaypoint = null;
    map.dataset.panning = 'false';
  });
}

async function initialize() {
  bindEvents();
  setMode('inspect');
  try {
    state.scenario = await request('/v1/scenario');
    const e = state.scenario.extent;
    const latitude = (e.south + e.north) / 2 * Math.PI / 180;
    state.world.height = Math.max(320, 1000 * (e.north - e.south) / (e.east - e.west) / Math.cos(latitude));
    state.fullView = {x: 0, y: 0, width: state.world.width, height: state.world.height};
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
