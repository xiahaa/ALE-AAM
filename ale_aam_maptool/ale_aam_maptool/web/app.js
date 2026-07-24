const $ = id => document.getElementById(id);
const colors = {A:'#ef4444', B:'#22c55e', C:'#3b82f6'};
let scenario, features = {};

async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data;
}
function points(feature) {
  const e = scenario.extent, width = $('map').clientWidth, height = $('map').clientHeight;
  return feature.geometry.coordinates.map(([lon,lat]) =>
    `${(lon-e.west)/(e.east-e.west)*width},${(e.north-lat)/(e.north-e.south)*height}`).join(' ');
}
function draw() {
  const svg = $('routes'); svg.innerHTML = '';
  svg.setAttribute('viewBox', `0 0 ${$('map').clientWidth} ${$('map').clientHeight}`);
  for (const [name, feature] of Object.entries(features)) {
    const line = document.createElementNS('http://www.w3.org/2000/svg','polyline');
    line.setAttribute('points', points(feature)); line.setAttribute('stroke', colors[name]);
    line.setAttribute('fill','none'); line.setAttribute('stroke-width','3'); svg.appendChild(line);
  }
}
async function initialize() {
  try {
    scenario = await request('/v1/scenario'); $('preview').src='/v1/preview?route=A';
    $('status').textContent = `${scenario.mission.name}\n${scenario.shape[1]} × ${scenario.shape[0]} @ ${scenario.resolution_m} m\n${scenario.crs}`;
  } catch(e) { $('status').textContent = `错误：${e.message}`; }
}
async function planOne(name) {
  const data = await request('/v1/plan',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({route:name})});
  features[name]=data.feature; draw(); $('export').disabled=false;
  $('status').textContent=`路线 ${name}\n${data.metrics.total_distance_m} m\n${data.metrics.estimated_duration_s} s\n${data.metrics.estimated_energy_wh} Wh`;
}
$('plan').onclick=()=>planOne($('route').value[0]).catch(e=>$('status').textContent=e.message);
$('all').onclick=async()=>{try{const data=await request('/v1/plan-all',{method:'POST'});features=Object.fromEntries(Object.entries(data).map(([k,v])=>[k,v.feature]));draw();$('export').disabled=false;$('status').textContent=Object.entries(data).map(([k,v])=>`${k}: ${v.metrics.total_distance_m} m`).join('\n');}catch(e){$('status').textContent=e.message;}};
$('export').onclick=()=>{const data={type:'FeatureCollection',features:Object.values(features)};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/geo+json'}));a.download='routes.geojson';a.click();};
window.onresize=draw; initialize();
