/* MPAS MEQ-Br technical report, layout v2 — client-side rendering.
   Every chart is drawn from the JSON embedded in the page (#report-data,
   #meteo-data); point series are loaded on demand from assets/series/*.js.
   Libraries: Plotly (basic bundle) and Leaflet, vendored under assets/vendor. */
(function () {
  'use strict';

  function parseJSON(id) {
    var node = document.getElementById(id);
    return node ? JSON.parse(node.textContent) : null;
  }
  var D = parseJSON('report-data') || {};
  var METEO = parseJSON('meteo-data') || { entries: [] };
  var C = D.colors || {};
  var ORDER = D.order || [];
  var SOURCES = ['ERA5'].concat(ORDER);
  var PERIOD_LABEL = { '2021': 'nov 2021', '2022': 'out 2022' };
  var SITE_OF_PERIOD = { '2021': 'P0', '2022': 'LPI' };
  var $ = function (id) { return document.getElementById(id); };

  // ---------- helpers ----------
  function fmt(v, d) {
    if (d === undefined) d = 2;
    if (v === null || v === undefined || !isFinite(v)) return '—';
    return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function esc(s) {
    return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function uniq(a) { return a.filter(function (v, i) { return a.indexOf(v) === i; }); }
  function num(v) { return (v === null || v === undefined || v === '') ? NaN : Number(v); }
  function truthy(v) { return v === true || v === 'True' || v === 'true' || v === 1; }
  function color(src) { return C[src] || '#555'; }
  function hexToRgb(h) { var n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  function paletteAt(name, t) {
    var stops = (D.palettes || {})[name];
    if (!stops) return '#ccc';
    t = Math.max(0, Math.min(1, t));
    for (var i = 1; i < stops.length; i++) {
      if (t <= stops[i].fraction) {
        var a = stops[i - 1], b = stops[i];
        var f = (t - a.fraction) / ((b.fraction - a.fraction) || 1);
        var ca = hexToRgb(a.colour), cb = hexToRgb(b.colour);
        return 'rgb(' + ca.map(function (x, k) { return Math.round(x + f * (cb[k] - x)); }).join(',') + ')';
      }
    }
    return stops[stops.length - 1].colour;
  }
  function textOn(t) { return Math.abs(t - 0.5) > 0.22 ? '#fff' : '#1a1a1a'; }
  function gradient(stops) {
    return 'linear-gradient(to right,' + stops.map(function (s) { return s.colour + ' ' + (s.fraction * 100) + '%'; }).join(',') + ')';
  }
  function select(id, options, value) {
    var s = $(id); if (!s) return;
    s.innerHTML = options.map(function (o) {
      var v = typeof o === 'object' ? o.value : o, l = typeof o === 'object' ? o.label : o;
      return '<option value="' + esc(v) + '"' + (String(v) === String(value) ? ' selected' : '') + '>' + esc(l) + '</option>';
    }).join('');
  }
  function segment(id, onChange) {
    var box = $(id); if (!box) return;
    box.addEventListener('click', function (ev) {
      var b = ev.target.closest('button'); if (!b) return;
      Array.prototype.forEach.call(box.querySelectorAll('button'), function (x) { x.classList.toggle('active', x === b); });
      onChange(b.dataset);
    });
  }
  function hoursSeq(t0, n) {
    var start = Date.parse(t0 + ':00Z'), out = new Array(n);
    for (var i = 0; i < n; i++) out[i] = new Date(start + i * 3600000).toISOString().slice(0, 16).replace('T', ' ');
    return out;
  }

  // ---------- Plotly defaults: journal style ----------
  var FONT = { family: 'Arial, Helvetica, sans-serif', size: 11, color: '#1a1a1a' };
  function axis(o) {
    return Object.assign({
      showline: true, linecolor: '#1a1a1a', linewidth: 0.8, ticks: 'outside', ticklen: 3,
      tickwidth: 0.8, tickcolor: '#1a1a1a', showgrid: false, zeroline: false, automargin: true,
      title: { font: { size: 11 } }
    }, o || {});
  }
  function layout(extra) {
    var base = {
      font: FONT, paper_bgcolor: '#fff', plot_bgcolor: '#fff',
      margin: { l: 56, r: 12, t: 12, b: 42 }, showlegend: false, hovermode: 'closest',
      hoverlabel: { font: { family: FONT.family, size: 11 }, bgcolor: '#fff', bordercolor: '#1a1a1a' },
      legend: { orientation: 'h', y: -0.22, x: 0, font: { size: 10 } },
      xaxis: axis(), yaxis: axis()
    };
    extra = extra || {};
    Object.keys(extra).forEach(function (k) {
      if (/^[xy]axis\d*$/.test(k)) base[k] = axis(extra[k]); else base[k] = extra[k];
    });
    return base;
  }
  var CONFIG = {
    displaylogo: false, responsive: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines', 'hoverCompareCartesian', 'hoverClosestCartesian'],
    toImageButtonOptions: { format: 'svg', filename: 'mpas_meqbr' }
  };
  function plot(id, traces, lay) {
    var node = $(id); if (!node) return;
    if (!window.Plotly) { node.innerHTML = '<div class="empty">Biblioteca de gráficos indisponível.</div>'; return; }
    if (!traces.length) { Plotly.purge(node); node.innerHTML = '<div class="empty">Sem dados para esta seleção.</div>'; return; }
    if (node.querySelector('.empty')) node.innerHTML = '';
    Plotly.react(node, traces, layout(lay), CONFIG);
  }
  function lineStyle(src) {
    if (src === 'OBS') return { color: '#000', width: 1.6 };
    if (src === 'ERA5') return { color: color('ERA5'), width: 1.3, dash: 'dash' };
    return { color: color(src), width: 1.1 };
  }
  function label(src) { return src === 'OBS' ? 'Observação' : src; }

  // ---------- navigation ----------
  function initNav() {
    var links = Array.prototype.slice.call(document.querySelectorAll('#chapter-nav a'));
    var sections = links.map(function (a) { return document.querySelector(a.getAttribute('href')); });
    function onScroll() {
      var y = window.scrollY + window.innerHeight * 0.3, current = 0;
      sections.forEach(function (s, i) { if (s && s.offsetTop <= y) current = i; });
      links.forEach(function (a, i) { a.classList.toggle('active', i === current); });
      var h = document.documentElement.scrollHeight - window.innerHeight;
      $('progress-bar').style.width = (h > 0 ? 100 * window.scrollY / h : 0) + '%';
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    document.addEventListener('click', function (ev) {
      var t = ev.target.closest('.tabs button');
      if (!t || !t.dataset.tab) return;
      var bar = t.parentNode;
      Array.prototype.forEach.call(bar.querySelectorAll('button'), function (b) {
        b.classList.toggle('active', b === t);
        var pane = $(b.dataset.tab); if (pane) pane.classList.toggle('active', b === t);
      });
      if (t.dataset.tab === 'fields-static' && fieldMap) setTimeout(function () { fieldMap.invalidateSize(); }, 30);
    });
  }

  // ======================================================================
  // 1 · Experiments and meshes
  // ======================================================================
  function initDesign() {
    var exps = {}; (D.experiments || []).forEach(function (e) { exps[e.id] = e; });
    var layoutTree = [
      ['CTL', 1, 1], ['EXP01', 1, 2], ['EXP02', 1, 3],
      ['EXP03', 2, 3],
      ['EXP04', 3, 2], ['EXP05', 3, 3], ['EXP06', 3, 4]
    ];
    var tree = $('design-tree'); if (!tree) return;
    var rowLabels = [[1, 'SST e fronteira'], [2, 'Geometria'], [3, 'Física da CLP']];
    var html = '';
    rowLabels.forEach(function (r) {
      if (r[0] > 1) html += '<div class="tree-row-label" style="grid-row:' + r[0] + ';grid-column:1">' + r[1] + '<br><small>a partir de EXP01</small></div>';
    });
    layoutTree.forEach(function (n) {
      var e = exps[n[0]]; if (!e) return;
      html += '<button type="button" class="node" data-exp="' + e.id + '" style="--c:' + color(e.id) + ';grid-row:' + n[1] + ';grid-column:' + n[2] + '">' +
        '<b>' + e.id + '</b>' + esc(e.short) + '<br><span class="mesh-tag">' + esc(e.mesh) + '</span></button>';
    });
    tree.innerHTML = html;
    function show(id) {
      var e = exps[id]; if (!e) return;
      Array.prototype.forEach.call(tree.querySelectorAll('.node'), function (b) { b.classList.toggle('active', b.dataset.exp === id); });
      var detail = '<p><b>' + e.id + '</b>' + (e.parent ? ' — muda em relação a <b>' + e.parent + '</b>' : ' — referência') + '. ' + esc(e.description) + '</p>' +
        '<p><span class="chip">malha ' + esc(e.mesh) + '</span><span class="chip">' + esc(e.n_cells) + ' células</span>' +
        '<span class="chip">' + esc(e.mpi_ranks) + ' ranks MPI</span><span class="chip">' + esc(e.status) + '</span></p>';
      if (e.id === 'EXP01' && D.sst_figure) detail += '<figure class="panel"><img src="' + D.sst_figure + '" alt="SST EXP01 − CTL" loading="lazy"><figcaption>SST média EXP01 − CTL, nov 2021: combina atualização diária e diferença do estado médio OISST × SST inicial do ERA5.</figcaption></figure>';
      $('exp-detail').innerHTML = detail;
    }
    tree.addEventListener('click', function (ev) { var b = ev.target.closest('.node'); if (b) show(b.dataset.exp); });
    show('CTL');

    // Meshes
    var meshes = D.meshes || [];
    var tabs = $('mesh-tabs');
    tabs.innerHTML = meshes.map(function (m, i) {
      return '<button type="button" class="' + (i === 0 ? 'active' : '') + '" data-mesh="' + i + '">' + esc(m.label) + '</button>';
    }).join('');
    function showMesh(i) {
      var m = meshes[i]; if (!m) return;
      Array.prototype.forEach.call(tabs.querySelectorAll('button'), function (b) { b.classList.toggle('active', Number(b.dataset.mesh) === i); });
      $('mesh-panel').innerHTML =
        '<div class="mesh-stats"><div><b>' + Number(m.n_cells).toLocaleString('pt-BR') + '</b>células</div>' +
        '<div><b>' + fmt(m.spacing_km, 1) + ' km</b>espaçamento no núcleo</div>' +
        (m.n_relaxation_cells ? '<div><b>' + Number(m.n_relaxation_cells).toLocaleString('pt-BR') + '</b>células de relaxação</div>' : '') +
        '<div><b>' + m.experiments.map(function (x) { return '<span class="chip" style="--c:' + color(x) + '"><i></i>' + x + '</span>'; }).join(' ') + '</b>experimentos</div></div>' +
        (m.figure ? '<img src="' + m.figure + '" alt="Malha ' + esc(m.name) + '" loading="lazy">' : '<div class="empty">Figura da malha não produzida.</div>') +
        '<figcaption><code>' + esc(m.name) + '</code>: espaçamento equivalente entre centros de célula (batlow; azul-escuro = menor). Pontos escuros = zona de relaxação lateral; círculo/quadrado = LiDARs; triângulos = estações INMET.</figcaption>';
      // Spacing-decay sub-view, only for meshes with a buffer (no CTL profile).
      var prof = (D.mesh_profile || []).filter(function (r) { return r.mesh === m.name; });
      $('mesh-view').hidden = !prof.length;
      if (!prof.length) meshView = 'mesh';
      Array.prototype.forEach.call($('mesh-view').querySelectorAll('button'), function (b) { b.classList.toggle('active', b.dataset.v === meshView); });
      $('mesh-panel').classList.toggle('show-profile', meshView === 'profile');
      $('mesh-profile-wrap').hidden = meshView !== 'profile';
      if (meshView === 'profile') renderMeshProfile(m, prof);
    }
    var meshView = 'mesh', currentMesh = 0;
    segment('mesh-view', function (d) { meshView = d.v; showMesh(currentMesh); });
    function renderMeshProfile(m, rows) {
      var c = color(m.experiments[m.experiments.length - 1]);
      var inner = rows.filter(function (r) { return r.kind === 'interior'; }).sort(function (a, b) { return a.dist_km - b.dist_km; });
      var relax = rows.filter(function (r) { return r.kind === 'relaxation'; });
      var theory = rows.filter(function (r) { return r.kind === 'theory'; });
      var marks = rows.filter(function (r) { return r.kind === 'marker'; });
      var xs = inner.map(function (r) { return r.dist_km; });
      var tr = [
        { type: 'scatter', mode: 'lines', x: xs, y: inner.map(function (r) { return r.p10_km; }), line: { width: 0 }, hoverinfo: 'skip', showlegend: false },
        { type: 'scatter', mode: 'lines', name: 'p10–p90', x: xs, y: inner.map(function (r) { return r.p90_km; }), fill: 'tonexty', fillcolor: 'rgba(120,120,120,0.22)', line: { width: 0 }, hoverinfo: 'skip' },
        { type: 'scatter', mode: 'lines', name: 'mediana', x: xs, y: inner.map(function (r) { return r.median_km; }), line: { color: c, width: 1.8 },
          customdata: inner.map(function (r) { return [r.n, r.p10_km, r.p90_km]; }),
          hovertemplate: '%{x:.0f} km: mediana %{y:.1f} km (p10 %{customdata[1]:.1f}, p90 %{customdata[2]:.1f}; n = %{customdata[0]})<extra></extra>' },
        { type: 'scatter', mode: 'markers', name: 'zona de relaxação', x: relax.map(function (r) { return r.dist_km; }), y: relax.map(function (r) { return r.median_km; }),
          marker: { symbol: 'diamond-open', size: 7, color: '#1a1a1a', line: { width: 1.2 } },
          customdata: relax.map(function (r) { return r.n; }), hovertemplate: 'relaxação, %{x:.0f} km: mediana %{y:.1f} km (n = %{customdata})<extra></extra>' },
        { type: 'scatter', mode: 'lines', name: 'perfil pedido', x: theory.map(function (r) { return r.dist_km; }), y: theory.map(function (r) { return r.theory_km; }),
          line: { color: '#1a1a1a', width: 1.1, dash: 'dash' }, hoverinfo: 'skip' }
      ];
      var LBL = { 'area of interest': 'borda da área de interesse', 'end of ramp': 'fim da rampa', 'LBC zone starts': 'início da zona de LBC', 'mesh edge': 'borda da malha' };
      var shapes = marks.map(function (r) { return { type: 'line', xref: 'x', yref: 'paper', x0: r.dist_km, x1: r.dist_km, y0: 0, y1: 1, line: { color: '#7a7a7a', width: 0.8, dash: 'dot' } }; });
      var ann = marks.map(function (r) { return { xref: 'x', yref: 'paper', x: r.dist_km, y: 1, text: LBL[r.marker] || r.marker, textangle: -90, xanchor: 'right', yanchor: 'top', showarrow: false, font: { size: 9, color: '#4a4a4a' } }; });
      plot('chart-mesh-profile', tr, { showlegend: true, legend: { orientation: 'h', y: -0.22, x: 0 }, shapes: shapes, annotations: ann,
        xaxis: { title: { text: 'distância à borda da área de interesse (km; negativa dentro)' } }, yaxis: { title: { text: 'espaçamento (km)' }, rangemode: 'tozero' } });
      var r0 = (D.mesh_profile_meta || {})[m.name] || {};
      $('mesh-profile-note').innerHTML = 'MPAS-Research <code>' + esc(String(r0.mpas_research_sha || '').slice(0, 8)) + '</code>.' +
        (truthy(r0.theory_reconstructed) ? ' Malha gerada antes de o código ser versionado: o perfil pedido foi reconstruído a partir dos parâmetros registrados no <code>domain.txt</code>.' : '');
    }
    tabs.addEventListener('click', function (ev) { var b = ev.target.closest('button'); if (b) { currentMesh = Number(b.dataset.mesh); showMesh(currentMesh); } });
    showMesh(0);

    // Periods
    var win = D.period_windows || [];
    // Two periods are a year apart: draw each on its own day-of-window axis.
    var tr2 = [];
    win.forEach(function (p) {
      var t0 = Date.parse(p.integration_start), d = function (s) { return (Date.parse(s) - t0) / 86400000; };
      var y = PERIOD_LABEL[p.id] + ' · ' + p.site;
      tr2.push({ type: 'bar', orientation: 'h', y: [y], base: [0], x: [d(p.analysis_start)], marker: { color: '#c8c8c8' },
        name: 'spin-up', hovertemplate: 'spin-up: ' + d(p.analysis_start) + ' dias<extra></extra>' });
      tr2.push({ type: 'bar', orientation: 'h', y: [y], base: [d(p.analysis_start)], x: [d(p.analysis_end) - d(p.analysis_start)], marker: { color: '#1a1a1a' },
        name: 'janela científica', hovertemplate: 'janela científica: ' + (d(p.analysis_end) - d(p.analysis_start)) + ' dias (' + p.analysis_start.slice(0, 10) + ' a ' + p.analysis_end.slice(0, 10) + ')<extra></extra>' });
    });
    plot('chart-periods', tr2, { barmode: 'overlay', xaxis: { title: { text: 'dias desde o início da integração' } }, yaxis: { autorange: 'reversed' }, margin: { l: 110, r: 12, t: 8, b: 40 } });

    // Cost
    var rt = (D.runtime || []).filter(function (r) { return ORDER.indexOf(r.experiment) >= 0; });
    var ranks = rt.map(function (r) { return num(r.mpi_ranks); }).filter(isFinite);
    if (ranks.length) $('cost-ranks').textContent = Math.min.apply(null, ranks) + ' a ' + Math.max.apply(null, ranks);
    function drawCost(mode) {
      var perCells = mode === 'cells';
      var costTr = ['2021', '2022'].map(function (p, k) {
        var rows = rt.filter(function (r) { return String(r.period) === p; });
        return { type: 'scatter', mode: 'markers', name: PERIOD_LABEL[p],
          x: rows.map(function (r) { return perCells ? r.core_hours_per_sim_hour / (r.n_cells / 1e5) : r.core_hours_per_sim_hour; }), y: rows.map(function (r) { return r.experiment; }),
          marker: { symbol: k ? 'square-open' : 'circle', size: 8, color: rows.map(function (r) { return color(r.experiment); }), line: { width: 1.4, color: rows.map(function (r) { return color(r.experiment); }) } },
          customdata: rows.map(function (r) { return [r.mpi_ranks, r.quality, Number(r.n_cells).toLocaleString('pt-BR')]; }),
          hovertemplate: '%{y} ' + PERIOD_LABEL[p] + ': %{x:.2f} ' + (perCells ? 'h-núcleo/h simulada por 10⁵ células' : 'h-núcleo/h simulada') +
            '<br>%{customdata[0]} ranks · %{customdata[2]} células · %{customdata[1]}<extra></extra>' };
      });
      plot('chart-cost', costTr, { showlegend: true, legend: { orientation: 'h', y: 1.12, x: 0 },
        xaxis: { title: { text: perCells ? 'horas-núcleo por hora simulada e por 10⁵ células' : 'horas-núcleo por hora simulada' }, rangemode: 'tozero' },
        yaxis: { categoryorder: 'array', categoryarray: ORDER.slice().reverse() }, margin: { l: 56, r: 12, t: 26, b: 40 } });
    }
    segment('cost-mode', function (d) { drawCost(d.c); });
    drawCost('hour');
  }

  // ======================================================================
  // Leaflet helpers
  // ======================================================================
  function baseMap(id, opts) {
    if (!window.L || !$(id)) { if ($(id)) $(id).innerHTML = '<div class="empty">Biblioteca de mapas indisponível.</div>'; return null; }
    var map = L.map(id, Object.assign({ crs: L.CRS.EPSG4326, zoomSnap: 0.25, zoomAnimation: false, attributionControl: false, minZoom: 2, maxZoom: 11 }, opts || {}));
    map.createPane('land'); map.getPane('land').style.zIndex = 250;
    map.createPane('lines'); map.getPane('lines').style.zIndex = 450;
    map.getPane('lines').style.pointerEvents = 'none';
    var g = D.geography && D.geography.layers;
    if (g) {
      if (g.land) L.geoJSON(g.land, { pane: 'land', interactive: false, style: { stroke: false, fillColor: '#ececec', fillOpacity: 1 } }).addTo(map);
      if (g.states) L.geoJSON(g.states, { pane: 'lines', interactive: false, style: { color: '#7a7a7a', weight: 0.6, dashArray: '3 2' } }).addTo(map);
      if (g.countries) L.geoJSON(g.countries, { pane: 'lines', interactive: false, style: { color: '#4a4a4a', weight: 0.9 } }).addTo(map);
      if (g.coastline) L.geoJSON(g.coastline, { pane: 'lines', interactive: false, style: { color: '#1a1a1a', weight: 0.9 } }).addTo(map);
    }
    // Graticule every 2°, labelled at the map edge.
    var grat = L.layerGroup().addTo(map);
    for (var lon = -64; lon <= -24; lon += 2) L.polyline([[-16, lon], [16, lon]], { pane: 'lines', color: '#b5b5b5', weight: 0.4, interactive: false }).addTo(grat);
    for (var lat = -16; lat <= 16; lat += 2) L.polyline([[lat, -64], [lat, -24]], { pane: 'lines', color: '#b5b5b5', weight: 0.4, interactive: false }).addTo(grat);
    L.control.scale({ imperial: false, position: 'bottomright' }).addTo(map);
    var Coord = L.Control.extend({ onAdd: function () { var d = L.DomUtil.create('div', 'leaflet-bar'); d.style.cssText = 'background:#fff;padding:2px 6px;font-size:11px;'; d.innerHTML = '—'; this._d = d; return d; } });
    var coord = new Coord({ position: 'bottomleft' }); coord.addTo(map);
    map.on('mousemove', function (e) {
      coord._d.innerHTML = Math.abs(e.latlng.lat).toFixed(2) + '°' + (e.latlng.lat < 0 ? 'S' : 'N') + ' · ' + Math.abs(e.latlng.lng).toFixed(2) + '°W';
    });
    return map;
  }

  // ======================================================================
  // 2 · Fields
  // ======================================================================
  var fieldMap = null;
  function initFields() {
    var entries = (METEO.entries || []).filter(function (e) { return e.available !== false && e.url; });
    var vars = METEO.variables || {};
    var rasters = entries.filter(function (e) { return e.kind === 'georaster'; });
    var varKeys = uniq(rasters.map(function (e) { return e.variable; }));
    var periods = uniq(rasters.map(function (e) { return String(e.period); })).sort();
    select('f-var', varKeys.map(function (k) { return { value: k, label: (vars[k] || {}).label || k }; }), varKeys[0]);
    select('f-period', periods.map(function (p) { return { value: p, label: PERIOD_LABEL[p] || p }; }), periods[0]);
    var ext = METEO.extent || [-46.5, -33.5, -7.5, 1.0];
    var bounds = [[ext[2], ext[0]], [ext[3], ext[1]]];
    fieldMap = baseMap('field-map');
    if (!fieldMap) return;
    fieldMap.fitBounds(bounds);
    var overlayA = null, overlayB = null, handle = null, handleX = null;

    function find(v, p, e) { return rasters.filter(function (r) { return r.variable === v && String(r.period) === p && r.experiment === e; })[0]; }
    function experimentsFor(v, p) { return ORDER.concat(['ERA5']).filter(function (e) { return find(v, p, e); }); }
    var mode = 'values', diffToken = 0;
    segment('f-mode', function (d) { mode = d.m; render(); });

    function clip() {
      if (!overlayB || !handle) return;
      var img = overlayB.getElement(); if (!img) return;
      var mapRect = $('field-map').getBoundingClientRect(), imgRect = img.getBoundingClientRect();
      var x = handleX === null ? mapRect.width / 2 : handleX;
      handle.style.left = x + 'px';
      var inset = Math.max(0, mapRect.left + x - imgRect.left);
      img.style.clipPath = 'inset(0 0 0 ' + inset + 'px)';
    }
    function ensureHandle(on) {
      var wrap = $('field-map');
      if (on && !handle) {
        handle = document.createElement('div'); handle.className = 'swipe-handle'; wrap.appendChild(handle);
        var drag = false;
        var move = function (ev) {
          if (!drag) return;
          var r = wrap.getBoundingClientRect(), cx = (ev.touches ? ev.touches[0].clientX : ev.clientX);
          handleX = Math.max(0, Math.min(r.width, cx - r.left)); clip(); ev.preventDefault();
        };
        handle.addEventListener('mousedown', function (ev) { drag = true; fieldMap.dragging.disable(); ev.stopPropagation(); });
        handle.addEventListener('touchstart', function (ev) { drag = true; fieldMap.dragging.disable(); ev.stopPropagation(); }, { passive: true });
        window.addEventListener('mousemove', move);
        window.addEventListener('touchmove', move, { passive: false });
        var up = function () { if (drag) { drag = false; fieldMap.dragging.enable(); } };
        window.addEventListener('mouseup', up); window.addEventListener('touchend', up);
      } else if (!on && handle) { handle.remove(); handle = null; handleX = null; }
    }
    fieldMap.on('move zoom resize viewreset', clip);

    function render() {
      var v = $('f-var').value, p = $('f-period').value;
      var avail = experimentsFor(v, p);
      var a = $('f-exp-a').value, b = $('f-exp-b').value;
      if (avail.indexOf(a) < 0) a = avail[0];
      if (avail.indexOf(b) < 0 || b === a) b = avail.filter(function (x) { return x !== a; })[0] || a;
      select('f-exp-a', avail, a);
      select('f-exp-b', avail.filter(function (x) { return x !== a; }), b);
      $('f-compare').disabled = mode === 'diff';
      if (mode === 'diff') { $('f-exp-b').disabled = avail.length < 2; renderDiff(v, p, a, b); return; }
      diffToken++;
      var compare = $('f-compare').checked && avail.length > 1;
      $('f-exp-b').disabled = !compare;
      var ea = find(v, p, a), eb = compare ? find(v, p, b) : null;
      if (overlayA) fieldMap.removeLayer(overlayA);
      if (overlayB) fieldMap.removeLayer(overlayB);
      overlayA = overlayB = null;
      if (ea) overlayA = L.imageOverlay(ea.url, bounds, { opacity: 1 }).addTo(fieldMap);
      if (eb) { overlayB = L.imageOverlay(eb.url, bounds, { opacity: 1 }).addTo(fieldMap); overlayB.on('load', clip); }
      ensureHandle(!!eb); setTimeout(clip, 0);
      $('field-labels').innerHTML = ea ? '<span>' + a + '</span>' + (eb ? '<span>' + b + '</span>' : '') : '';
      if (ea) {
        $('field-colorbar').innerHTML = '<span>' + fmt(ea.vmin, ea.vmax < 2 ? 2 : 1) + '</span><div class="bar" style="background:' + gradient(ea.colour_stops) + '"></div><span>' + fmt(ea.vmax, ea.vmax < 2 ? 2 : 1) + '</span><span>' + esc(ea.unit) + '</span>';
        $('field-caption').innerHTML = '<b>' + esc(ea.variable_label) + '</b> — ' + esc(a) + (eb ? ' (esquerda) × ' + esc(b) + ' (direita)' : '') + ', ' + (PERIOD_LABEL[p] || p) +
          '; média de ' + ea.n_hours + ' h (' + esc(ea.window_start) + ' a ' + esc(ea.window_end) + '). ' + esc(ea.limitation || '');
      }
    }
    // ---- A − B from the numeric twins (assets/interactive/values/*.js) ----
    function renderDiff(v, p, a, b) {
      var ea = find(v, p, a), eb = find(v, p, b), token = ++diffToken;
      if (overlayA) fieldMap.removeLayer(overlayA);
      if (overlayB) fieldMap.removeLayer(overlayB);
      overlayA = overlayB = null; ensureHandle(false);
      $('field-labels').innerHTML = ea && eb ? '<span>' + esc(a) + ' − ' + esc(b) + '</span>' : '';
      if (!ea || !eb || !ea.values || !eb.values || !ea.values.url || !eb.values.url) {
        $('field-colorbar').innerHTML = ''; $('field-caption').textContent = 'Valores numéricos indisponíveis para esta combinação.'; return;
      }
      $('field-caption').textContent = 'Carregando valores…';
      loadValues(ea.values, function (qa) {
        loadValues(eb.values, function (qb) {
          if (token !== diffToken) return;
          if (!qa || !qb) { $('field-caption').textContent = 'Falha ao carregar os valores numéricos.'; return; }
          var A = ea.values, B = eb.values, n = qa.length, d = new Float32Array(n), mags = [];
          for (var i = 0; i < n; i++) {
            if (qa[i] === A.nodata || qb[i] === B.nodata) { d[i] = NaN; continue; }
            d[i] = (A.offset + qa[i] * A.scale) - (B.offset + qb[i] * B.scale);
            mags.push(Math.abs(d[i]));
          }
          if (!mags.length) { $('field-caption').textContent = 'Sem área comum entre ' + a + ' e ' + b + '.'; return; }
          mags.sort(function (x, y) { return x - y; });
          var lim = mags[Math.min(mags.length - 1, Math.floor(0.99 * mags.length))] || 1e-6;
          var ny = A.shape[0], nx = A.shape[1], cv = document.createElement('canvas');
          cv.width = nx; cv.height = ny;
          var ctx = cv.getContext('2d'), img = ctx.createImageData(nx, ny), lut = vikLut();
          for (var k = 0; k < n; k++) {
            if (!isFinite(d[k])) continue;
            var t = Math.max(0, Math.min(255, Math.round(255 * (0.5 + 0.5 * d[k] / lim)))), c = lut[t];
            img.data[4 * k] = c[0]; img.data[4 * k + 1] = c[1]; img.data[4 * k + 2] = c[2]; img.data[4 * k + 3] = 240;
          }
          ctx.putImageData(img, 0, 0);
          overlayA = L.imageOverlay(cv.toDataURL('image/png'), bounds, { opacity: 1 }).addTo(fieldMap);
          var dec = lim < 2 ? 2 : (lim < 20 ? 1 : 0);
          $('field-colorbar').innerHTML = '<span>−' + fmt(lim, dec) + '</span><div class="bar" style="background:' + gradient((D.palettes || {}).vik || []) + '"></div><span>+' + fmt(lim, dec) + '</span><span>' + esc(ea.unit) + '</span>';
          $('field-caption').innerHTML = '<b>' + esc(ea.variable_label) + ': ' + esc(a) + ' − ' + esc(b) + '</b>, ' + (PERIOD_LABEL[p] || p) +
            '; médias de ' + ea.n_hours + ' h e ' + eb.n_hours + ' h (' + esc(ea.window_start) + ' a ' + esc(ea.window_end) + '). ' +
            'Escala divergente simétrica em ±p99 de |A − B| (vermelho = A maior). Diferença calculada célula a célula na grade de 0,04°; ' +
            (a === 'ERA5' || b === 'ERA5' ? 'o ERA5 (0,25°) entra pela célula ERA5 mais próxima, sem suavização. ' : '') +
            'Quantização dos valores: ' + fmt(A.scale, 4) + ' ' + esc(ea.unit) + '.';
        });
      });
    }
    ['f-var', 'f-period', 'f-exp-a', 'f-exp-b', 'f-compare'].forEach(function (id) { $(id).addEventListener('change', render); });
    render();

    // Derived diagnostics (pre-rendered maps/sections)
    var diag = entries.filter(function (e) { return e.kind === 'image' && e.variable !== 'resource_vs_era5'; });
    var products = uniq(diag.map(function (e) { return e.variable; }));
    select('d-product', products.map(function (k) { return { value: k, label: (vars[k] || {}).label || k }; }), products[0]);
    function renderDiag() {
      var pr = $('d-product').value;
      var rows = diag.filter(function (e) { return e.variable === pr; });
      var ps = uniq(rows.map(function (e) { return String(e.period); })).sort();
      var p = ps.indexOf($('d-period').value) >= 0 ? $('d-period').value : ps[0];
      select('d-period', ps.map(function (x) { return { value: x, label: PERIOD_LABEL[x] || x }; }), p);
      var ex = ORDER.filter(function (e) { return rows.some(function (r) { return r.experiment === e && String(r.period) === p; }); });
      var e = ex.indexOf($('d-exp').value) >= 0 ? $('d-exp').value : ex[0];
      select('d-exp', ex, e);
      var item = rows.filter(function (r) { return r.experiment === e && String(r.period) === p; })[0];
      if (item) {
        $('d-img').src = item.url; $('d-img').alt = item.variable_label + ' ' + e;
        $('d-caption').innerHTML = '<b>' + esc(item.variable_label) + ' — ' + esc(e) + ', ' + (PERIOD_LABEL[p] || p) + '.</b> ' + esc(item.caption || item.description || '');
      }
    }
    ['d-product', 'd-period', 'd-exp'].forEach(function (id) { $(id).addEventListener('change', renderDiag); });
    if (products.length) renderDiag();

    // Animations
    var anims = entries.filter(function (e) { return e.kind === 'animation'; });
    var aprods = uniq(anims.map(function (e) { return e.variable; }));
    select('a-product', aprods.map(function (k) { return { value: k, label: (vars[k] || {}).label || k }; }), aprods[0]);
    var va = $('a-video-a'), vb = $('a-video-b'), playing = false;
    function renderAnim() {
      var pr = $('a-product').value;
      var rows = anims.filter(function (e) { return e.variable === pr; });
      var ps = uniq(rows.map(function (e) { return String(e.period); })).sort();
      var p = ps.indexOf($('a-period').value) >= 0 ? $('a-period').value : ps[0];
      select('a-period', ps.map(function (x) { return { value: x, label: PERIOD_LABEL[x] || x }; }), p);
      var ex = ORDER.filter(function (e) { return rows.some(function (r) { return r.experiment === e && String(r.period) === p; }); });
      var a = ex.indexOf($('a-exp-a').value) >= 0 ? $('a-exp-a').value : ex[0];
      var b = ex.indexOf($('a-exp-b').value) >= 0 ? $('a-exp-b').value : (ex[1] || ex[0]);
      select('a-exp-a', ex, a); select('a-exp-b', ex, b);
      var ia = rows.filter(function (r) { return r.experiment === a && String(r.period) === p; })[0];
      var ib = rows.filter(function (r) { return r.experiment === b && String(r.period) === p; })[0];
      pause();
      if (ia) { va.src = ia.url; $('a-cap-a').innerHTML = '<b>' + a + '</b> · ' + esc(ia.variable_label) + (ia.days ? ' · ' + ia.days + ' dias' : ''); }
      if (ib) { vb.src = ib.url; $('a-cap-b').innerHTML = '<b>' + b + '</b> · ' + esc(ib.variable_label) + (ib.days ? ' · ' + ib.days + ' dias' : ''); }
      var notes = [ia, ib].filter(function (x) { return x && x.coverage_note; }).map(function (x) { return x.experiment + ': ' + x.coverage_note; });
      $('a-note').textContent = 'Os dois vídeos são sincronizados: reproduzir, pausar e a barra de tempo atuam nos dois. ' + notes.join(' ');
      setRate();
    }
    function setRate() { var r = Number($('a-rate').value); va.playbackRate = r; vb.playbackRate = r; }
    function pause() { va.pause(); vb.pause(); playing = false; $('a-play').textContent = '▶ reproduzir'; }
    $('a-play').addEventListener('click', function () {
      if (playing) { pause(); return; }
      vb.currentTime = Math.min(va.currentTime, vb.duration || va.currentTime);
      va.play(); vb.play(); playing = true; $('a-play').textContent = '❚❚ pausar';
    });
    va.addEventListener('timeupdate', function () {
      if (va.duration) $('a-seek').value = Math.round(1000 * va.currentTime / va.duration);
      if (vb.duration && Math.abs(vb.currentTime - va.currentTime) > 0.25 && va.currentTime <= vb.duration) vb.currentTime = va.currentTime;
    });
    va.addEventListener('ended', pause);
    $('a-seek').addEventListener('input', function () {
      var f = Number(this.value) / 1000;
      if (va.duration) va.currentTime = f * va.duration;
      if (vb.duration) vb.currentTime = Math.min(f * va.duration, vb.duration);
    });
    ['a-product', 'a-period', 'a-exp-a', 'a-exp-b'].forEach(function (id) { $(id).addEventListener('change', renderAnim); });
    $('a-rate').addEventListener('change', setRate);
    if (aprods.length) renderAnim();
  }

  // ======================================================================
  // 3 · Observation network
  // ======================================================================
  var seriesCache = {};
  var hiddenSources = {};
  var valueCache = {};
  function loadValues(v, cb) {
    var have = window.MEQ_FIELDS && window.MEQ_FIELDS[v.key];
    if (have) { cb(decodeValues(have)); return; }
    if (valueCache[v.key]) { valueCache[v.key].push(cb); return; }
    valueCache[v.key] = [cb];
    var s = document.createElement('script'); s.src = v.url;
    s.onload = function () { var raw = window.MEQ_FIELDS && window.MEQ_FIELDS[v.key]; var q = raw ? decodeValues(raw) : null; valueCache[v.key].forEach(function (f) { f(q); }); valueCache[v.key] = null; };
    s.onerror = function () { valueCache[v.key].forEach(function (f) { f(null); }); valueCache[v.key] = null; };
    document.head.appendChild(s);
  }
  function decodeValues(b64) {
    var bin = atob(b64), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Uint16Array(bytes.buffer);       // little-endian, as written
  }
  var VIK_LUT = null;
  function vikLut() {
    if (VIK_LUT) return VIK_LUT;
    VIK_LUT = [];
    for (var i = 0; i < 256; i++) {
      var c = paletteAt('vik', i / 255), m = /rgb\((\d+),(\d+),(\d+)\)/.exec(c);
      VIK_LUT.push(m ? [+m[1], +m[2], +m[3]] : hexToRgb(c));
    }
    return VIK_LUT;
  }
  function loadSeries(key, url, cb) {
    window.MEQ_SERIES = window.MEQ_SERIES || {};
    if (window.MEQ_SERIES[key]) { cb(window.MEQ_SERIES[key]); return; }
    if (seriesCache[key]) { seriesCache[key].push(cb); return; }
    seriesCache[key] = [cb];
    var s = document.createElement('script');
    s.src = url;
    s.onload = function () { var d = window.MEQ_SERIES[key]; seriesCache[key].forEach(function (f) { f(d); }); seriesCache[key] = null; };
    s.onerror = function () { seriesCache[key].forEach(function (f) { f(null); }); seriesCache[key] = null; };
    document.body.appendChild(s);
  }
  function icon(kind, selected) {
    var fill = selected ? '#1a1a1a' : '#fff', svg;
    if (kind === 'P0') svg = '<circle cx="9" cy="9" r="6.5" fill="' + fill + '" stroke="#1a1a1a" stroke-width="2"/>';
    else if (kind === 'LPI') svg = '<rect x="2.5" y="2.5" width="13" height="13" fill="' + fill + '" stroke="#1a1a1a" stroke-width="2"/>';
    else svg = '<polygon points="9,2 16,15.5 2,15.5" fill="' + (selected ? '#1a1a1a' : '#fff') + '" stroke="#1a1a1a" stroke-width="1.6"/>';
    return L.divIcon({ className: '', html: '<svg width="18" height="18" viewBox="0 0 18 18">' + svg + '</svg>', iconSize: [18, 18], iconAnchor: [9, 9] });
  }
  function initNetwork() {
    var map = baseMap('network-map');
    var points = D.points || [];
    var series = D.series || {};
    var state = { point: null };
    var markers = {};
    if (map) {
      map.fitBounds([[-9.5, -50], [3.5, -33]]);
      var domains = L.layerGroup();
      (D.meshes || []).forEach(function (m) {
        if (!m.extent || m.extent[0] === null) return;
        L.rectangle([[m.extent[1], m.extent[0]], [m.extent[3], m.extent[2]]], { color: '#1a1a1a', weight: 1, dashArray: '5 4', fill: false })
          .bindTooltip(m.name + ' (' + m.experiments.join(', ') + ')', { sticky: true }).addTo(domains);
      });
      var lidar = L.layerGroup().addTo(map), inmet = L.layerGroup().addTo(map);
      points.forEach(function (p) {
        var kind = p.network === 'LiDAR' ? p.point : 'INMET';
        var m = L.marker([p.lat, p.lon], { icon: icon(kind, false), keyboard: true, title: p.name })
          .bindTooltip(p.name, { direction: 'top', offset: [0, -8] })
          .on('click', function () { choose(p.point); });
        m.addTo(p.network === 'LiDAR' ? lidar : inmet);
        markers[p.point] = { marker: m, kind: kind };
      });
      L.control.layers(null, { 'LiDAR offshore': lidar, 'Estações INMET': inmet, 'Domínios das malhas': domains }, { collapsed: false, position: 'topright' }).addTo(map);
    }
    $('network-legend').innerHTML = '<span><span class="sym circle"></span>P0 — LiDAR flutuante (2021)</span><span><span class="sym"></span>LPI — LiDAR fixo (2022)</span>' +
      '<span><span class="sym tri"></span>Estação automática INMET (10 m)</span><span><span class="sym dash"></span>Domínio das malhas (camada opcional)</span>';

    // Source chips (shared by the three point charts)
    var chips = $('pt-sources');
    chips.innerHTML = ['OBS'].concat(SOURCES).map(function (s) {
      var c = s === 'OBS' ? '#000' : color(s);
      return '<button type="button" data-src="' + s + '" style="--c:' + c + '"><i' + (s === 'ERA5' ? ' style="background:repeating-linear-gradient(90deg,' + c + ' 0 3px,transparent 3px 5px)"' : '') + '></i>' + label(s) + '</button>';
    }).join('');
    chips.addEventListener('click', function (ev) {
      var b = ev.target.closest('button'); if (!b) return;
      hiddenSources[b.dataset.src] = !hiddenSources[b.dataset.src];
      b.classList.toggle('off', !!hiddenSources[b.dataset.src]);
      renderPoint();
    });

    function choose(pointId) {
      state.point = pointId;
      Object.keys(markers).forEach(function (k) { markers[k].marker.setIcon(icon(markers[k].kind, k === pointId)); });
      var p = points.filter(function (x) { return x.point === pointId; })[0];
      var keys = Object.keys(series).filter(function (k) { return series[k].point === pointId; });
      var periods = uniq(keys.map(function (k) { return String(series[k].period); })).sort();
      select('pt-period', periods.map(function (x) { return { value: x, label: PERIOD_LABEL[x] || x }; }), periods[0]);
      $('pt-title').textContent = p ? p.name : pointId;
      $('pt-meta').innerHTML = p ? (esc(p.instrument || p.network) + ' · ' + Math.abs(p.lat).toFixed(3) + '°S, ' + Math.abs(p.lon).toFixed(3) + '°W' +
        (p.quality_control ? '<br>QC: ' + esc(p.quality_control) : '')) : '';
      updateHeights();
    }
    function currentKey() {
      var p = points.filter(function (x) { return x.point === state.point; })[0];
      return p ? p.network + '_' + p.point + '_' + $('pt-period').value : null;
    }
    function updateHeights() {
      var key = currentKey(), s = series[key];
      var hs = s ? s.heights : [];
      var def = hs.indexOf('100') >= 0 ? '100' : hs[0];
      select('pt-height', hs.map(function (h) { return { value: h, label: h + ' m' }; }), def);
      renderPoint();
    }
    $('pt-period').addEventListener('change', updateHeights);
    $('pt-height').addEventListener('change', renderPoint);

    function renderPoint() {
      var key = currentKey(), meta = series[key];
      if (!meta) {
        ['chart-pt-series', 'chart-pt-diurnal', 'chart-pt-hist'].forEach(function (id) { plot(id, [], {}); });
        $('pt-metrics').innerHTML = ''; return;
      }
      var h = $('pt-height').value;
      loadSeries(key, meta.url, function (data) {
        if (!data || currentKey() !== key) return;
        var block = data.heights[h] || {};
        var x = hoursSeq(data.t0, data.n);
        var srcs = ['OBS'].concat(SOURCES).filter(function (s) { return block[s] && !hiddenSources[s]; });
        // order: models below, ERA5, then observation on top
        var drawOrder = srcs.filter(function (s) { return s !== 'OBS' && s !== 'ERA5'; }).concat(srcs.indexOf('ERA5') >= 0 ? ['ERA5'] : [], srcs.indexOf('OBS') >= 0 ? ['OBS'] : []);
        plot('chart-pt-series', drawOrder.map(function (s) {
          return { type: 'scatter', mode: 'lines', name: label(s), x: x, y: block[s], line: lineStyle(s), connectgaps: false,
            hovertemplate: label(s) + ': %{y:.2f} m s⁻¹<extra>%{x|%d/%m %H}h UTC</extra>' };
        }), { yaxis: { title: { text: 'vento a ' + h + ' m (m s⁻¹)' }, rangemode: 'tozero' }, xaxis: { type: 'date', tickformat: '%d/%m' }, hovermode: 'x unified', margin: { l: 52, r: 8, t: 8, b: 34 } });

        // Diurnal cycle over hours where the observation exists (paired).
        var obs = block.OBS || [];
        var t0h = new Date(Date.parse(data.t0 + ':00Z')).getUTCHours();
        var diurnal = drawOrder.map(function (s) {
          var sum = new Array(24).fill(0), cnt = new Array(24).fill(0), arr = block[s];
          for (var i = 0; i < arr.length; i++) {
            if (arr[i] === null || obs[i] === null || obs[i] === undefined) continue;
            var lh = ((t0h + i - 3) % 24 + 24) % 24; sum[lh] += arr[i]; cnt[lh]++;
          }
          return { type: 'scatter', mode: 'lines', name: label(s), x: Array.from({ length: 24 }, function (_, k) { return k; }),
            y: sum.map(function (v, k) { return cnt[k] ? v / cnt[k] : null; }), line: lineStyle(s),
            hovertemplate: label(s) + ' %{x}h: %{y:.2f}<extra></extra>' };
        });
        plot('chart-pt-diurnal', diurnal, { xaxis: { title: { text: 'hora local' }, tickvals: [0, 6, 12, 18, 23], range: [0, 23] }, yaxis: { title: { text: 'm s⁻¹' } }, margin: { l: 44, r: 6, t: 22, b: 38 },
          annotations: [{ text: '<b>Ciclo diurno médio</b>', xref: 'paper', yref: 'paper', x: 0, y: 1.1, showarrow: false, xanchor: 'left', font: { size: 11 } }] });

        // Frequency distribution (1 m s⁻¹ bins), paired hours.
        var maxv = 0; drawOrder.forEach(function (s) { block[s].forEach(function (v) { if (v !== null && v > maxv) maxv = v; }); });
        var nb = Math.ceil(maxv) + 1;
        var hist = drawOrder.map(function (s) {
          var c = new Array(nb).fill(0), n = 0, arr = block[s];
          for (var i = 0; i < arr.length; i++) { if (arr[i] === null || obs[i] === null || obs[i] === undefined) continue; c[Math.floor(arr[i])]++; n++; }
          return { type: 'scatter', mode: 'lines', line: Object.assign({ shape: 'hvh' }, lineStyle(s)), name: label(s),
            x: c.map(function (_, k) { return k + 0.5; }), y: c.map(function (v) { return n ? 100 * v / n : 0; }),
            hovertemplate: label(s) + ' %{x:.1f} m s⁻¹: %{y:.1f}%<extra></extra>' };
        });
        plot('chart-pt-hist', hist, { xaxis: { title: { text: 'm s⁻¹' } }, yaxis: { title: { text: '% das horas' } }, margin: { l: 44, r: 6, t: 22, b: 38 },
          annotations: [{ text: '<b>Distribuição</b>', xref: 'paper', yref: 'paper', x: 0, y: 1.1, showarrow: false, xanchor: 'left', font: { size: 11 } }] });
      });

      // Metrics for the selected unit
      var p = points.filter(function (x) { return x.point === state.point; })[0];
      var rows = (D.point_metrics || []).filter(function (r) {
        return r.point === state.point && String(r.period) === $('pt-period').value && String(r.height_m) === h;
      });
      var best = {}; ['rmse', 'r'].forEach(function (m) {
        var vals = rows.map(function (r) { return num(r[m]); }).filter(isFinite);
        best[m] = m === 'rmse' ? Math.min.apply(null, vals) : Math.max.apply(null, vals);
      });
      var babs = Math.min.apply(null, rows.map(function (r) { return Math.abs(num(r.bias)); }).filter(isFinite));
      $('pt-metrics').innerHTML = rows.length ? '<thead><tr><th>Fonte</th><th>N</th><th>Viés</th><th>RMSE</th><th>r</th><th>Skill vs ERA5</th></tr></thead><tbody>' +
        SOURCES.map(function (s) {
          var r = rows.filter(function (x) { return x.source === s; })[0]; if (!r) return '';
          var sk = num(r.skill_vs_era5);
          return '<tr><td><span class="chip" style="--c:' + color(s) + '"><i></i>' + s + '</span></td><td>' + r.n + '</td>' +
            '<td' + (Math.abs(num(r.bias)) === babs ? ' style="font-weight:700"' : '') + '>' + fmt(r.bias) + '</td>' +
            '<td' + (num(r.rmse) === best.rmse ? ' style="font-weight:700"' : '') + '>' + fmt(r.rmse) + '</td>' +
            '<td' + (num(r.r) === best.r ? ' style="font-weight:700"' : '') + '>' + fmt(r.r) + '</td>' +
            '<td>' + (s === 'ERA5' ? 'ref.' : isFinite(sk) ? fmt(sk) + (truthy(r.significant_vs_era5) ? '' : ' (ND)') : 'Não avaliado nesta altura') + '</td></tr>';
        }).join('') + '</tbody>' : '<tbody><tr><td>Sem métricas para esta seleção.</td></tr></tbody>';
    }
    var first = points.filter(function (p) { return p.point === 'P0'; })[0] || points[0];
    if (first) choose(first.point);
  }

  // ======================================================================
  // 4 · Validation scorecard
  // ======================================================================
  var METRIC_INFO = {
    rmse: { label: 'RMSE (m s⁻¹)', better: 'low', lo: 'rmse_lo', hi: 'rmse_hi' },
    bias: { label: 'Viés (m s⁻¹)', better: 'abs', lo: 'bias_lo', hi: 'bias_hi' },
    r: { label: 'Correlação', better: 'high', lo: 'r_lo', hi: 'r_hi' },
    skill_vs_era5: { label: 'Skill de Murphy vs ERA5', better: 'high', lo: 'skill_lo', hi: 'skill_hi' }
  };
  function initValidation() {
    var state = { metric: 'rmse', network: 'LiDAR', unit: null };
    var pm = D.point_metrics || [];
    function units() {
      var rows = pm.filter(function (r) { return r.network === state.network; });
      var keys = uniq(rows.map(function (r) { return [r.point, r.period, r.height_m].join('|'); }));
      var order = { P0: 0, LPI: 1 };
      keys.sort(function (a, b) {
        var A = a.split('|'), B = b.split('|');
        return (A[1] - B[1]) || ((order[A[0]] !== undefined ? order[A[0]] : 9) - (order[B[0]] !== undefined ? order[B[0]] : 9)) || A[0].localeCompare(B[0]) || (A[2] - B[2]);
      });
      return keys.map(function (k) {
        var p = k.split('|'), sub = rows.filter(function (r) { return r.point === p[0] && String(r.period) === p[1] && String(r.height_m) === p[2]; });
        return { key: k, point: p[0], period: p[1], height: p[2], name: sub[0].name, role: sub[0].selection_role, rows: sub };
      });
    }
    function value(r, m) { return r ? num(r[m]) : NaN; }
    function score(v, m) { return m === 'bias' ? Math.abs(v) : v; }

    function render() {
      var info = METRIC_INFO[state.metric], list = units();
      var head = '<thead><tr><th>Unidade observacional</th>' + SOURCES.map(function (s) {
        return '<th>' + s + '<i style="--c:' + color(s) + '"></i></th>';
      }).join('') + '</tr></thead>';
      var body = '', lastGroup = '';
      list.forEach(function (u) {
        var group = state.network === 'LiDAR' ? u.point + ' · ' + (PERIOD_LABEL[u.period] || u.period) : (PERIOD_LABEL[u.period] || u.period);
        if (group !== lastGroup) { body += '<tr class="group"><th colspan="' + (SOURCES.length + 1) + '">' + esc(group) + '</th></tr>'; lastGroup = group; }
        var vals = SOURCES.map(function (s) { return value(u.rows.filter(function (r) { return r.source === s; })[0], state.metric); });
        var finite = vals.map(function (v, i) { return state.metric === 'skill_vs_era5' && SOURCES[i] === 'ERA5' ? NaN : score(v, state.metric); }).filter(isFinite);
        var sorted = finite.slice().sort(function (a, b) { return a - b; });
        var med = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
        var spread = Math.max.apply(null, finite.map(function (v) { return Math.abs(v - med); }).concat([1e-9]));
        var bestV = info.better === 'high' ? Math.max.apply(null, finite) : Math.min.apply(null, finite);
        var rowLabel = state.network === 'LiDAR' ? u.height + ' m' : esc(u.name.replace(' (INMET A)', ''));
        body += '<tr data-key="' + u.key + '" class="' + (u.role === 'descriptive_only' ? 'descriptive ' : '') + (state.unit === u.key ? 'sel' : '') + '"><th>' + rowLabel + '</th>';
        SOURCES.forEach(function (s, i) {
          var v = vals[i], r = u.rows.filter(function (x) { return x.source === s; })[0];
          if (state.metric === 'skill_vs_era5' && s === 'ERA5') { body += '<td class="na">ref.</td>'; return; }
          if (!isFinite(v)) {
            body += '<td class="na">' + (state.metric === 'skill_vs_era5' ? 'Não avaliado nesta altura' : '—') + '</td>'; return;
          }
          var t;
          if (state.metric === 'skill_vs_era5') t = 0.5 - 0.5 * Math.max(-1, Math.min(1, v / 0.6));
          else {
            var d = (score(v, state.metric) - med) / spread; // −1 … 1
            if (info.better === 'high') d = -d;
            t = 0.5 + 0.38 * d;
          }
          var cls = [];
          if (score(v, state.metric) === bestV) cls.push('best');
          if (state.metric === 'skill_vs_era5' && r && !truthy(r.significant_vs_era5)) cls.push('ns');
          body += '<td class="' + cls.join(' ') + '" style="background:' + paletteAt('vik', t) + ';color:' + textOn(t) + '" title="' + s + ': ' + fmt(v, 3) + '">' + fmt(v, state.metric === 'r' || state.metric === 'skill_vs_era5' ? 2 : 2) + '</td>';
        });
        body += '</tr>';
      });
      $('scorecard').innerHTML = head + '<tbody>' + body + '</tbody>';
      var stops = (D.palettes || {}).vik || [];
      if (state.metric === 'skill_vs_era5') {
        $('sc-colorbar').innerHTML = '<span>perda −0,6</span><div class="bar" style="background:' + gradient(stops.slice().reverse().map(function (s) { return { fraction: 1 - s.fraction, colour: s.colour }; })) + '"></div><span>+0,6 ganho</span>';
        $('sc-caption').innerHTML = 'Skill = 1 − MSE<sub>fonte</sub>/MSE<sub>ERA5</sub> nas mesmas horas; avaliado só a 100 m (LiDAR) e 10 m (INMET). Hachura = diferença não detectável (IC95% inclui zero); contorno = maior skill da linha.';
      } else {
        $('sc-colorbar').innerHTML = '<span>melhor na linha</span><div class="bar" style="background:' + gradient(stops) + '"></div><span>pior na linha</span>';
        $('sc-caption').innerHTML = esc(info.label) + '. Cor relativa à mediana da linha' + (state.metric === 'bias' ? ' (pelo módulo do viés)' : '') + '; contorno = melhor valor da linha. ' +
          (state.network === 'LiDAR' ? 'P0/250 m é descritivo e fica fora dos testes de seleção.' : 'Estações INMET: vento a 10 m, célula MPAS mais próxima.');
      }
      if (!state.unit || !list.some(function (u) { return u.key === state.unit; })) {
        var def = list.filter(function (u) { return u.height === (state.network === 'LiDAR' ? '100' : u.height); })[0] || list[0];
        state.unit = def ? def.key : null;
        Array.prototype.forEach.call(document.querySelectorAll('#scorecard tbody tr[data-key]'), function (tr) { tr.classList.toggle('sel', tr.dataset.key === state.unit); });
      }
      renderUnit(list.filter(function (u) { return u.key === state.unit; })[0]);
    }
    function renderUnit(u) {
      if (!u) return;
      var info = METRIC_INFO[state.metric];
      var title = (state.network === 'LiDAR' ? u.point + ' · ' + (PERIOD_LABEL[u.period] || u.period) + ' · ' + u.height + ' m' : u.name + ' · ' + (PERIOD_LABEL[u.period] || u.period));
      $('forest-title').textContent = info.label + ' — ' + title;
      var srcs = SOURCES.filter(function (s) { return !(state.metric === 'skill_vs_era5' && s === 'ERA5'); });
      var rows = srcs.map(function (s) { return u.rows.filter(function (r) { return r.source === s; })[0]; });
      var ok = rows.map(function (r) { return r && isFinite(num(r[state.metric])); });
      var tr = [];
      srcs.forEach(function (s, i) {
        if (!ok[i]) return;
        var r = rows[i], v = num(r[state.metric]), lo = num(r[info.lo]), hi = num(r[info.hi]);
        var sig = state.metric !== 'skill_vs_era5' || truthy(r.significant_vs_era5);
        tr.push({ type: 'scatter', mode: 'markers', x: [v], y: [s], name: s,
          error_x: isFinite(lo) && isFinite(hi) ? { type: 'data', symmetric: false, array: [hi - v], arrayminus: [v - lo], color: color(s), thickness: 1.4, width: 4 } : undefined,
          marker: { size: 9, color: sig ? color(s) : '#fff', line: { color: color(s), width: 1.6 }, symbol: s === 'ERA5' ? 'diamond' : 'circle' },
          hovertemplate: s + ': %{x:.3f}' + (isFinite(lo) ? ' [' + fmt(lo, 3) + '; ' + fmt(hi, 3) + ']' : '') + '<extra></extra>' });
      });
      var era = u.rows.filter(function (r) { return r.source === 'ERA5'; })[0];
      var ref = state.metric === 'skill_vs_era5' || state.metric === 'bias' ? 0 : (era ? num(era[state.metric]) : NaN);
      var shapes = isFinite(ref) ? [{ type: 'line', xref: 'x', yref: 'paper', x0: ref, x1: ref, y0: 0, y1: 1, line: { color: '#8c8c8c', width: 1, dash: 'dot' } }] : [];
      plot('chart-forest', tr, { xaxis: { title: { text: info.label } }, yaxis: { categoryorder: 'array', categoryarray: srcs.slice().reverse() }, shapes: shapes, margin: { l: 56, r: 12, t: 8, b: 42 } });

      // Pairwise matrix (LiDAR only)
      var pw = (D.pairwise || []).filter(function (r) { return String(r.period) === u.period && r.site === u.point && String(r.height_m) === u.height; });
      if (!pw.length) {
        $('pairwise-grid').innerHTML = '<div class="empty">' + (state.network === 'INMET' ? 'Testes pareados entre experimentos são calculados para os LiDARs.' : 'Sem testes pareados nesta altura (P0/250 m é descritivo).') + '</div>';
        return;
      }
      var html = '<table><thead><tr><th></th>' + ORDER.map(function (b) { return '<th>' + b.replace('EXP', 'E') + '</th>'; }).join('') + '</tr></thead><tbody>';
      ORDER.forEach(function (a) {
        html += '<tr><th>' + a + '</th>';
        ORDER.forEach(function (b) {
          if (a === b) { html += '<td class="diag"></td>'; return; }
          var r = pw.filter(function (x) { return (x.experiment_a === a && x.experiment_b === b) || (x.experiment_a === b && x.experiment_b === a); })[0];
          if (!r) { html += '<td>—</td>'; return; }
          var tip = 'ΔMSE ' + r.experiment_a + '−' + r.experiment_b + ' = ' + fmt(r.delta_mse, 3) + ' [' + fmt(r.lo, 3) + '; ' + fmt(r.hi, 3) + ']';
          if (truthy(r.significant)) html += '<td style="background:' + color(r.better) + ';color:#fff" title="' + tip + '">' + r.better.replace('EXP', 'E') + '</td>';
          else html += '<td class="nd" title="' + tip + '">·</td>';
        });
        html += '</tr>';
      });
      $('pairwise-grid').innerHTML = html + '</tbody></table>';
    }
    segment('sc-metric', function (d) { state.metric = d.m; render(); });
    segment('sc-network', function (d) { state.network = d.n; state.unit = null; render(); });
    $('scorecard').addEventListener('click', function (ev) {
      var tr = ev.target.closest('tr[data-key]'); if (!tr) return;
      state.unit = tr.dataset.key;
      Array.prototype.forEach.call(document.querySelectorAll('#scorecard tbody tr[data-key]'), function (x) { x.classList.toggle('sel', x === tr); });
      renderUnit(units().filter(function (u) { return u.key === state.unit; })[0]);
    });
    render();

    // Profiles
    var profState = { site: 'P0', period: '2021' };
    function renderProfile() {
      var sm = (D.site_metrics || []).filter(function (r) { return r.site === profState.site && String(r.period) === profState.period; });
      var heights = uniq(sm.map(function (r) { return Number(r.height_m); })).sort(function (a, b) { return a - b; });
      var obsRows = heights.map(function (h) { return sm.filter(function (r) { return Number(r.height_m) === h; })[0]; });
      var tr = ORDER.map(function (e) {
        var rows = sm.filter(function (r) { return r.experiment === e; }).sort(function (a, b) { return a.height_m - b.height_m; });
        return { type: 'scatter', mode: 'lines+markers', name: e, x: rows.map(function (r) { return r.model_mean; }), y: rows.map(function (r) { return r.height_m; }),
          line: { color: color(e), width: 1.2 }, marker: { size: 5, color: color(e) }, hovertemplate: e + ' %{y} m: %{x:.2f} m s⁻¹<extra></extra>' };
      });
      var era = sm.filter(function (r) { return r.experiment === 'ERA5'; });
      if (era.length) tr.push({ type: 'scatter', mode: 'markers', name: 'ERA5', x: era.map(function (r) { return r.model_mean; }), y: era.map(function (r) { return r.height_m; }),
        marker: { symbol: 'diamond', size: 9, color: color('ERA5') }, hovertemplate: 'ERA5 %{y} m: %{x:.2f}<extra></extra>' });
      tr.push({ type: 'scatter', mode: 'lines+markers', name: 'Observação', x: obsRows.map(function (r) { return r.obs_mean; }), y: heights,
        line: { color: '#000', width: 2 }, marker: { size: 7, color: '#000' }, hovertemplate: 'LiDAR %{y} m: %{x:.2f}<extra></extra>' });
      plot('chart-profile', tr, { xaxis: { title: { text: 'velocidade média (m s⁻¹)' } }, yaxis: { title: { text: 'altura (m)' } },
        annotations: [{ text: '<b>a</b>', xref: 'paper', yref: 'paper', x: -0.12, y: 1.04, showarrow: false, font: { size: 13 } }] });

      var rk = (D.ranking || []).filter(function (r) { return r.site === profState.site && String(r.period) === profState.period; });
      var tr2 = ORDER.map(function (e, k) {
        var rows = rk.filter(function (r) { return r.experiment === e; }).sort(function (a, b) { return a.height_m - b.height_m; });
        var off = (k - (ORDER.length - 1) / 2) * 3;
        return { type: 'scatter', mode: 'markers', name: e, x: rows.map(function (r) { return r.rmse; }), y: rows.map(function (r) { return r.height_m + off; }),
          error_x: { type: 'data', symmetric: false, array: rows.map(function (r) { return r.rmse_hi - r.rmse; }), arrayminus: rows.map(function (r) { return r.rmse - r.rmse_lo; }), color: color(e), thickness: 1, width: 0 },
          marker: { size: 6, color: color(e) }, customdata: rows.map(function (r) { return r.height_m; }), hovertemplate: e + ' %{customdata} m: RMSE %{x:.2f}<extra></extra>' };
      });
      var era100 = sm.filter(function (r) { return r.experiment === 'ERA5'; });
      if (era100.length) tr2.push({ type: 'scatter', mode: 'markers', name: 'ERA5', x: era100.map(function (r) { return r.rmse; }), y: era100.map(function (r) { return r.height_m; }),
        marker: { symbol: 'diamond', size: 9, color: color('ERA5') }, hovertemplate: 'ERA5 100 m: %{x:.2f}<extra></extra>' });
      plot('chart-profile-rmse', tr2, { xaxis: { title: { text: 'RMSE (m s⁻¹)' } }, yaxis: { title: { text: 'altura (m)' }, tickvals: heights },
        annotations: [{ text: '<b>b</b>', xref: 'paper', yref: 'paper', x: -0.12, y: 1.04, showarrow: false, font: { size: 13 } }] });

      var tr3 = ORDER.map(function (e) {
        var rows = sm.filter(function (r) { return r.experiment === e; }).sort(function (a, b) { return a.height_m - b.height_m; });
        return { type: 'scatter', mode: 'lines+markers', name: e, x: rows.map(function (r) { return r.diurnal_amp_model; }), y: rows.map(function (r) { return r.height_m; }),
          line: { color: color(e), width: 1.2 }, marker: { size: 5, color: color(e) }, hovertemplate: e + ' %{y} m: %{x:.2f} m s⁻¹<extra></extra>' };
      });
      tr3.push({ type: 'scatter', mode: 'lines+markers', name: 'Observação', x: obsRows.map(function (r) { return r.diurnal_amp_obs; }), y: heights,
        line: { color: '#000', width: 2 }, marker: { size: 7, color: '#000' }, hovertemplate: 'LiDAR %{y} m: %{x:.2f}<extra></extra>' });
      plot('chart-diurnal-amp', tr3, { xaxis: { title: { text: 'amplitude diurna (m s⁻¹)' }, rangemode: 'tozero' }, yaxis: { title: { text: 'altura (m)' } },
        annotations: [{ text: '<b>c</b>', xref: 'paper', yref: 'paper', x: -0.12, y: 1.04, showarrow: false, font: { size: 13 } }] });
    }
    segment('prof-site', function (d) { var p = d.s.split('|'); profState.site = p[0]; profState.period = p[1]; renderProfile(); });
    renderProfile();

    // Network summary: three panels (bias, RMSE, r)
    var ns = D.network_summary || [];
    var metrics = [['bias', 'viés (m s⁻¹)'], ['rmse', 'RMSE (m s⁻¹)'], ['r', 'correlação']];
    var tr = [], lay = { yaxis: { categoryorder: 'array', categoryarray: SOURCES.slice().reverse() }, showlegend: true, legend: { orientation: 'h', y: 1.14, x: 0 }, margin: { l: 56, r: 12, t: 30, b: 42 } };
    metrics.forEach(function (m, k) {
      var ax = k ? String(k + 1) : '';
      lay['xaxis' + ax] = { domain: [k * 0.35, k * 0.35 + 0.3], title: { text: m[1] }, anchor: 'y' };
      ['LiDAR', 'INMET'].forEach(function (net, j) {
        var rows = ns.filter(function (r) { return r.network === net; });
        tr.push({ type: 'scatter', mode: 'markers', name: net === 'LiDAR' ? 'LiDAR offshore' : 'INMET 10 m', showlegend: k === 0, legendgroup: net, xaxis: 'x' + ax, yaxis: 'y',
          x: rows.map(function (r) { return r[m[0]]; }), y: rows.map(function (r) { return r.source; }),
          marker: { symbol: j ? 'triangle-up-open' : 'circle', size: 8, color: rows.map(function (r) { return color(r.source); }), line: { width: 1.5, color: rows.map(function (r) { return color(r.source); }) } },
          hovertemplate: '%{y} · ' + net + ': %{x:.2f}<extra></extra>' });
      });
    });
    plot('chart-network-summary', tr, lay);
  }

  // ======================================================================
  // 5 · Added value
  // ======================================================================
  function initAddedValue() {
    var av = (D.added_value || []).filter(function (r) { return r.source !== 'ERA5'; });
    var sites = [['P0', 'circle', -0.15], ['LPI', 'square', 0.15]];
    var yIndex = {}; ORDER.forEach(function (e, i) { yIndex[e] = ORDER.length - 1 - i; });
    var tr = sites.map(function (s) {
      var rows = av.filter(function (r) { return r.site === s[0]; });
      return { type: 'scatter', mode: 'markers', name: s[0] + (s[0] === 'P0' ? ' · nov 2021' : ' · out 2022'),
        x: rows.map(function (r) { return r.skill_vs_era5; }), y: rows.map(function (r) { return yIndex[r.source] + s[2]; }),
        error_x: { type: 'data', symmetric: false, array: rows.map(function (r) { return r.skill_hi - r.skill_vs_era5; }), arrayminus: rows.map(function (r) { return r.skill_vs_era5 - r.skill_lo; }),
          color: '#1a1a1a', thickness: 1, width: 3 },
        marker: { symbol: rows.map(function (r) { return truthy(r.significant) ? s[1] : s[1] + '-open'; }), size: 9,
          color: rows.map(function (r) { return color(r.source); }), line: { width: 1.6, color: rows.map(function (r) { return color(r.source); }) } },
        customdata: rows.map(function (r) { return [r.source, r.skill_lo, r.skill_hi, r.rmse]; }),
        hovertemplate: '%{customdata[0]} · ' + s[0] + ': %{x:.2f} [%{customdata[1]:.2f}; %{customdata[2]:.2f}]<br>RMSE %{customdata[3]:.2f} m s⁻¹<extra></extra>' };
    });
    var zero = [{ type: 'line', xref: 'x', yref: 'paper', x0: 0, x1: 0, y0: 0, y1: 1, line: { color: '#1a1a1a', width: 0.8 } }];
    plot('chart-skill-lidar', tr, { showlegend: true, legend: { orientation: 'h', y: 1.1, x: 0 }, shapes: zero, margin: { l: 56, r: 12, t: 28, b: 42 },
      xaxis: { title: { text: 'skill de Murphy vs ERA5' } }, yaxis: { tickvals: ORDER.map(function (e) { return yIndex[e]; }), ticktext: ORDER, range: [-0.6, ORDER.length - 0.4] } });

    var inm = (D.point_metrics || []).filter(function (r) { return r.network === 'INMET' && r.source !== 'ERA5'; });
    var tr2 = [{ type: 'scatter', mode: 'markers', name: 'estação × período',
      x: inm.map(function (r) { return r.skill_vs_era5; }),
      y: inm.map(function (r, i) { return yIndex[r.source] + ((i * 37) % 7 - 3) * 0.05; }),
      marker: { size: 7, symbol: inm.map(function (r) { return truthy(r.significant_vs_era5) ? 'triangle-up' : 'triangle-up-open'; }),
        color: inm.map(function (r) { return color(r.source); }), line: { width: 1.2, color: inm.map(function (r) { return color(r.source); }) } },
      customdata: inm.map(function (r) { return [r.source, r.name, PERIOD_LABEL[r.period] || r.period, r.skill_lo, r.skill_hi]; }),
      hovertemplate: '%{customdata[0]} · %{customdata[1]} (%{customdata[2]}): %{x:.2f} [%{customdata[3]:.2f}; %{customdata[4]:.2f}]<extra></extra>' }];
    var ns = (D.network_summary || []).filter(function (r) { return r.network === 'INMET' && r.source !== 'ERA5'; });
    tr2.push({ type: 'scatter', mode: 'markers', name: 'média da rede', x: ns.map(function (r) { return r.skill_vs_era5; }), y: ns.map(function (r) { return yIndex[r.source]; }),
      marker: { symbol: 'line-ns', size: 18, line: { width: 2.4, color: '#1a1a1a' } }, hovertemplate: '%{y}: média %{x:.2f}<extra></extra>' });
    plot('chart-skill-inmet', tr2, { showlegend: true, legend: { orientation: 'h', y: 1.1, x: 0 }, shapes: zero, margin: { l: 56, r: 12, t: 28, b: 42 },
      xaxis: { title: { text: 'skill de Murphy vs ERA5' } }, yaxis: { tickvals: ORDER.map(function (e) { return yIndex[e]; }), ticktext: ORDER, range: [-0.6, ORDER.length - 0.4] } });

    // Climatology
    var rep = D.representativeness || [], clim = D.climatology || [];
    var monthNo = { Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6, Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12 };
    var tr3 = [];
    rep.forEach(function (r, k) {
      var m = monthNo[r.month] || Number(r.month);
      var rows = clim.filter(function (c) { return c.site === r.site && Number(c.month) === m; });
      var xl = r.site + ' · ' + r.month + ' (' + r.sim_year + ')';
      tr3.push({ type: 'scatter', mode: 'markers', name: 'ERA5 1990–2020', showlegend: k === 0, x: rows.map(function (c, i) { return k + ((i * 53) % 11 - 5) * 0.025; }),
        y: rows.map(function (c) { return c.mean_speed_100; }), marker: { size: 6, color: '#a6a6a6' }, customdata: rows.map(function (c) { return c.year; }),
        hovertemplate: '%{customdata}: %{y:.2f} m s⁻¹<extra>' + xl + '</extra>' });
      tr3.push({ type: 'scatter', mode: 'markers', name: 'mês simulado', showlegend: k === 0, x: [k], y: [r.sim_mean_speed_100],
        marker: { symbol: 'diamond', size: 13, color: '#1a1a1a' },
        hovertemplate: 'simulado: %{y:.2f} m s⁻¹<br>percentil ' + fmt(r.percentile_speed, 0) + ', z = ' + fmt(r.z_score_speed, 2) + '<extra>' + xl + '</extra>' });
    });
    plot('chart-climatology', tr3, { showlegend: true, legend: { orientation: 'h', y: 1.1, x: 0 }, margin: { l: 56, r: 12, t: 28, b: 42 },
      xaxis: { tickvals: rep.map(function (_, k) { return k; }), ticktext: rep.map(function (r) { return r.site + ' · ' + r.month + ' ' + r.sim_year; }), range: [-0.5, rep.length - 0.5] },
      yaxis: { title: { text: 'vento médio mensal a 100 m (m s⁻¹)' } } });

    // Resource
    var res = D.resource || [];
    var tr4 = ORDER.map(function (e) {
      var rows = res.filter(function (r) { return r.experiment === e; });
      return { type: 'bar', name: e, x: rows.map(function (r) { return PERIOD_LABEL[r.period] || r.period; }), y: rows.map(function (r) { return r.domain_wpd_rel_diff_pct; }),
        marker: { color: color(e) }, customdata: rows.map(function (r) { return [r.domain_mean_speed_diff]; }),
        hovertemplate: e + ' %{x}: %{y:+.1f}% (Δvento %{customdata[0]:+.2f} m s⁻¹)<extra></extra>' };
    });
    plot('chart-resource', tr4, { barmode: 'group', bargap: 0.25, showlegend: true, legend: { orientation: 'h', y: 1.12, x: 0 }, margin: { l: 56, r: 12, t: 30, b: 36 },
      yaxis: { title: { text: 'Δ WPD relativa ao ERA5 (%)' }, zeroline: true, zerolinecolor: '#1a1a1a', zerolinewidth: 0.8 } });

    // Resource maps: MPAS (left) × ERA5 (right) on the shared MPAS colour scale.
    var rasters = (METEO.entries || []).filter(function (e) { return e.kind === 'georaster' && e.url && e.available !== false; });
    var refs = rasters.filter(function (e) { return e.experiment === 'ERA5'; });
    var vars = METEO.variables || {};
    var resVars = uniq(refs.map(function (e) { return e.variable; }));
    if (!resVars.length) { if ($('res-map')) $('res-map').innerHTML = '<div class="empty">Camadas ERA5 não produzidas.</div>'; return; }
    select('res-var', resVars.map(function (k) { return { value: k, label: (vars[k] || {}).label || k }; }), resVars[0]);
    var ext = METEO.extent || [-46.5, -33.5, -7.5, 1.0];
    var bounds = [[ext[2], ext[0]], [ext[3], ext[1]]];
    var resMap = baseMap('res-map');
    if (!resMap) return;
    resMap.fitBounds(bounds);
    var sw = swipe(resMap, 'res-map');
    function find(v, p, e) { return rasters.filter(function (r) { return r.variable === v && String(r.period) === p && r.experiment === e; })[0]; }
    function renderRes() {
      var v = $('res-var').value;
      var ex = ORDER.filter(function (e) { return rasters.some(function (r) { return r.variable === v && r.experiment === e; }); });
      var e = ex.indexOf($('res-exp').value) >= 0 ? $('res-exp').value : ex[0];
      select('res-exp', ex, e);
      var ps = uniq(refs.filter(function (r) { return r.variable === v && find(v, String(r.period), e); }).map(function (r) { return String(r.period); })).sort();
      var p = ps.indexOf($('res-period').value) >= 0 ? $('res-period').value : ps[0];
      select('res-period', ps.map(function (x) { return { value: x, label: PERIOD_LABEL[x] || x }; }), p);
      var ea = find(v, p, e), eb = find(v, p, 'ERA5');
      sw.show(ea, eb, bounds);
      $('res-labels').innerHTML = ea && eb ? '<span>' + esc(e) + '</span><span>ERA5</span>' : '';
      if (ea && eb) {
        var d = ea.vmax < 2 ? 2 : 1, sat = eb.saturation || {};
        $('res-colorbar').innerHTML = '<span>' + fmt(ea.vmin, d) + '</span><div class="bar" style="background:' + gradient(ea.colour_stops) + '"></div><span>' + fmt(ea.vmax, d) + '</span><span>' + esc(ea.unit) + '</span>';
        $('res-caption').innerHTML = '<b>' + esc(ea.variable_label) + ' — ' + esc(e) + ' (esquerda) × ERA5 (direita), ' + (PERIOD_LABEL[p] || p) + '.</b> Média de ' + ea.n_hours + ' h (' + esc(ea.window_start) + ' a ' + esc(ea.window_end) + '); ERA5 nas mesmas horas (' + eb.n_hours + ' h), resolução nativa ' + fmt(eb.native_resolution_deg, 2) + '°, célula mais próxima sem suavização. ' +
          'Escala dos campos MPAS: ' + fmt(100 * (sat.below_vmin || 0), 1) + '% das células ERA5 saturam abaixo e ' + fmt(100 * (sat.above_vmax || 0), 1) + '% acima.';
      }
    }
    ['res-var', 'res-exp', 'res-period'].forEach(function (id) { $(id).addEventListener('change', renderRes); });
    renderRes();
  }

  // A|B swipe over a Leaflet map: A fills the map, B is clipped left of the handle.
  function swipe(map, wrapId) {
    var wrap = $(wrapId), handle = null, handleX = null, A = null, B = null;
    function clip() {
      if (!B || !handle) return;
      var img = B.getElement(); if (!img) return;
      var mapRect = wrap.getBoundingClientRect(), imgRect = img.getBoundingClientRect();
      var x = handleX === null ? mapRect.width / 2 : handleX;
      handle.style.left = x + 'px';
      img.style.clipPath = 'inset(0 0 0 ' + Math.max(0, mapRect.left + x - imgRect.left) + 'px)';
    }
    function ensureHandle() {
      if (handle) return;
      handle = document.createElement('div'); handle.className = 'swipe-handle'; wrap.appendChild(handle);
      var drag = false;
      var move = function (ev) {
        if (!drag) return;
        var r = wrap.getBoundingClientRect(), cx = (ev.touches ? ev.touches[0].clientX : ev.clientX);
        handleX = Math.max(0, Math.min(r.width, cx - r.left)); clip(); ev.preventDefault();
      };
      handle.addEventListener('mousedown', function (ev) { drag = true; map.dragging.disable(); ev.stopPropagation(); });
      handle.addEventListener('touchstart', function (ev) { drag = true; map.dragging.disable(); ev.stopPropagation(); }, { passive: true });
      window.addEventListener('mousemove', move);
      window.addEventListener('touchmove', move, { passive: false });
      var up = function () { if (drag) { drag = false; map.dragging.enable(); } };
      window.addEventListener('mouseup', up); window.addEventListener('touchend', up);
    }
    map.on('move zoom resize viewreset', clip);
    return {
      show: function (ea, eb, bounds) {
        if (A) map.removeLayer(A); if (B) map.removeLayer(B); A = B = null;
        if (ea) A = L.imageOverlay(ea.url, bounds, { opacity: 1 }).addTo(map);
        if (eb) { B = L.imageOverlay(eb.url, bounds, { opacity: 1 }).addTo(map); B.on('load', clip); ensureHandle(); }
        setTimeout(clip, 0);
      }
    };
  }

  // ======================================================================
  // 6 · Physics
  // ======================================================================
  function initPhysics() {
    var at = D.attribution || [];
    var vars = [['mean_sst_K', 'SST (K)'], ['mean_lh_Wm2', 'calor latente (W m⁻²)'], ['mean_hpbl_m', 'altura da CLP (m)'], ['mean_speed100_ms', 'vento 100 m (m s⁻¹)']];
    var tr = [], lay = { yaxis: { categoryorder: 'array', categoryarray: ORDER.slice().reverse() }, showlegend: true, legend: { orientation: 'h', y: 1.16, x: 0 }, margin: { l: 56, r: 12, t: 30, b: 42 } };
    vars.forEach(function (v, k) {
      var ax = k ? String(k + 1) : '';
      lay['xaxis' + ax] = { domain: [k * 0.26, k * 0.26 + 0.21], title: { text: v[1] }, anchor: 'y', nticks: 4 };
      [['P0', 'circle'], ['LPI', 'square-open']].forEach(function (s) {
        var rows = at.filter(function (r) { return r.site === s[0] && isFinite(num(r[v[0]])); });
        tr.push({ type: 'scatter', mode: 'markers', name: s[0], legendgroup: s[0], showlegend: k === 0, xaxis: 'x' + ax, yaxis: 'y',
          x: rows.map(function (r) { return r[v[0]]; }), y: rows.map(function (r) { return r.experiment; }),
          marker: { symbol: s[1], size: 8, color: rows.map(function (r) { return color(r.experiment); }), line: { width: 1.4, color: rows.map(function (r) { return color(r.experiment); }) } },
          hovertemplate: '%{y} · ' + s[0] + ': %{x:.2f}<extra>' + v[1] + '</extra>' });
      });
    });
    plot('chart-attribution', tr, lay);

    var bd = D.boundary || [];
    plot('chart-boundary', [{ type: 'scatter', mode: 'lines+markers', x: bd.map(function (r) { return r.distance_bin + ' km'; }), y: bd.map(function (r) { return r.mean_abs_diff; }),
      line: { color: color('EXP02'), width: 1.6 }, marker: { size: 8, color: color('EXP02') }, customdata: bd.map(function (r) { return r.n_points; }),
      hovertemplate: '%{x}: %{y:.3f} m s⁻¹ (%{customdata} células)<extra></extra>' }],
      { xaxis: { title: { text: 'distância à zona de relaxação do EXP01' } }, yaxis: { title: { text: '|Δ vento 100 m| (m s⁻¹)' }, rangemode: 'tozero' } });

    // Contrast matrix
    var ct = D.contrasts || [];
    var cols = uniq(ct.map(function (r) { return r.period + '|' + r.site + '|' + r.height_m; }));
    var pairs = uniq(ct.map(function (r) { return r.experiment_a + '|' + r.experiment_b + '|' + r.hypothesis; }));
    var html = '<thead><tr><th>Contraste (A × B)</th>' + cols.map(function (c) { var p = c.split('|'); return '<th>' + p[1] + '<br>' + p[2] + ' m</th>'; }).join('') + '</tr></thead><tbody>';
    pairs.forEach(function (pr) {
      var p = pr.split('|');
      html += '<tr><th><b>' + p[0] + ' × ' + p[1] + '</b><br><small>' + esc(p[2]) + '</small></th>';
      cols.forEach(function (c) {
        var q = c.split('|');
        var r = ct.filter(function (x) { return x.experiment_a === p[0] && x.experiment_b === p[1] && String(x.period) === q[0] && x.site === q[1] && String(x.height_m) === q[2]; })[0];
        if (!r) { html += '<td>—</td>'; return; }
        var tip = 'ΔMSE = ' + fmt(r.delta_mse, 3) + ' [' + fmt(r.lo, 3) + '; ' + fmt(r.hi, 3) + '] · ' + r.verdict;
        if (truthy(r.significant) && (r.better === p[0] || r.better === p[1])) html += '<td style="background:' + color(r.better) + ';color:#fff" title="' + esc(tip) + '">' + r.better + '</td>';
        else html += '<td style="color:#8c8c8c;background:#f3f3f3" title="' + esc(tip) + '">ND</td>';
      });
      html += '</tr>';
    });
    $('contrast-matrix').innerHTML = html + '</tbody>';

    // EXP06 SST cycle
    var sc = (D.sst_site_cycle || []).filter(function (r) { return Number(r.cell_rank) === 0; });
    var tr2 = [];
    [['P0', 'solid'], ['LPI', 'dot']].forEach(function (s) {
      var rows = sc.filter(function (r) { return r.site === s[0]; }).sort(function (a, b) { return a.local_hour - b.local_hour; });
      if (!rows.length) return;
      tr2.push({ type: 'scatter', mode: 'lines', name: s[0] + ' · SST prescrita', x: rows.map(function (r) { return r.local_hour; }), y: rows.map(function (r) { return r.sst_K; }), line: { color: '#8c8c8c', width: 1.4, dash: s[1] } });
      tr2.push({ type: 'scatter', mode: 'lines', name: s[0] + ' · temperatura de pele', x: rows.map(function (r) { return r.local_hour; }), y: rows.map(function (r) { return r.skintemp_K; }), line: { color: color('EXP06'), width: 1.8, dash: s[1] } });
    });
    plot('chart-sst-cycle', tr2, { showlegend: true, legend: { orientation: 'h', y: 1.15, x: 0 }, margin: { l: 56, r: 12, t: 30, b: 40 }, hovermode: 'x unified',
      xaxis: { title: { text: 'hora local' }, tickvals: [0, 6, 12, 18, 23] }, yaxis: { title: { text: 'K' } } });

    // Cell sensitivity
    var cs = D.cell_sensitivity || [];
    var tr3 = [], lay3 = { showlegend: true, legend: { orientation: 'h', y: 1.15, x: 0 }, margin: { l: 56, r: 12, t: 30, b: 42 } };
    [['P0', ''], ['LPI', '2']].forEach(function (s, k) {
      lay3['xaxis' + s[1]] = { domain: [k * 0.53, k * 0.53 + 0.47], title: { text: s[0] + ': distância da célula ao LiDAR (km)' }, anchor: 'y' };
      ORDER.forEach(function (e) {
        var rows = cs.filter(function (r) { return r.site === s[0] && r.experiment === e; }).sort(function (a, b) { return a.distance_km - b.distance_km; });
        if (!rows.length) return;
        tr3.push({ type: 'scatter', mode: 'markers', name: e, legendgroup: e, showlegend: k === 0, xaxis: 'x' + s[1], yaxis: 'y',
          x: rows.map(function (r) { return r.distance_km; }), y: rows.map(function (r) { return r.rmse; }),
          marker: { size: 8, color: rows.map(function (r) { return Number(r.cell) === 0 ? color(e) : '#fff'; }), line: { width: 1.5, color: color(e) } }, hovertemplate: e + ' · %{x:.1f} km: RMSE %{y:.2f}<extra>' + s[0] + '</extra>' });
      });
    });
    lay3.yaxis = { title: { text: 'RMSE 100 m (m s⁻¹)' } };
    plot('chart-cells', tr3, lay3);
  }

  // ======================================================================
  // 7 · Synthesis
  // ======================================================================
  function initSynthesis() {
    var dm = D.decision || { rows: [], criteria: [] };
    var rows = {}; dm.rows.forEach(function (r) { rows[r.experiment] = r; });
    var defs = {
      pairwise: { v: function (r) { return r.pairwise_wins - r.pairwise_losses; }, txt: function (r) { return '+' + r.pairwise_wins + ' / −' + r.pairwise_losses; }, high: true },
      lidar_rmse_100: { v: function (r) { return r.lidar_rmse_100; }, txt: function (r) { return fmt(r.lidar_rmse_100); }, high: false },
      era5: { v: function (r) { return r.era5_gains - r.era5_losses; }, txt: function (r) { return r.era5_gains + ' de ' + r.era5_units + (r.era5_losses ? ' (−' + r.era5_losses + ')' : ''); }, high: true },
      inmet_rmse: { v: function (r) { return r.inmet_rmse; }, txt: function (r) { return fmt(r.inmet_rmse); }, high: false },
      cost: { v: function (r) { return r.cost; }, txt: function (r) { return fmt(r.cost, 2); }, high: false }
    };
    var html = '<thead><tr><th>Critério</th>' + ORDER.map(function (e) { return '<th>' + e + '<i style="--c:' + color(e) + '"></i></th>'; }).join('') + '</tr></thead><tbody>';
    dm.criteria.forEach(function (c) {
      var d = defs[c.key]; if (!d) return;
      var vals = ORDER.map(function (e) { return rows[e] ? num(d.v(rows[e])) : NaN; });
      var fin = vals.filter(isFinite), mn = Math.min.apply(null, fin), mx = Math.max.apply(null, fin);
      html += '<tr><th><abbr title="' + esc(c.help + ' Fonte: ' + c.source) + '">' + esc(c.label) + '</abbr></th>';
      ORDER.forEach(function (e, i) {
        var v = vals[i];
        if (!isFinite(v)) { html += '<td>—</td>'; return; }
        var good = mx > mn ? (d.high ? (v - mn) / (mx - mn) : (mx - v) / (mx - mn)) : 0.5;
        var t = 0.5 - 0.42 * good;
        html += '<td style="background:' + paletteAt('vik', t) + ';color:' + textOn(t) + '">' + d.txt(rows[e]) + '</td>';
      });
      html += '</tr>';
    });
    $('decision-matrix').innerHTML = html + '</tbody>';

    var sorted = ORDER.filter(function (e) { return rows[e]; }).sort(function (a, b) {
      return (rows[a].pairwise_wins - rows[a].pairwise_losses) - (rows[b].pairwise_wins - rows[b].pairwise_losses);
    });
    plot('chart-dominance', [
      { type: 'bar', orientation: 'h', name: 'vitórias', y: sorted, x: sorted.map(function (e) { return rows[e].pairwise_wins; }), marker: { color: sorted.map(color) },
        hovertemplate: '%{y}: %{x} vitórias significativas<extra></extra>' },
      { type: 'bar', orientation: 'h', name: 'derrotas', y: sorted, x: sorted.map(function (e) { return -rows[e].pairwise_losses; }), marker: { color: sorted.map(color), opacity: 0.35 },
        customdata: sorted.map(function (e) { return rows[e].pairwise_losses; }), hovertemplate: '%{y}: %{customdata} derrotas significativas<extra></extra>' }
    ], { barmode: 'relative', xaxis: { title: { text: '← derrotas · vitórias →' }, zeroline: true, zerolinecolor: '#1a1a1a', zerolinewidth: 1 }, margin: { l: 56, r: 12, t: 8, b: 42 } });

    var pts = ORDER.filter(function (e) { return rows[e] && isFinite(num(rows[e].cost)) && isFinite(num(rows[e].lidar_rmse_100)); });
    var TO = D.tradeoff || { rows: [] }, rel = {};
    TO.rows.forEach(function (r) { rel[r.experiment] = r; });
    function pct(v) { return (v >= 0 ? '+' : '') + fmt(100 * v, 0) + '%'; }
    if (isFinite(num(TO.x_divider))) {
      $('tradeoff-div').textContent = 'custo relativo ' + fmt(TO.x_divider, 2);
      $('tradeoff-range').textContent = pct(TO.partition_lo - 1) + ' e ' + pct(TO.partition_hi - 1) + ' de custo em relação ao CTL';
    }
    function drawTradeoff(mode) {
      if (mode !== 'rel') {
        plot('chart-tradeoff', [{ type: 'scatter', mode: 'markers+text', x: pts.map(function (e) { return rows[e].cost; }), y: pts.map(function (e) { return rows[e].lidar_rmse_100; }),
          text: pts, textposition: 'top center', textfont: { size: 10, color: pts.map(color) },
          marker: { size: 11, color: pts.map(color) }, hovertemplate: '%{text}: %{x:.2f} h-núcleo/h · RMSE %{y:.2f} m s⁻¹<extra></extra>' }],
          { xaxis: { title: { text: 'horas-núcleo por hora simulada' } }, yaxis: { title: { text: 'RMSE LiDAR médio a 100 m (m s⁻¹)' } } });
        return;
      }
      var pr = ORDER.filter(function (e) { return rel[e]; });
      var xs = pr.map(function (e) { return rel[e].cost_rel; }), ys = pr.map(function (e) { return rel[e].rmse_reduction_pct; });
      var xmin = Math.min.apply(null, xs), xmax = Math.max.apply(null, xs), ymin = Math.min.apply(null, ys), ymax = Math.max.apply(null, ys);
      var px = 0.08 * (xmax - xmin || 1), py = 0.15 * (ymax - ymin || 1);
      var X0 = xmin - px, X1 = xmax + px, Y0 = Math.min(ymin, 0) - py, Y1 = Math.max(ymax, 0) + py, xd = TO.x_divider;
      var q = function (x, y, t, xa, ya) { return { x: x, y: y, xref: 'x', yref: 'y', text: t, showarrow: false, xanchor: xa, yanchor: ya, font: { size: 10, color: '#7a7a7a' } }; };
      plot('chart-tradeoff', [{ type: 'scatter', mode: 'markers+text', x: xs, y: ys, text: pr, textposition: 'top center', textfont: { size: 10, color: pr.map(color) },
        marker: { size: 11, color: pr.map(color) }, hovertemplate: '%{text}: custo ×%{x:.2f} do CTL · RMSE %{y:+.1f}% vs CTL<extra></extra>' }],
        { shapes: [
            { type: 'line', x0: X0, x1: X1, y0: 0, y1: 0, line: { color: '#1a1a1a', width: 0.8 } },
            { type: 'line', x0: xd, x1: xd, y0: Y0, y1: Y1, line: { color: '#1a1a1a', width: 0.8, dash: 'dot' } }],
          annotations: [q(X0, Y1, 'bons e baratos', 'left', 'top'), q(X1, Y1, 'bons e caros', 'right', 'top'),
            q(X0, Y0, 'ruins e baratos', 'left', 'bottom'), q(X1, Y0, 'ruins e caros', 'right', 'bottom')],
          xaxis: { title: { text: 'custo relativo ao CTL (horas-núcleo por hora simulada)' }, range: [X0, X1] },
          yaxis: { title: { text: 'redução do RMSE a 100 m vs CTL (%)' }, range: [Y0, Y1] } });
    }
    segment('tradeoff-mode', function (d) { drawTradeoff(d.t); });
    drawTradeoff('abs');

    // What counts as a win: totals always come from the decision matrix.
    var wr = ORDER.filter(function (e) { return rows[e]; });
    if (wr.length) {
      $('wins-n').textContent = uniq(wr.map(function (e) { return rows[e].pairwise_total; })).join(', ');
      $('wins-totals').textContent = wr.map(function (e) { return e + ' ' + rows[e].pairwise_wins + '/' + rows[e].pairwise_losses; }).join(' · ');
    }
  }

  function safe(fn, name) {
    try { fn(); } catch (err) { if (window.console) console.error('[report] ' + name, err); }
  }
  function boot() {
    safe(initNav, 'nav');
    safe(initDesign, 'design');
    safe(initFields, 'fields');
    safe(initNetwork, 'network');
    safe(initValidation, 'validation');
    safe(initAddedValue, 'added value');
    safe(initPhysics, 'physics');
    safe(initSynthesis, 'synthesis');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
