#!/usr/bin/env python3
"""Panel web de alertas de JarvisCAN.

Sirve una pagina para un usuario de prueba: muestra la regla detectada, el
mensaje y reproduce el audio de cada alerta. No usa microfono ni STT.
"""
import argparse
import json
import os
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data"

RULE_LABELS = {
    "engine_temp": "Temperatura del motor",
    "coolant_level": "Nivel de refrigerante",
    "tire_pressure": "Presión de neumáticos",
    "oil_level": "Nivel de aceite",
    "dtc": "Códigos de falla",
    "overspeed": "Exceso de velocidad",
}

INDEX_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JarvisCAN · Alertas por voz</title>
<link rel="icon" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCA2NCI+PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9IjY0IiByeD0iMTQiIGZpbGw9IiMyOWI2ZjYiLz48dGV4dCB4PSIzMiIgeT0iNDUiIGZvbnQtZmFtaWx5PSJzYW5zLXNlcmlmIiBmb250LXNpemU9IjM4IiBmb250LXdlaWdodD0iYm9sZCIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZmlsbD0iIzA0MTAxOCI+SjwvdGV4dD48L3N2Zz4=">
<style>
  :root { color-scheme: dark; --bg:#060a10; --panel:#0b1620; --card:#0d1b27;
          --line:#1b3a4d; --text:#eaf6ff; --muted:#8fb3c9; --accent:#29b6f6;
          --ok:#38d39f; --warn:#ffb74d; --danger:#ff6b6b; }
  * { box-sizing:border-box; }
  html { scroll-behavior:smooth; }
  body { margin:0; min-height:100vh; color:var(--text);
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    background:
      radial-gradient(900px 500px at 12% -10%, #12354d 0%, transparent 60%),
      radial-gradient(700px 420px at 95% 0%, #0d3a33 0%, transparent 55%),
      var(--bg);
    overflow-x:hidden; }
  body::before { content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
    background-image:linear-gradient(rgba(41,182,246,.045) 1px, transparent 1px),
                     linear-gradient(90deg, rgba(41,182,246,.045) 1px, transparent 1px);
    background-size:46px 46px;
    mask-image:radial-gradient(circle at 50% 0%, #000 0%, transparent 72%);
    -webkit-mask-image:radial-gradient(circle at 50% 0%, #000 0%, transparent 72%); }
  body::after { content:""; position:fixed; inset:auto -10% -30% -10%; height:55vh; pointer-events:none; z-index:0;
    background:radial-gradient(ellipse at 50% 50%, rgba(41,182,246,.10), transparent 60%); filter:blur(40px); }
  header, main { position:relative; z-index:1; width:min(94vw, 1120px); margin:0 auto; }
  header { padding:26px 0 8px; display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap; }
  .brand { display:flex; align-items:center; gap:12px; }
  .brand-mark { width:44px; height:44px; border-radius:14px; display:grid; place-items:center;
    color:#041018; background:linear-gradient(135deg,#29b6f6,#38d39f);
    box-shadow:0 0 26px -6px #29b6f6; font-size:1.35rem; font-weight:900; }
  h1 { margin:0; font-size:1.85rem; letter-spacing:.02em; }
  .sub { margin:3px 0 0; color:var(--muted); font-size:.9rem; }
  .pill { padding:8px 13px; border-radius:999px; font-size:.78rem; font-weight:800;
    background:#17384d; color:#cfeaff; white-space:nowrap; display:inline-flex; align-items:center; gap:8px;
    border:1px solid #1f4a63; }
  .pill .dot { width:8px; height:8px; border-radius:50%; background:#8fb3c9; }
  .pill.ok { background:#0e352a; color:#9df3d0; border-color:#1b5c47; }
  .pill.ok .dot { background:var(--ok); box-shadow:0 0 10px var(--ok); animation:pulse 1.8s infinite; }
  .pill.off { background:#3a1d20; color:#ffb4b4; border-color:#6b2b31; }
  .pill.off .dot { background:#ff6b6b; box-shadow:0 0 10px #ff6b6b; }
  main { padding:8px 0 40px; }
  .card { background:linear-gradient(180deg,#0d1b28,var(--card)); border:1px solid var(--line);
    border-radius:18px; padding:18px; margin:12px 0; box-shadow:0 14px 34px #00000040; }
  .hero { display:flex; align-items:center; justify-content:space-between; gap:22px; flex-wrap:wrap;
    background:linear-gradient(120deg,#0b2233 0%,#0c1b27 55%,#0b2622 100%); border-color:#21506a; }
  .hero-copy { flex:1 1 520px; }
  .hero-side { display:flex; flex-direction:column; align-items:flex-end; gap:12px; }
  .hero-visual { width:150px; height:150px; display:grid; place-items:center; }
  .radar { width:140px; height:140px; border-radius:50%; border:1px solid #1d5a77; position:relative;
    background:radial-gradient(circle, rgba(41,182,246,.14), transparent 68%);
    box-shadow:0 0 40px -10px #29b6f6 inset, 0 0 30px -12px #29b6f6; }
  .radar::before, .radar::after { content:""; position:absolute; border-radius:50%;
    border:1px solid rgba(41,182,246,.28); inset:22%; }
  .radar::after { inset:44%; border-color:rgba(56,211,159,.45); }
  .radar i { position:absolute; top:50%; left:50%; width:50%; height:2px;
    background:linear-gradient(90deg,#38d39f,rgba(56,211,159,0));
    transform-origin:0 50%; animation:sweep 3.4s linear infinite; }
  .radar i::after { content:""; position:absolute; right:-3px; top:-3px; width:8px; height:8px;
    border-radius:50%; background:#38d39f; box-shadow:0 0 12px #38d39f; }
  .hero h2 { margin:8px 0 6px; font-size:1.45rem; line-height:1.25; }
  .hero h2 span { color:#9fe4ff; }
  .hero p { margin:0; color:#a9c6d8; font-size:.9rem; line-height:1.55; max-width:62ch; }
  .live { display:inline-flex; align-items:center; gap:8px; font-size:.68rem; font-weight:900;
    letter-spacing:.13em; color:#8df0c8; text-transform:uppercase; }
  .live i { width:8px; height:8px; border-radius:50%; background:var(--ok);
    box-shadow:0 0 12px var(--ok); animation:pulse 1.6s infinite; }
  .hero-badges { display:flex; gap:8px; flex-wrap:wrap; }
  .hero-badges span { padding:8px 11px; border-radius:10px; background:#0b1f2d; border:1px solid #1d4055;
    color:#b9dcef; font-size:.76rem; font-weight:700; white-space:nowrap; }
  .toolbar { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
  button { border:0; border-radius:12px; padding:12px 17px; font-weight:800; cursor:pointer;
    background:linear-gradient(135deg,#29b6f6,#38d39f); color:#041018; font-size:.93rem;
    box-shadow:0 8px 20px -8px #29b6f6; transition:transform .15s, box-shadow .15s; }
  button:hover { transform:translateY(-1px); box-shadow:0 12px 24px -8px #29b6f6; }
  button.secondary { background:#17384d; color:#cfeaff; box-shadow:none; border:1px solid #245a76; }
  button.small { padding:8px 12px; font-size:.8rem; }
  button:active { transform:scale(.985); }
  #status { color:#9ad8ff; font-size:.88rem; flex:1; min-width:200px; }
  .eq { display:flex; align-items:flex-end; gap:3px; height:22px; width:34px; opacity:.45; }
  .eq span { width:4px; border-radius:2px; background:linear-gradient(180deg,#38d39f,#29b6f6);
    height:6px; }
  body.playing .eq { opacity:1; }
  body.playing .eq span { animation:eq .7s ease-in-out infinite alternate; }
  body.playing .eq span:nth-child(2){ animation-delay:.12s; }
  body.playing .eq span:nth-child(3){ animation-delay:.24s; }
  body.playing .eq span:nth-child(4){ animation-delay:.36s; }
  body.playing .eq span:nth-child(5){ animation-delay:.48s; }
  .section-head { display:flex; align-items:flex-end; justify-content:space-between; gap:14px;
    margin:20px 2px 10px; flex-wrap:wrap; }
  .section-head h2 { margin:0; font-size:1.3rem; }
  .section-head p { margin:4px 0 0; color:var(--muted); font-size:.84rem; }
  .badge { padding:6px 10px; border-radius:999px; background:#0f2c3d; border:1px solid #1e4a61;
    color:#9fe4ff; font-size:.72rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
  .rules-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
  .rule-card { position:relative; overflow:hidden; min-height:196px; padding:16px;
    background:linear-gradient(160deg,#0e2130,#0a141f); border:1px solid #1b3b50;
    border-radius:16px; box-shadow:0 10px 26px #00000030;
    transition:transform .2s, border-color .2s, box-shadow .2s; }
  .rule-card::before { content:""; position:absolute; inset:0 0 auto 0; height:3px;
    background:linear-gradient(90deg,var(--accent),transparent 78%); }
  .rule-card:hover { transform:translateY(-3px); border-color:var(--accent);
    box-shadow:0 18px 36px #00000055, 0 0 30px -14px var(--accent); }
  .rule-top { display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .rule-icon { width:42px; height:42px; border-radius:12px; display:grid; place-items:center;
    color:var(--accent); background:#0a1c28; border:1px solid #1b3b50; }
  .rule-icon svg { width:24px; height:24px; }
  .rule-state { font-size:.64rem; font-weight:900; letter-spacing:.09em; text-transform:uppercase;
    color:#8fb3c9; background:#0b202d; border:1px solid #1b3b50; padding:5px 8px; border-radius:999px; }
  .rule-card h3 { margin:13px 0 5px; font-size:1.02rem; line-height:1.25; }
  .rule-detail { margin:0; color:#a9c6d8; font-size:.79rem; line-height:1.45; min-height:44px; }
  .rule-chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:11px; }
  .rule-chips span { font-size:.68rem; font-weight:800; color:var(--accent);
    background:#0a1a24; border:1px solid #1b3b50; padding:4px 7px; border-radius:7px; white-space:nowrap; }
  .rule-foot { display:flex; justify-content:space-between; gap:8px; margin-top:13px; padding-top:9px;
    border-top:1px solid #162f41; color:#6f95aa; font-size:.7rem; }
  .rule-foot [data-last] { text-align:right; }
  .rule-card.fired { border-color:var(--accent); animation:fire 1.15s ease-out 4; }
  .rule-card.fired .rule-state { color:var(--accent); border-color:var(--accent); background:#0a1a24; }
  .rule-card.fired .rule-icon { box-shadow:0 0 22px -6px var(--accent); }
  .latest { border-color:#2a6b8d; border-left:4px solid var(--accent, #2a6b8d);
    background:linear-gradient(135deg,#0d2637,#0d1824); }
  .latest-head { display:flex; align-items:center; justify-content:space-between; gap:12px; }
  .rule { display:inline-flex; align-items:center; gap:6px; padding:5px 9px; border-radius:999px;
    background:#123b52; color:var(--accent, #9fe4ff); font-size:.74rem; font-weight:800;
    text-transform:uppercase; letter-spacing:.05em; }
  .rule-dot { width:6px; height:6px; border-radius:50%; background:var(--accent, #9fe4ff);
    display:inline-block; box-shadow:0 0 7px var(--accent, #9fe4ff); }
  time { color:var(--muted); font-size:.78rem; }
  .message { margin:12px 0 0; line-height:1.55; font-size:1.04rem; }
  #latest-play { margin-top:12px; }
  .eyebrow { color:var(--muted); text-transform:uppercase; letter-spacing:.13em; font-size:.68rem;
    font-weight:800; margin-bottom:8px; }
  .feed-head { display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
  h2 { margin:0 0 10px; font-size:1.08rem; }
  #count { color:var(--muted); font-size:.78rem; }
  #list { list-style:none; margin:0; padding:0; }
  #list li { padding:14px 0; border-top:1px solid #173247; }
  #list li:first-child { border-top:0; }
  .item-top { display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .item-top .message { font-size:.94rem; margin:8px 0 0; color:#d8edff; }
  .empty { color:var(--muted); font-size:.92rem; padding:8px 0 4px; }
  .hint { color:#6f95aa; font-size:.8rem; line-height:1.55; margin:16px 2px 0; }
  @keyframes pulse { 0%,100%{ opacity:1; transform:scale(1); } 50%{ opacity:.55; transform:scale(.86); } }
  @keyframes fire { 0%{ box-shadow:0 0 0 0 var(--accent); } 100%{ box-shadow:0 0 0 16px transparent; } }
  @keyframes eq { from{ height:5px; } to{ height:21px; } }
  @keyframes sweep { to { transform:rotate(360deg); } }
  @media (max-width:900px) {
    .rules-grid { grid-template-columns:repeat(2,1fr); }
    .hero-side { flex-direction:row; align-items:center; flex-wrap:wrap; }
    .hero-visual { width:110px; height:110px; }
    .radar { width:100px; height:100px; }
  }
  @media (max-width:620px) {
    header { padding-top:18px; }
    h1 { font-size:1.55rem; }
    .hero { padding:16px; }
    .hero h2 { font-size:1.18rem; }
    .rules-grid { grid-template-columns:1fr; }
    .card { padding:15px; border-radius:15px; }
    #status { width:100%; order:5; }
    .rule-card { min-height:0; }
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <div class="brand-mark">J</div>
    <div>
      <h1>JarvisCAN</h1>
      <p class="sub">Alertas vehiculares por voz · Demo UNO Q</p>
    </div>
  </div>
  <div id="monitor" class="pill"><span class="dot"></span> Conectando…</div>
</header>
<main>
  <section class="card hero">
    <div class="hero-copy">
      <span class="live"><i></i> Demo en vivo</span>
      <h2>Seis reglas vigilan el vehículo. <span>Una voz avisa cuando algo no está bien.</span></h2>
      <p>JarvisCAN lee datos CAN/OBD-II, evalúa reglas de seguridad y convierte cada alerta en una locución de voz. Esta pantalla muestra las reglas activas y el historial de alertas.</p>
    </div>
    <div class="hero-side">
      <div class="hero-visual" aria-hidden="true"><div class="radar"><i></i></div></div>
      <div class="hero-badges">
        <span>6 reglas activas</span>
        <span>Chequeo cada 3 min</span>
        <span>Voz local</span>
      </div>
    </div>
  </section>

  <section class="card toolbar">
    <button id="enable">🔊 Activar sonido</button>
    <div class="eq" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div>
    <span id="status">Cargando…</span>
    <button id="refresh" class="secondary">Actualizar</button>
  </section>

  <div class="section-head">
    <div>
      <h2>Reglas de alerta configuradas</h2>
      <p>Cada regla se evalúa sobre las muestras CAN y puede generar una alerta con voz.</p>
    </div>
    <span class="badge">6 reglas · 3 min</span>
  </div>
  <section class="rules-grid" id="rules-grid" aria-label="Reglas de alerta configuradas"></section>

  <section class="card latest" id="latest-card" hidden>
    <div class="eyebrow">Última alerta</div>
    <div class="latest-head">
      <span id="latest-rule" class="rule"></span>
      <time id="latest-time"></time>
    </div>
    <p id="latest-message" class="message"></p>
    <button id="latest-play" class="small" hidden>Escuchar de nuevo</button>
  </section>

  <section class="card feed">
    <div class="feed-head">
      <h2>Alertas recientes</h2>
      <span id="count"></span>
    </div>
    <div id="empty" class="empty">Todavía no hay alertas. El monitor revisa cada 3 minutos.</div>
    <ul id="list"></ul>
  </section>

  <p class="hint">Las reglas se evalúan cada 3 minutos sobre los datos CAN simulados. Dejá esta página abierta y tocá “Activar sonido” una vez: cada alerta nueva se muestra y se reproduce sola en este equipo. El audífono Bluetooth de la placa es opcional.</p>
</main>
<audio id="audio" preload="auto"></audio>
<script>
  const RULES = [
    {id:'engine_temp', label:'Temperatura del motor', icon:'temp', accent:'#ff6b6b',
     detail:'Temperatura absoluta riesgosa o un salto brusco sobre la media móvil.',
     chips:['≥ 105 °C','Δ +15 °C','media 10 muestras']},
    {id:'coolant_level', label:'Nivel de refrigerante', icon:'drop', accent:'#4dd0e1',
     detail:'El refrigerante cae por debajo del nivel mínimo seguro.',
     chips:['≤ 60 %']},
    {id:'tire_pressure', label:'Presión de neumáticos', icon:'tire', accent:'#ffb74d',
     detail:'Presión absoluta baja o caída abrupta en cualquiera de las 4 ruedas.',
     chips:['≤ 180 kPa','caída ≥ 25 %','4 ruedas']},
    {id:'oil_level', label:'Nivel de aceite', icon:'oil', accent:'#c084fc',
     detail:'El aceite del motor cae por debajo del nivel mínimo seguro.',
     chips:['≤ 60 %']},
    {id:'dtc', label:'Códigos de falla', icon:'dtc', accent:'#ff8a65',
     detail:'Aparecen DTC nuevos o testigos de advertencia en las últimas muestras.',
     chips:['DTC nuevos','testigos','20 muestras']},
    {id:'overspeed', label:'Exceso de velocidad', icon:'speed', accent:'#64b5f6',
     detail:'La velocidad supera el límite y se genera una alerta por episodio.',
     chips:['> 130 km/h','1 por episodio']}
  ];

  const ICONS = {
    temp:'<path d="M12 4a2 2 0 0 1 2 2v7.2a4 4 0 1 1-4 0V6a2 2 0 0 1 2-2Z"/><path d="M12 9v6"/>',
    drop:'<path d="M12 3s6 6.3 6 10a6 6 0 0 1-12 0c0-3.7 6-10 6-10Z"/>',
    tire:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 4v3M12 17v3M4 12h3M17 12h3"/>',
    oil:'<path d="M5 15h14v4H5z"/><path d="M8 15V9h5l3 3v3"/><path d="M10 6h4"/>',
    dtc:'<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 9v5"/><circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none"/>',
    speed:'<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-5"/><circle cx="12" cy="18" r="1.6" fill="currentColor" stroke="none"/>'
  };

  const audio = document.getElementById('audio');
  const monitorEl = document.getElementById('monitor');
  const statusEl = document.getElementById('status');
  const latestCard = document.getElementById('latest-card');
  const latestRule = document.getElementById('latest-rule');
  const latestTime = document.getElementById('latest-time');
  const latestMessage = document.getElementById('latest-message');
  const latestPlay = document.getElementById('latest-play');
  const listEl = document.getElementById('list');
  const emptyEl = document.getElementById('empty');
  const countEl = document.getElementById('count');
  const enableBtn = document.getElementById('enable');

  let enabled = false;
  let first = true;
  let lastId = null;
  let queue = [];
  let playing = false;
  const fireTimers = new Map();

  function esc(value) {
    return String(value == null ? '' : value)
      .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  }

  function fmtTime(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toLocaleString('es-AR', {hour12: false});
  }

  function fmtShort(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString('es-AR', {hour12: false, hour: '2-digit', minute: '2-digit'});
  }

  function ruleMeta(rule) {
    return RULES.find((item) => item.id === rule) || null;
  }

  function ruleAccent(rule) {
    const meta = ruleMeta(rule);
    return meta ? meta.accent : '#2a6b8d';
  }

  function setStatus(text) { statusEl.textContent = text; }

  function setMonitor(active, text) {
    monitorEl.className = 'pill ' + (active ? 'ok' : 'off');
    monitorEl.innerHTML = '<span class="dot"></span> ' + text;
  }

  function setPlaying(on) {
    document.body.classList.toggle('playing', !!on);
  }

  function ruleIcon(name) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
      'stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || '') + '</svg>';
  }

  function renderRules() {
    const grid = document.getElementById('rules-grid');
    grid.innerHTML = RULES.map((r) =>
      '<article class="rule-card" data-rule="' + r.id + '" style="--accent:' + r.accent + '">' +
        '<div class="rule-top"><span class="rule-icon">' + ruleIcon(r.icon) + '</span>' +
        '<span class="rule-state" data-state>En guardia</span></div>' +
        '<h3>' + r.label + '</h3>' +
        '<p class="rule-detail">' + r.detail + '</p>' +
        '<div class="rule-chips">' + r.chips.map((c) => '<span>' + c + '</span>').join('') + '</div>' +
        '<div class="rule-foot"><span data-count>0 alertas</span><span data-last>sin alertas</span></div>' +
      '</article>'
    ).join('');
  }

  function updateRuleStats(alerts) {
    const counts = {};
    const latest = {};
    alerts.forEach((a) => {
      counts[a.rule] = (counts[a.rule] || 0) + 1;
      if (!latest[a.rule] || (a.epoch || 0) > (latest[a.rule].epoch || 0)) latest[a.rule] = a;
    });
    document.querySelectorAll('.rule-card').forEach((card) => {
      const rule = card.dataset.rule;
      const n = counts[rule] || 0;
      card.querySelector('[data-count]').textContent = n + (n === 1 ? ' alerta' : ' alertas');
      const last = latest[rule];
      card.querySelector('[data-last]').textContent = last ? 'última ' + fmtShort(last.ts) : 'sin alertas';
    });
  }

  function flashRule(rule) {
    const card = document.querySelector('.rule-card[data-rule="' + rule + '"]');
    if (!card) return;
    card.classList.remove('fired');
    void card.offsetWidth;
    card.classList.add('fired');
    const state = card.querySelector('[data-state]');
    state.textContent = 'Disparó';
    clearTimeout(fireTimers.get(card));
    fireTimers.set(card, setTimeout(() => {
      card.classList.remove('fired');
      state.textContent = 'En guardia';
    }, 8000));
  }

  async function fetchAlerts() {
    const r = await fetch('/api/alerts?limit=60', {cache: 'no-store'});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }

  function render(data) {
    const alerts = data.alerts || [];
    setMonitor(!!data.monitor_active, data.monitor_active ? 'Monitoreo activo' : 'Monitoreo detenido');

    const latest = alerts[0];
    if (latest) {
      latestCard.hidden = false;
      latestCard.style.setProperty('--accent', ruleAccent(latest.rule));
      latestRule.style.setProperty('--accent', ruleAccent(latest.rule));
      latestRule.innerHTML = '<i class="rule-dot"></i>' + esc(latest.rule_label || latest.rule);
      latestTime.textContent = fmtTime(latest.ts);
      latestMessage.textContent = latest.message;
      latestPlay.hidden = !latest.audio_url;
      latestPlay.dataset.url = latest.audio_url || '';
    } else {
      latestCard.hidden = true;
    }

    countEl.textContent = alerts.length ? alerts.length + ' recientes' : '';
    emptyEl.hidden = alerts.length > 0;
    listEl.innerHTML = alerts.map((a) => {
      const accent = ruleAccent(a.rule);
      const play = a.audio_url
        ? '<button class="small play" data-url="' + esc(a.audio_url) + '">Escuchar</button>'
        : '';
      return '<li>' +
        '<div class="item-top"><span class="rule" style="--accent:' + accent + '">' +
        '<i class="rule-dot"></i>' + esc(a.rule_label || a.rule) + '</span>' +
        '<time>' + esc(fmtTime(a.ts)) + '</time></div>' +
        '<p class="message">' + esc(a.message) + '</p>' +
        (play ? '<div style="margin-top:10px">' + play + '</div>' : '') +
      '</li>';
    }).join('');

    updateRuleStats(alerts);
  }

  async function unlock() {
    audio.src = '/silence.wav?t=' + Date.now();
    try {
      await audio.play();
      enabled = true;
      enableBtn.textContent = 'Sonido activado';
      setStatus('Sonido activado. Esperando alertas…');
      pump();
      return true;
    } catch (e) {
      setStatus('El navegador bloqueó el audio. Tocá “Activar sonido” de nuevo.');
      return false;
    }
  }

  function playUrl(url) {
    if (!url) return;
    if (!enabled) {
      setStatus('Tocá “Activar sonido” para escuchar las alertas.');
      return;
    }
    queue = [];
    playing = true;
    audio.src = url + (url.includes('?') ? '&' : '?') + 't=' + Date.now();
    audio.play().then(() => setStatus('Reproduciendo alerta…')).catch(() => {
      playing = false;
      setStatus('No se pudo reproducir. Tocá “Activar sonido” y probá de nuevo.');
    });
  }

  function pump() {
    if (!enabled || playing || !queue.length) return;
    const alert = queue.shift();
    if (!alert.audio_url) { pump(); return; }
    playing = true;
    audio.src = alert.audio_url + (alert.audio_url.includes('?') ? '&' : '?') + 't=' + Date.now();
    audio.play().then(() => setStatus('Alerta: ' + (alert.rule_label || alert.rule))).catch(() => {
      playing = false;
      setStatus('El navegador bloqueó el audio. Tocá “Activar sonido”.');
    });
  }

  async function poll() {
    let data;
    try {
      data = await fetchAlerts();
    } catch (e) {
      setMonitor(false, 'Sin conexión');
      setStatus('Sin conexión con la UNO Q. Reintentando…');
      return;
    }

    const alerts = data.alerts || [];
    if (first) {
      first = false;
      lastId = alerts.length ? alerts[0].id : null;
      render(data);
      if (!enabled) setStatus('Tocá “Activar sonido” para escuchar las alertas.');
      return;
    }

    let fresh = [];
    if (lastId === null) {
      fresh = alerts.slice();
    } else {
      const idx = alerts.findIndex((a) => a.id === lastId);
      fresh = idx > 0 ? alerts.slice(0, idx) : [];
    }
    lastId = alerts.length ? alerts[0].id : lastId;
    render(data);

    if (!fresh.length) return;
    fresh.reverse();
    const playable = fresh.filter((a) => a.audio_url);
    playable.forEach((a) => queue.push(a));
    flashRule(fresh[fresh.length - 1].rule);
    if (fresh.length === 1) {
      setStatus('Nueva alerta: ' + (fresh[0].rule_label || fresh[0].rule));
    } else {
      setStatus(fresh.length + ' alertas nuevas.');
    }
    if (!enabled) {
      setStatus('Hay ' + fresh.length + ' alerta(s) nueva(s). Tocá “Activar sonido”.');
      return;
    }
    pump();
  }

  enableBtn.onclick = unlock;
  document.getElementById('refresh').onclick = poll;
  latestPlay.onclick = () => playUrl(latestPlay.dataset.url);
  listEl.addEventListener('click', (event) => {
    const button = event.target.closest('button.play');
    if (!button) return;
    if (!enabled) {
      unlock().then((ok) => { if (ok) playUrl(button.dataset.url); });
      return;
    }
    playUrl(button.dataset.url);
  });
  audio.addEventListener('playing', () => setPlaying(true));
  audio.addEventListener('pause', () => setPlaying(false));
  audio.addEventListener('ended', () => { setPlaying(false); playing = false; pump(); });
  audio.addEventListener('error', () => setPlaying(false));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

  renderRules();
  poll();
  setInterval(poll, 2000);
</script>
</body>
</html>
"""


def silent_wav():
    rate = 16000
    samples = int(rate * 0.12)
    data = b"\x00\x00" * samples
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(data), b"WAVE", b"fmt ", 16,
        1, 1, rate, rate * 2, 2, 16, b"data", len(data),
    )
    return header + data


def load_alerts(jsonl_path, audio_dir, limit=60):
    try:
        lines = Path(jsonl_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    alerts = []
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        audio_file = str(event.get("audio_file") or "")
        audio_url = ""
        if audio_file:
            name = Path(audio_file).name
            if name and name not in (".", "..") and (Path(audio_dir) / name).is_file():
                audio_url = "/alert-audio/" + quote(name)
        rule = str(event.get("rule") or "")
        alert_id = audio_file or f"{event.get('epoch', '')}-{rule}-{len(alerts)}"
        alerts.append({
            "id": alert_id,
            "ts": str(event.get("ts") or ""),
            "epoch": event.get("epoch") or 0,
            "rule": rule,
            "rule_label": RULE_LABELS.get(rule, rule),
            "message": str(event.get("message") or ""),
            "audio_url": audio_url,
            "played_on_device": bool(event.get("played_on_device")),
            "audio_sink": str(event.get("audio_sink") or ""),
        })
    alerts.sort(key=lambda item: (item.get("epoch") or 0, item.get("ts") or ""), reverse=True)
    return alerts[:max(1, int(limit))]


def monitor_active(data_dir):
    pid_file = Path(data_dir) / "can_alerts.pid"
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "JarvisCANAlerts/2.0"

    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/healthz":
            body = {"ok": True, "monitor_active": monitor_active(self.server.answer_dir)}
            self._send(200, json.dumps(body).encode("utf-8"), "application/json")
            return
        if path == "/api/alerts":
            try:
                limit = int(parse_qs(parsed.query).get("limit", ["60"])[0])
            except (TypeError, ValueError):
                limit = 60
            limit = min(200, max(1, limit))
            alerts = load_alerts(
                self.server.alerts_jsonl, self.server.alert_audio_dir, limit,
            )
            body = {
                "alerts": alerts,
                "count": len(alerts),
                "monitor_active": monitor_active(self.server.answer_dir),
            }
            self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        if path.startswith("/alert-audio/"):
            name = unquote(path[len("/alert-audio/"):])
            if not name or name in (".", "..") or "\\" in name or Path(name).name != name:
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            wav = Path(self.server.alert_audio_dir) / name
            try:
                body = wav.read_bytes()
            except OSError:
                self._send(404, b"no audio", "text/plain; charset=utf-8")
                return
            self._send(200, body, "audio/wav")
            return
        if path == "/silence.wav":
            self._send(200, silent_wav(), "audio/wav")
            return
        if path == "/answer.json":
            meta = Path(self.server.answer_dir) / "last_answer.json"
            try:
                body = meta.read_bytes()
                data = json.loads(body.decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError
            except Exception:
                data = {"mtime": 0, "text": ""}
            self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        if path == "/answer.wav":
            wav = Path(self.server.answer_dir) / "last_answer.wav"
            try:
                body = wav.read_bytes()
            except OSError:
                self._send(404, b"no answer yet", "text/plain; charset=utf-8")
                return
            self._send(200, body, "audio/wav")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def main():
    ap = argparse.ArgumentParser(description="Panel de alertas de JarvisCAN")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--alerts-jsonl", default="")
    ap.add_argument("--alert-audio-dir", default="")
    args = ap.parse_args()
    answer_dir = Path(args.dir).expanduser().resolve()
    answer_dir.mkdir(parents=True, exist_ok=True)
    alerts_jsonl = (
        Path(args.alerts_jsonl).expanduser().resolve()
        if args.alerts_jsonl else answer_dir / "alerts.jsonl"
    )
    alert_audio_dir = (
        Path(args.alert_audio_dir).expanduser().resolve()
        if args.alert_audio_dir else answer_dir / "alert_audio"
    )
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.answer_dir = answer_dir
    server.alerts_jsonl = alerts_jsonl
    server.alert_audio_dir = alert_audio_dir
    print(
        f"Panel de alertas en http://{args.host}:{args.port}/ "
        f"(jsonl={alerts_jsonl}, audio={alert_audio_dir})",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
