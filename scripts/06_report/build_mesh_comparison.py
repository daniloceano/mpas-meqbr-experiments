#!/usr/bin/env python3
"""Build the self-contained MEQ-02A interactive mesh comparison report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), *args], text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"


HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,">
<title>MEQ-02A · Atlas das malhas Meq-BR</title>
<style>
:root{--ink:#17231f;--muted:#60706a;--paper:#f7f5ef;--card:#fffdf8;--line:#d9d8ce;--ctl:#2a6f97;--exp:#e07a3f;--oval:#6a4c93;--accent:#147d64;--danger:#9d3c3c}
*{box-sizing:border-box} body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:34px clamp(20px,5vw,70px) 26px;background:linear-gradient(135deg,#142d29,#235248);color:#fff}
header .eyebrow{text-transform:uppercase;letter-spacing:.13em;font-size:12px;color:#b8ddd3;font-weight:700} h1{font-size:clamp(28px,4vw,48px);line-height:1.08;margin:7px 0 12px;max-width:920px} header p{max-width:900px;color:#dcece7;margin:0}
main{max-width:1460px;margin:auto;padding:26px clamp(14px,3vw,36px) 60px}.summary{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:12px;margin:-8px 0 24px}.metric,.card{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 24px #183b3020}.metric{padding:16px}.metric strong{display:block;font-size:25px}.metric span{color:var(--muted);font-size:13px}
h2{font-size:24px;margin:34px 0 12px} h3{margin:0 0 10px}.note{border-left:4px solid var(--accent);padding:10px 14px;background:#edf7f3;border-radius:0 9px 9px 0;margin:14px 0}.warning{border-color:#d58a35;background:#fff5e7}
.atlas{display:grid;grid-template-columns:285px minmax(0,1fr);gap:14px}.controls{padding:16px;align-self:start;position:sticky;top:12px}.control-section{border-top:1px solid var(--line);padding-top:12px;margin-top:12px}.control-section:first-child{border-top:0;padding-top:0;margin-top:0}.control-title{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:800;margin-bottom:8px}.toggle{display:flex;align-items:center;gap:9px;margin:7px 0}.toggle input{width:17px;height:17px}.swatch{width:12px;height:12px;border-radius:3px;display:inline-block}.buttons{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}button{border:1px solid #bac3be;background:#fff;border-radius:8px;padding:7px 10px;color:var(--ink);cursor:pointer}button:hover{background:#eef4f1}.map-card{padding:10px;position:relative;overflow:hidden}.map-toolbar{display:flex;justify-content:space-between;align-items:center;padding:5px 7px 10px;color:var(--muted);font-size:13px}.map-wrap{height:min(72vh,780px);min-height:520px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#edf4f1;position:relative}.map-wrap svg{width:100%;height:100%;display:block;touch-action:none;cursor:grab}.map-wrap svg.dragging{cursor:grabbing}.tooltip{position:absolute;pointer-events:none;background:#17231fee;color:#fff;padding:7px 9px;border-radius:7px;font-size:12px;display:none;z-index:5;max-width:240px}.legend{position:absolute;right:18px;bottom:18px;background:#fffef0ee;padding:9px 11px;border-radius:8px;border:1px solid var(--line);font-size:12px}.legend div{margin:3px 0}.selected-panel{margin-top:12px;padding:15px}.coverage-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.coverage-card{padding:10px;border-radius:9px;background:#f1f3ef}.coverage-card strong{font-size:20px;display:block}.coverage-card small{color:var(--muted)}
.coverage-chart{padding:18px 20px}.chart-axis{display:grid;grid-template-columns:minmax(125px,190px) minmax(260px,1fr);gap:14px;margin-bottom:8px;color:var(--muted);font-size:11px}.chart-axis-scale{display:flex;justify-content:space-between;border-bottom:1px solid #c8cec9;padding-bottom:4px}.chart-group{display:grid;grid-template-columns:minmax(125px,190px) minmax(260px,1fr);gap:14px;padding:11px 0;border-bottom:1px solid #e5e3da}.chart-group:last-child{border-bottom:0}.chart-basin{border:0;background:transparent;padding:2px 0;text-align:left;color:var(--ink);font-weight:700}.chart-basin:hover{background:transparent;text-decoration:underline}.chart-bars{display:grid;gap:5px}.chart-bar-row{display:grid;grid-template-columns:82px minmax(120px,1fr) 55px;gap:8px;align-items:center;font-size:12px}.chart-series{color:var(--muted);white-space:nowrap}.chart-track{height:13px;background:#e5e9e6;border-radius:3px;overflow:hidden}.chart-bar{height:100%;transition:width .24s ease}.chart-value{text-align:right;font-variant-numeric:tabular-nums}.chart-empty{padding:32px;text-align:center;color:var(--muted)}.sub{display:block;color:var(--muted);font-size:11px}.positive{color:#0d7a58;font-weight:700}.negative{color:var(--danger);font-weight:700}.mesh-grid,.site-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.mesh-card,.site-card{padding:16px}.mesh-card .count{font-size:27px;font-weight:800}.pill{display:inline-block;border-radius:999px;padding:3px 8px;background:#e8ece8;font-size:12px;margin:2px 3px 2px 0}details{margin:10px 0;border:1px solid var(--line);border-radius:10px;background:var(--card);padding:10px 13px}summary{cursor:pointer;font-weight:700}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;overflow-wrap:anywhere}.footer{color:var(--muted);margin-top:34px;border-top:1px solid var(--line);padding-top:18px;font-size:13px}
.gridline{stroke:#b8c7c1;stroke-width:.7}.gridlabel{fill:#63746d;font-size:10px}.coastline{fill:none;stroke:#273a34;stroke-width:1.35;vector-effect:non-scaling-stroke}.country-boundary{fill:none;stroke:#4b5954;stroke-width:1.05;opacity:.9;vector-effect:non-scaling-stroke}.state-boundary{fill:none;stroke:#66736e;stroke-width:.72;opacity:.85;vector-effect:non-scaling-stroke}.basin{fill:#cfb77d55;stroke:#6d5524;stroke-width:1.1;vector-effect:non-scaling-stroke}.basin.selected{fill:#ffd56d99;stroke:#7d4f00;stroke-width:2.2}.outer{fill:none;stroke-width:2.2;vector-effect:non-scaling-stroke}.buffer{stroke:none;opacity:.095}.refined{stroke:none;opacity:.28}.site{stroke:#fff;stroke-width:1.8;vector-effect:non-scaling-stroke}.surface-site{fill:#b34f2c;stroke:#fff;stroke-width:1.4;vector-effect:non-scaling-stroke}.site-label,.surface-label{font-size:11px;font-weight:800;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}.surface-label{font-size:9.5px;fill:#78331d}.line-swatch{display:inline-block;width:16px;border-top:2px solid #273a34;vertical-align:middle}.country-swatch{border-color:#4b5954;border-top-width:1px}.state-swatch{border-color:#66736e;border-top-width:1px;opacity:.8}.dot-swatch{display:inline-block;width:9px;height:9px;border-radius:50%;background:#17231f;vertical-align:middle}.diamond-swatch{display:inline-block;width:8px;height:8px;background:#b34f2c;transform:rotate(45deg);vertical-align:middle}.hidden{display:none!important}
@media(max-width:980px){.summary{grid-template-columns:repeat(2,1fr)}.atlas{grid-template-columns:1fr}.controls{position:static}.mesh-grid,.site-grid{grid-template-columns:1fr}.map-wrap{min-height:460px}.coverage-cards{grid-template-columns:1fr}}
@media(max-width:700px){.chart-axis{display:none}.chart-group{grid-template-columns:1fr;gap:5px}.chart-bar-row{grid-template-columns:74px minmax(100px,1fr) 50px}}
@media(max-width:560px){.summary{grid-template-columns:1fr}.map-wrap{min-height:390px}header{padding:28px 18px}.legend{display:none}.coverage-chart{padding:12px}}
</style>
</head>
<body>
<header><div class="eyebrow">Meq-BR · MEQ-02A · evidência geométrica</div><h1>Atlas interativo das malhas da Margem Equatorial Brasileira</h1><p>Comparação direta entre a malha original de CTL/EXP01, a malha efetivamente usada pelo EXP02 e a nova candidata Oval. Contornos e espaçamentos são medidos nos arquivos MPAS; não representam desempenho meteorológico.</p></header>
<main>
<section class="summary" id="summary"></section>
<div class="note"><strong>Leitura científica.</strong> CTL/EXP01 usa a malha original. EXP02 amplia o domínio e introduz tratamento gradual de fronteira. A Oval orienta o núcleo refinado ao longo da Margem Equatorial e foi ajustada para preservar, em especial, Foz do Amazonas e Potiguar. Ela ainda requer validação operacional e meteorológica.</div>
<div class="note" id="validation-summary"></div>
<h2>Mapa comparativo</h2>
<section class="atlas">
  <aside class="card controls">
    <div class="control-section"><div class="control-title">Malhas</div><div id="mesh-controls"></div><div class="buttons"><button data-preset="all">Todas</button><button data-preset="ctl">Só CTL</button><button data-preset="exp02">Só EXP02</button><button data-preset="oval">Só Oval</button></div></div>
    <div class="control-section"><div class="control-title">Camadas</div><label class="toggle"><input type="checkbox" data-feature="outer" checked> Limites externos</label><label class="toggle"><input type="checkbox" data-feature="buffer" checked> Domínio / buffer</label><label class="toggle"><input type="checkbox" data-feature="refined" checked> Região refinada &lt;5,5 km</label><label class="toggle"><input type="checkbox" id="toggle-coastline" checked> Linha de costa</label><label class="toggle"><input type="checkbox" id="toggle-countries" checked> Fronteiras internacionais</label><label class="toggle"><input type="checkbox" id="toggle-states" checked> Limites estaduais</label><label class="toggle"><input type="checkbox" id="toggle-basins" checked> Bacias sedimentares</label><label class="toggle"><input type="checkbox" id="toggle-sites" checked> LiDARes P0 e LPI</label><label class="toggle"><input type="checkbox" id="toggle-surface" checked> Estações INMET</label></div>
    <div class="control-section"><div class="control-title">Bacias</div><div id="basin-controls"></div></div>
  </aside>
  <div>
    <div class="card map-card"><div class="map-toolbar"><span>Arraste para mover · roda para ampliar · clique numa bacia</span><button id="reset-map">Restaurar mapa</button></div><div class="map-wrap" id="map-wrap"><svg id="map" viewBox="0 0 1100 740" aria-label="Mapa interativo das malhas e bacias"></svg><div class="tooltip" id="tooltip"></div><div class="legend" id="legend"></div></div></div>
    <div class="card selected-panel" id="selected-panel"></div>
  </div>
</section>
<h2>Cobertura refinada das bacias</h2><p>As barras mostram a fração da área total da bacia com espaçamento equivalente &lt;5,5 km. Passe o ponteiro sobre uma barra para consultar também a cobertura do domínio. O gráfico acompanha as malhas visíveis no mapa.</p><div class="card coverage-chart" id="coverage-chart" aria-live="polite"></div>
<h2>Identificação e integridade</h2><section class="mesh-grid" id="mesh-grid"></section>
<h2>Rede observacional</h2><section class="site-grid" id="site-grid"></section>
<details><summary>Proveniência e método</summary><div id="provenance"></div></details>
<details><summary>Limitações</summary><ul id="limitations"></ul></details>
<div class="footer">Relatório especializado gerado por <span class="mono">scripts/06_report/build_mesh_comparison.py</span>. Artefato estático, sem backend. Branch local: <span class="mono">__BRANCH__</span>; commit-base: <span class="mono">__COMMIT__</span>; construção: __BUILT__.</div>
</main>
<script id="mesh-data" type="application/json">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('mesh-data').textContent);
const colors={ctl:'#2a6f97',exp02:'#e07a3f',oval:'#6a4c93'};
const meshKeys=['ctl','exp02','oval']; const W=1100,H=740,extent={w:-65,e:-24,s:-17,n:16};
const project=([lon,lat])=>[(lon-extent.w)/(extent.e-extent.w)*W,(extent.n-lat)/(extent.n-extent.s)*H];
function linePath(points,close=false){let d='';points.forEach((p,i)=>{const [x,y]=project(p);d+=(i?'L':'M')+x.toFixed(2)+','+y.toFixed(2)});return d+(close?'Z':'')}
function pathGeometry(g){if(g.type==='LineString')return linePath(g.coordinates);if(g.type==='MultiLineString')return g.coordinates.map(x=>linePath(x)).join('');const polygons=g.type==='Polygon'?[g.coordinates]:g.coordinates;return polygons.map(poly=>poly.map(ring=>linePath(ring,true)).join('')).join('')}
const svg=document.getElementById('map');
function el(tag,attrs={},parent=svg){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);parent.appendChild(n);return n}
const grid=el('g',{id:'grid'});for(let lon=-60;lon<=-25;lon+=5){let [x]=project([lon,0]);el('line',{x1:x,y1:0,x2:x,y2:H,class:'gridline'},grid);let t=el('text',{x:x+4,y:16,class:'gridlabel'},grid);t.textContent=Math.abs(lon)+'°W'}for(let lat=-15;lat<=15;lat+=5){let [,y]=project([0,lat]);el('line',{x1:0,y1:y,x2:W,y2:y,class:'gridline'},grid);let t=el('text',{x:4,y:y-4,class:'gridlabel'},grid);t.textContent=lat===0?'0°':Math.abs(lat)+'°'+(lat>0?'N':'S')}
const meshRoot=el('g',{id:'meshes'});for(const key of meshKeys){const m=data.meshes[key],g=el('g',{'data-mesh-group':key},meshRoot);el('path',{d:pathGeometry(m.geometry.domain),fill:colors[key],class:'buffer feature-buffer'},g);el('path',{d:pathGeometry(m.geometry.refined),fill:colors[key],class:'refined feature-refined'},g);el('path',{d:pathGeometry(m.geometry.domain),stroke:colors[key],class:'outer feature-outer'},g)}
const contextRoot=el('g',{id:'cartographic-context'});const stateRoot=el('g',{id:'state-boundaries'},contextRoot);el('path',{d:pathGeometry(data.cartography.state_boundaries),class:'state-boundary'},stateRoot);const countryRoot=el('g',{id:'country-boundaries'},contextRoot);el('path',{d:pathGeometry(data.cartography.country_boundaries),class:'country-boundary'},countryRoot);const coastlineRoot=el('g',{id:'coastline'},contextRoot);el('path',{d:pathGeometry(data.cartography.coastline),class:'coastline'},coastlineRoot);
const basinRoot=el('g',{id:'basins'});for(const b of data.basins){const p=el('path',{d:pathGeometry(b.geometry),class:'basin','data-basin':b.key,tabindex:'0'},basinRoot);p.addEventListener('click',()=>selectBasin(b.key));p.addEventListener('mousemove',e=>tip(e,`${b.name} · ${fmt(b.area_km2,0)} km²`));p.addEventListener('mouseleave',hideTip)}
const siteRoot=el('g',{id:'sites'});for(const s of data.sites){const [x,y]=project([s.lon,s.lat]);el('circle',{cx:x,cy:y,r:5.5,fill:'#17231f',class:'site'},siteRoot);let t=el('text',{x:x+8,y:y-7,class:'site-label'},siteRoot);t.textContent=s.key}
const surfaceLabelOffsets={'81715099999':[-9,-9,'end'],'81758099999':[-8,-8,'end'],'81798099999':[-8,15,'end'],'81835099999':[8,15,'start']};const surfaceRoot=el('g',{id:'surface-stations'});for(const s of data.surface_stations){const [x,y]=project([s.lon,s.lat]),[dx,dy,anchor]=surfaceLabelOffsets[s.id]||[7,-7,'start'];const p=el('rect',{x:x-4,y:y-4,width:8,height:8,transform:`rotate(45 ${x} ${y})`,class:'surface-site'},surfaceRoot);p.addEventListener('mousemove',e=>tip(e,`${s.name} · ISD ${s.id} · ${s.periods.join(' e ')}`));p.addEventListener('mouseleave',hideTip);let t=el('text',{x:x+dx,y:y+dy,'text-anchor':anchor,class:'surface-label'},surfaceRoot);t.textContent=s.label}
function fmt(v,n=2){return Number(v).toLocaleString('pt-BR',{minimumFractionDigits:n,maximumFractionDigits:n})}function pct(v){return fmt(v,2)+'%'}
document.getElementById('summary').innerHTML=`<div class="metric"><strong>${fmt(data.meshes.oval.nCells,0)}</strong><span>células reais da Oval</span></div><div class="metric"><strong>${data.basins.length}</strong><span>bacias marítimas intersectadas</span></div><div class="metric"><strong>${pct(findBasin('Foz do Amazonas').coverage.oval.refined_pct)}</strong><span>Foz refinada na Oval</span></div><div class="metric"><strong>${pct(findBasin('Potiguar').coverage.oval.refined_pct)}</strong><span>Potiguar refinada na Oval</span></div>`;
const foz=findBasin('Foz do Amazonas'),pot=findBasin('Potiguar');document.getElementById('validation-summary').innerHTML=`<strong>Geometria materializada.</strong> A previsão geométrica foi ${pct(data.oval_validation.predicted_refined_pct['Foz do Amazonas'])} para Foz e ${pct(data.oval_validation.predicted_refined_pct.Potiguar)} para Potiguar. Na malha MPAS efetiva, os valores são ${pct(foz.coverage.oval.refined_pct)} e ${pct(pot.coverage.oval.refined_pct)}, respectivamente; ambos permanecem acima do EXP02.`;
const meshControls=document.getElementById('mesh-controls');for(const key of meshKeys){meshControls.insertAdjacentHTML('beforeend',`<label class="toggle"><input type="checkbox" data-mesh="${key}" checked><span class="swatch" style="background:${colors[key]}"></span>${data.meshes[key].label}</label>`)}
const basinControls=document.getElementById('basin-controls');for(const b of data.basins){basinControls.insertAdjacentHTML('beforeend',`<label class="toggle"><input type="checkbox" data-basin-toggle="${b.key}" checked> ${b.name}</label>`)}
document.addEventListener('change',e=>{if(e.target.dataset.mesh){document.querySelector(`[data-mesh-group="${e.target.dataset.mesh}"]`).classList.toggle('hidden',!e.target.checked);renderCoverageChart()}if(e.target.dataset.feature){document.querySelectorAll(`.feature-${e.target.dataset.feature}`).forEach(x=>x.classList.toggle('hidden',!e.target.checked))}if(e.target.dataset.basinToggle){document.querySelector(`[data-basin="${e.target.dataset.basinToggle}"]`).classList.toggle('hidden',!e.target.checked)}if(e.target.id==='toggle-coastline')coastlineRoot.classList.toggle('hidden',!e.target.checked);if(e.target.id==='toggle-countries')countryRoot.classList.toggle('hidden',!e.target.checked);if(e.target.id==='toggle-states')stateRoot.classList.toggle('hidden',!e.target.checked);if(e.target.id==='toggle-basins')basinRoot.classList.toggle('hidden',!e.target.checked);if(e.target.id==='toggle-sites')siteRoot.classList.toggle('hidden',!e.target.checked);if(e.target.id==='toggle-surface')surfaceRoot.classList.toggle('hidden',!e.target.checked)});
document.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>{const p=b.dataset.preset;document.querySelectorAll('[data-mesh]').forEach(c=>{c.checked=p==='all'||c.dataset.mesh===p;c.dispatchEvent(new Event('change',{bubbles:true}))})});
function findBasin(name){return data.basins.find(b=>b.name===name)}
function activeMeshes(){return meshKeys.filter(k=>document.querySelector(`[data-mesh="${k}"]`)?.checked)}
function renderCoverageChart(){const active=activeMeshes(),chart=document.getElementById('coverage-chart');if(!active.length){chart.innerHTML='<div class="chart-empty">Selecione ao menos uma malha para exibir as coberturas.</div>';return}const axis=`<div class="chart-axis"><span>Bacia</span><div class="chart-axis-scale"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div></div>`;const groups=data.basins.map(b=>`<div class="chart-group"><button class="chart-basin" type="button" data-chart-basin="${b.key}">${b.name}</button><div class="chart-bars">${active.map(k=>{const c=b.coverage[k];return `<div class="chart-bar-row" title="${data.meshes[k].label}: refinada ${pct(c.refined_pct)}; domínio ${pct(c.domain_pct)}"><span class="chart-series">${data.meshes[k].label}</span><div class="chart-track"><div class="chart-bar" style="width:${Math.max(0,Math.min(100,c.refined_pct))}%;background:${colors[k]}"></div></div><strong class="chart-value">${pct(c.refined_pct)}</strong></div>`}).join('')}</div></div>`).join('');chart.innerHTML=axis+groups;chart.querySelectorAll('[data-chart-basin]').forEach(button=>button.onclick=()=>selectBasin(button.dataset.chartBasin))}
function selectBasin(key){document.querySelectorAll('.basin').forEach(p=>p.classList.toggle('selected',p.dataset.basin===key));const b=data.basins.find(x=>x.key===key),c=b.coverage,s=b.sensitivity_2km;const sensitivity=s?`<p class="sub">Sensibilidade da amostragem: com passo de 2 km, EXP02=${pct(s.exp02.refined_pct)} e Oval=${pct(s.oval.refined_pct)}; com 1 km, EXP02=${pct(c.exp02.refined_pct)} e Oval=${pct(c.oval.refined_pct)}.</p>`:'';document.getElementById('selected-panel').innerHTML=`<h3>${b.name}</h3><div class="coverage-cards">${meshKeys.map(k=>`<div class="coverage-card" style="border-top:4px solid ${colors[k]}"><small>${data.meshes[k].label}</small><strong>${pct(c[k].refined_pct)}</strong><span>refinada · domínio ${pct(c[k].domain_pct)}</span></div>`).join('')}</div><p>Diferença Oval − EXP02: <strong class="${b.oval_minus_exp02_refined_pp>=0?'positive':'negative'}">${b.oval_minus_exp02_refined_pp>=0?'+':''}${fmt(b.oval_minus_exp02_refined_pp)} p.p.</strong>. Área total: ${fmt(b.area_km2,0)} km²; ${fmt(b.sample_points_1km,0)} pontos comuns de 1 km.</p>${sensitivity}`}
document.getElementById('selected-panel').innerHTML='<h3>Detalhe por bacia</h3><p>Selecione qualquer bacia no mapa ou no gráfico para comparar suas coberturas. Todas começam com o mesmo tratamento visual.</p>';renderCoverageChart();
const meshGrid=document.getElementById('mesh-grid');for(const k of meshKeys){const m=data.meshes[k],q=m.spacing_km,i=m.integrity;meshGrid.insertAdjacentHTML('beforeend',`<article class="card mesh-card" style="border-top:5px solid ${colors[k]}"><h3>${m.label}</h3><div class="count">${fmt(m.nCells,0)} células</div><p>${m.role}</p><span class="pill">${fmt(m.nEdges,0)} arestas</span><span class="pill">${fmt(m.nVertices,0)} vértices</span><span class="pill">${fmt(m.refined_cell_fraction_pct,1)}% células &lt;5,5 km</span><p><strong>Espaçamento equivalente:</strong> ${fmt(q.min,2)}–${fmt(q.max,2)} km; mediana ${fmt(q.median,2)} km.</p><p>${m.parameters}</p><p class="sub">SHA-256 <span class="mono">${m.sha256}</span></p><p class="sub">Integridade: Euler=${i.euler_cells_minus_edges_plus_vertices}; ${i.obtuse_triangles} triângulos obtusos; índices inválidos=${Object.values(i.connectivity).reduce((a,x)=>a+x.invalid_indices,0)}.</p></article>`)}
const siteGrid=document.getElementById('site-grid');for(const s of data.sites){siteGrid.insertAdjacentHTML('beforeend',`<article class="card site-card"><h3>${s.label}</h3><p><span class="dot-swatch"></span> LiDAR offshore · ${fmt(Math.abs(s.lat),4)}°S, ${fmt(Math.abs(s.lon),4)}°W</p>${meshKeys.map(k=>`<span class="pill" style="border-left:4px solid ${colors[k]}">${data.meshes[k].label}: ${fmt(s.meshes[k].spacing_km,2)} km · ${s.meshes[k].refined?'refinada':'não refinada'}</span>`).join('')}</article>`)}for(const s of data.surface_stations){siteGrid.insertAdjacentHTML('beforeend',`<article class="card site-card"><h3>${s.label}</h3><p><span class="diamond-swatch"></span> Estação automática INMET · ${fmt(Math.abs(s.lat),3)}°S, ${fmt(Math.abs(s.lon),3)}°W</p><span class="pill">ISD ${s.id}</span><span class="pill">período${s.periods.length>1?'s':''} ${s.periods.join(' e ')}</span></article>`)}
const idLines=Object.entries(data.identity_checks).flatMap(([k,rows])=>rows.map(r=>`<li><strong>${r.experiment}</strong>: ${data.meshes[k].label}, nCells ${fmt(r.nCells,0)}, lat/lon exatas após conversão de dtype: ${r.latCell_exact_after_dtype_cast&&r.lonCell_exact_after_dtype_cast?'sim':'não'}.</li>`)).join('');
document.getElementById('provenance').innerHTML=`<p><strong>Geração da Oval:</strong> <span class="mono">${data.generator.command}</span></p><p>Fonte: <span class="mono">${data.generator.repository}</span>, branch <span class="mono">${data.generator.branch}</span>, commit <span class="mono">${data.generator.commit}</span>.</p><p>${data.oval_validation.generation_note}</p><p><strong>Método:</strong> ${data.sampling.spacing_definition}. ${data.sampling.domain_definition}. ${data.sampling.refined_definition}. Amostragem ${data.sampling.step_km} km em ${data.sampling.projection}; ${data.sampling.denominator}.</p><p><strong>Contexto cartográfico:</strong> ${data.cartography.provenance.dataset} ${data.cartography.provenance.scale}, domínio público, usando costa, fronteiras internacionais terrestres e limites administrativos estaduais do cache Cartopy no Swell; ${data.cartography.provenance.browser_simplification}.</p><p><strong>Rede observacional:</strong> LiDARes de ${data.station_provenance.lidars}. As quatro estações automáticas INMET vêm de <span class="mono">${data.station_provenance.surface}</span>, com dados arquivados no ${data.station_provenance.surface_archive}; são as estações efetivamente presentes na análise primária.</p><p><strong>Identidade experimental:</strong></p><ul>${idLines}</ul><p>A previsão analítica era ${fmt(data.oval_validation.predicted_nCells,0)} células; a malha produzida tem ${fmt(data.oval_validation.actual_nCells,0)} (${data.oval_validation.difference_cells>=0?'+':''}${data.oval_validation.difference_cells}).</p>`;
document.getElementById('limitations').innerHTML=data.limitations.map(x=>`<li>${x}</li>`).join('');document.getElementById('legend').innerHTML=meshKeys.map(k=>`<div><span class="swatch" style="background:${colors[k]}"></span> ${data.meshes[k].label}</div>`).join('')+'<div><span class="line-swatch"></span> costa</div><div><span class="line-swatch country-swatch"></span> países</div><div><span class="line-swatch state-swatch"></span> estados</div><div><span class="dot-swatch"></span> LiDAR offshore</div><div><span class="diamond-swatch"></span> INMET</div><div>Preenchimento forte: &lt;5,5 km</div><div>Preenchimento leve: restante do domínio</div>';
const tooltip=document.getElementById('tooltip');function tip(e,text){const r=document.getElementById('map-wrap').getBoundingClientRect();tooltip.textContent=text;tooltip.style.left=(e.clientX-r.left+12)+'px';tooltip.style.top=(e.clientY-r.top+12)+'px';tooltip.style.display='block'}function hideTip(){tooltip.style.display='none'}
let vb={x:0,y:0,w:W,h:H},drag=null;function applyVB(){svg.setAttribute('viewBox',`${vb.x} ${vb.y} ${vb.w} ${vb.h}`)}svg.addEventListener('wheel',e=>{e.preventDefault();const f=e.deltaY>0?1.14:.86,nw=Math.min(W,Math.max(220,vb.w*f)),nh=nw*H/W,r=svg.getBoundingClientRect(),px=(e.clientX-r.left)/r.width,py=(e.clientY-r.top)/r.height;vb.x+=px*(vb.w-nw);vb.y+=py*(vb.h-nh);vb.w=nw;vb.h=nh;applyVB()},{passive:false});svg.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,vx:vb.x,vy:vb.y};svg.setPointerCapture(e.pointerId);svg.classList.add('dragging')});svg.addEventListener('pointermove',e=>{if(!drag)return;const r=svg.getBoundingClientRect();vb.x=drag.vx-(e.clientX-drag.x)*vb.w/r.width;vb.y=drag.vy-(e.clientY-drag.y)*vb.h/r.height;applyVB()});svg.addEventListener('pointerup',()=>{drag=null;svg.classList.remove('dragging')});document.getElementById('reset-map').onclick=()=>{vb={x:0,y:0,w:W,h:H};applyVB()};
</script>
</body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        default="results/report/mesh-comparison/assets/mesh_data.json",
    )
    parser.add_argument("--output", default="results/report/mesh-comparison")
    args = parser.parse_args()

    data_path = REPO_ROOT / args.data
    output_dir = REPO_ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(data_path.read_text(encoding="utf-8"))
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    branch = git_value("branch", "--show-current")
    commit = git_value("rev-parse", "HEAD")
    html = (
        HTML.replace("__DATA__", compact)
        .replace("__BUILT__", generated)
        .replace("__BRANCH__", branch)
        .replace("__COMMIT__", commit)
    )
    output = output_dir / "index.html"
    output.write_text(html, encoding="utf-8")
    preview = output_dir / "preview.png"

    manifest = {
        "generated_utc": generated,
        "analysis_branch": branch,
        "analysis_commit_base": commit,
        "working_tree_dirty": bool(git_value("status", "--porcelain")),
        "builder": "scripts/06_report/build_mesh_comparison.py",
        "data_preparer": "scripts/06_report/prepare_mesh_comparison_data.py",
        "context_enricher": "scripts/06_report/enrich_mesh_comparison_context.py",
        "data_asset": str(data_path.relative_to(REPO_ROOT)),
        "data_sha256": sha256(data_path),
        "html_sha256": sha256(output),
        "preview": str(preview.relative_to(REPO_ROOT)) if preview.exists() else None,
        "preview_sha256": sha256(preview) if preview.exists() else None,
        "mesh_hashes": {key: value["sha256"] for key, value in data["meshes"].items()},
        "generator_commit": data["generator"]["commit"],
        "cartographic_context": {
            "dataset": data["cartography"]["provenance"]["dataset"],
            "scale": data["cartography"]["provenance"]["scale"],
            "license": data["cartography"]["provenance"]["license"],
            "coastline_source": data["cartography"]["provenance"][
                "coastline_source"
            ],
            "country_boundaries_source": data["cartography"]["provenance"][
                "country_boundaries_source"
            ],
            "state_boundaries_source": data["cartography"]["provenance"][
                "state_boundaries_source"
            ],
            "browser_simplification": data["cartography"]["provenance"][
                "browser_simplification"
            ],
            "source_hashes": {
                "coastline": data["cartography"]["provenance"][
                    "coastline_hashes"
                ],
                "country_boundaries": data["cartography"]["provenance"][
                    "country_boundaries_hashes"
                ],
                "state_boundaries": data["cartography"]["provenance"][
                    "state_boundaries_hashes"
                ],
            },
        },
        "notes": [
            "Only CTL/EXP01, EXP02 and the MEQ-02A Oval are displayed.",
            "All percentages and mesh counts are measured; prior Oval percentages are retained only as validation references.",
        ],
    }
    manifest_path = output_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(output.relative_to(REPO_ROOT))
    print(manifest_path.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
