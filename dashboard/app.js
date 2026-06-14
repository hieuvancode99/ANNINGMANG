/**
 * app.js — SDN DDoS Detection Dashboard
 *
 * Connects to Ryu Controller REST API for real-time data.
 * Falls back to Demo mode if controller is unreachable.
 */

// ============================================================
// CONFIGURATION
// ============================================================
const DEFAULT_API_BASE = 'http://localhost:8080';
let API_BASE = DEFAULT_API_BASE;
let POLL_INTERVAL = 2000; // ms

// ============================================================
// APPLICATION STATE
// ============================================================
const state = {
  mode: 'connecting',       // 'live', 'demo', 'connecting', 'offline'
  activeModel: 'lstm',
  connected: false,

  // KPI
  latency: { avg: 0, min: 0, max: 0, count: 0 },
  totalFlows: 0,
  totalAlerts: 0,
  detectionRate: 0,
  throughput: 0,

  // Extractor
  trackedFlows: 0,
  bufferedFlows: 0,
  queueData: 0,
  queueResult: 0,

  // Charts data
  latencyHistory: [],
  classificationData: { normal: 0, ddos: 0 },

  // Alerts
  alerts: [],
  lastAlertCount: 0,

  // Simulation
  attackRunning: false,
  attackType: 'syn',
  attackSource: 'h2',
  attackTarget: 'h1',

  // Connected switches
  dpids: [],
};

// Demo mode simulation
const demo = {
  enabled: false,
  tickCount: 0,
  attackActive: false,
};

// ============================================================
// TOPOLOGY DATA — Tree Topo (depth=2, fanout=3)
// ============================================================
const TOPO = {
  switches: [
    { id: 's1', label: 'S1 (Core)', x: 400, y: 80, isCore: true },
    { id: 's2', label: 'S2', x: 160, y: 200 },
    { id: 's3', label: 'S3', x: 400, y: 200 },
    { id: 's4', label: 'S4', x: 640, y: 200 },
  ],
  hosts: [
    { id: 'h1', label: 'H1', x: 80,  y: 340, parent: 's2' },
    { id: 'h2', label: 'H2', x: 160, y: 340, parent: 's2' },
    { id: 'h3', label: 'H3', x: 240, y: 340, parent: 's2' },
    { id: 'h4', label: 'H4', x: 320, y: 340, parent: 's3' },
    { id: 'h5', label: 'H5', x: 400, y: 340, parent: 's3' },
    { id: 'h6', label: 'H6', x: 480, y: 340, parent: 's3' },
    { id: 'h7', label: 'H7', x: 560, y: 340, parent: 's4' },
    { id: 'h8', label: 'H8', x: 640, y: 340, parent: 's4' },
    { id: 'h9', label: 'H9', x: 720, y: 340, parent: 's4' },
  ],
  links: [
    { from: 's1', to: 's2' },
    { from: 's1', to: 's3' },
    { from: 's1', to: 's4' },
    { from: 's2', to: 'h1' },
    { from: 's2', to: 'h2' },
    { from: 's2', to: 'h3' },
    { from: 's3', to: 'h4' },
    { from: 's3', to: 'h5' },
    { from: 's3', to: 'h6' },
    { from: 's4', to: 'h7' },
    { from: 's4', to: 'h8' },
    { from: 's4', to: 'h9' },
  ],
};

// Model info
const MODEL_INFO = {
  lstm:        { name: 'LSTM', shape: '(1, 10, 6)', threshold: '> 0.5', avgLatency: 1.2 },
  transformer: { name: 'Transformer', shape: '(1, 10, 6)', threshold: '> 0.5', avgLatency: 1.8 },
  autoencoder: { name: 'Autoencoder', shape: '(1, 6)', threshold: 'MSE > 0.0026', avgLatency: 0.3 },
};


// ============================================================
// API CLIENT
// ============================================================
async function apiGet(path) {
  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (e) {
    return null;
  }
}

async function apiPut(path, body) {
  try {
    const resp = await fetch(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (e) {
    return null;
  }
}


// ============================================================
// DATA FETCHING (LIVE MODE)
// ============================================================
async function fetchStats() {
  const data = await apiGet('/api/stats');
  if (!data) return false;

  state.activeModel = data.active_model || state.activeModel;
  state.dpids = data.connected_dpids || [];
  state.queueData = data.queue_data || 0;
  state.queueResult = data.queue_result || 0;
  state.totalAlerts = data.total_alerts || 0;

  // Latency
  if (data.latency) {
    state.latency = {
      avg: data.latency.avg_ms || 0,
      min: data.latency.min_ms === Infinity ? 0 : (data.latency.min_ms || 0),
      max: data.latency.max_ms || 0,
      count: data.latency.count || 0,
    };
    state.totalFlows = data.latency.count || 0;
  }

  // Extractor
  if (data.extractor) {
    state.trackedFlows = data.extractor.tracked_flows || 0;
    state.bufferedFlows = data.extractor.buffered_flows || 0;
  }

  // Push latency to history
  if (state.latency.avg > 0) {
    state.latencyHistory.push({
      time: Date.now(),
      value: state.latency.avg,
    });
    if (state.latencyHistory.length > 60) state.latencyHistory.shift();
  }

  return true;
}

async function fetchAlerts() {
  const data = await apiGet('/api/alerts');
  if (!data || !data.alerts) return false;

  state.alerts = data.alerts;

  // Count normal vs ddos
  let ddos = 0;
  let normal = 0;
  for (const a of state.alerts) {
    if (a.label === 'DDoS') ddos++;
    else normal++;
  }
  state.classificationData = { normal, ddos };

  // Detection rate
  const total = normal + ddos;
  state.detectionRate = total > 0 ? ((ddos / total) * 100) : 0;

  // Throughput (flows per second based on last 10 alerts)
  if (state.alerts.length >= 2) {
    const recent = state.alerts.slice(-10);
    const dt = recent[recent.length - 1].timestamp - recent[0].timestamp;
    state.throughput = dt > 0 ? (recent.length / dt).toFixed(1) : 0;
  }

  return true;
}

async function fetchModel() {
  const data = await apiGet('/api/model');
  if (!data) return false;
  state.activeModel = data.model || state.activeModel;
  return true;
}


// ============================================================
// DEMO MODE ENGINE
// ============================================================
function demoTick() {
  demo.tickCount++;

  // Simulate latency based on model
  const baseLatency = MODEL_INFO[state.activeModel]?.avgLatency || 1.0;
  const jitter = (Math.random() - 0.5) * 0.8;
  let lat = baseLatency + jitter;

  if (demo.attackActive) {
    lat += Math.random() * 0.5; // Slightly higher under attack
  }
  lat = Math.max(0.05, lat);

  state.latency.avg = lat;
  state.latency.count++;
  state.totalFlows = state.latency.count;

  state.latencyHistory.push({ time: Date.now(), value: lat });
  if (state.latencyHistory.length > 60) state.latencyHistory.shift();

  // Simulate tracked flows
  state.trackedFlows = 5 + Math.floor(Math.random() * 10);
  state.bufferedFlows = state.trackedFlows;
  state.queueData = Math.floor(Math.random() * 5);
  state.queueResult = Math.floor(Math.random() * 3);

  // Attack simulation
  if (demo.attackActive && demo.tickCount % 2 === 0) {
    const confidence = 0.85 + Math.random() * 0.14;
    const alert = {
      timestamp: Date.now() / 1000,
      flow_id: `${state.attackSource}_to_${state.attackTarget}_${demo.tickCount}`,
      model: state.activeModel,
      confidence: parseFloat(confidence.toFixed(4)),
      latency_ms: parseFloat(lat.toFixed(2)),
      label: 'DDoS',
    };
    state.alerts.push(alert);
    state.totalAlerts = state.alerts.length;
    state.classificationData.ddos++;
  } else if (demo.tickCount % 3 === 0) {
    // Normal flow
    state.classificationData.normal++;
  }

  // Detection rate
  const total = state.classificationData.normal + state.classificationData.ddos;
  state.detectionRate = total > 0 ? ((state.classificationData.ddos / total) * 100) : 0;
  state.throughput = (1000 / POLL_INTERVAL).toFixed(1);
}


// ============================================================
// TOPOLOGY RENDERER (SVG)
// ============================================================
class TopologyRenderer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.svg = null;
    this.nodes = {};
    this.links = {};
    this.particles = [];
    this.animFrame = null;
    this.init();
  }

  init() {
    const ns = 'http://www.w3.org/2000/svg';
    this.svg = document.createElementNS(ns, 'svg');
    this.svg.setAttribute('viewBox', '0 0 800 400');
    this.svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    this.container.innerHTML = '';
    this.container.appendChild(this.svg);

    // Defs for filters
    const defs = document.createElementNS(ns, 'defs');

    // Glow filter
    const glow = document.createElementNS(ns, 'filter');
    glow.setAttribute('id', 'glow');
    glow.innerHTML = `
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    `;
    defs.appendChild(glow);

    // Attack glow
    const attackGlow = document.createElementNS(ns, 'filter');
    attackGlow.setAttribute('id', 'attack-glow');
    attackGlow.innerHTML = `
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feFlood flood-color="#ef4444" flood-opacity="0.6" result="color"/>
      <feComposite in="color" in2="blur" operator="in" result="shadow"/>
      <feMerge><feMergeNode in="shadow"/><feMergeNode in="SourceGraphic"/></feMerge>
    `;
    defs.appendChild(attackGlow);

    this.svg.appendChild(defs);

    // Draw links
    const linkGroup = document.createElementNS(ns, 'g');
    linkGroup.setAttribute('class', 'topo-links');
    TOPO.links.forEach((link, i) => {
      const line = document.createElementNS(ns, 'line');
      const fromNode = this._findNode(link.from);
      const toNode = this._findNode(link.to);
      line.setAttribute('x1', fromNode.x);
      line.setAttribute('y1', fromNode.y);
      line.setAttribute('x2', toNode.x);
      line.setAttribute('y2', toNode.y);
      line.setAttribute('class', 'topo-link');
      line.setAttribute('id', `link-${link.from}-${link.to}`);
      linkGroup.appendChild(line);
      this.links[`${link.from}-${link.to}`] = line;
    });
    this.svg.appendChild(linkGroup);

    // Particle group
    this.particleGroup = document.createElementNS(ns, 'g');
    this.particleGroup.setAttribute('class', 'topo-particles');
    this.svg.appendChild(this.particleGroup);

    // Draw switches
    const nodeGroup = document.createElementNS(ns, 'g');
    nodeGroup.setAttribute('class', 'topo-nodes');

    TOPO.switches.forEach(sw => {
      const g = document.createElementNS(ns, 'g');
      g.setAttribute('class', `topo-node topo-node-switch ${sw.isCore ? 'core' : ''}`);
      g.setAttribute('id', `node-${sw.id}`);

      const size = sw.isCore ? 50 : 40;
      const rect = document.createElementNS(ns, 'rect');
      rect.setAttribute('x', sw.x - size/2);
      rect.setAttribute('y', sw.y - size/2);
      rect.setAttribute('width', size);
      rect.setAttribute('height', size);
      g.appendChild(rect);

      // Switch icon (⬡)
      const icon = document.createElementNS(ns, 'text');
      icon.setAttribute('x', sw.x);
      icon.setAttribute('y', sw.y + 1);
      icon.setAttribute('text-anchor', 'middle');
      icon.setAttribute('dominant-baseline', 'central');
      icon.setAttribute('fill', sw.isCore ? '#8b5cf6' : '#00d4ff');
      icon.setAttribute('font-size', sw.isCore ? '18' : '14');
      icon.textContent = '⬡';
      g.appendChild(icon);

      // Label
      const label = document.createElementNS(ns, 'text');
      label.setAttribute('x', sw.x);
      label.setAttribute('y', sw.y + size/2 + 14);
      label.setAttribute('class', `topo-label ${sw.isCore ? 'topo-label-core' : 'topo-label-switch'}`);
      label.textContent = sw.label;
      g.appendChild(label);

      nodeGroup.appendChild(g);
      this.nodes[sw.id] = g;
    });

    // Draw hosts
    TOPO.hosts.forEach(host => {
      const g = document.createElementNS(ns, 'g');
      g.setAttribute('class', 'topo-node topo-node-host');
      g.setAttribute('id', `node-${host.id}`);

      const circle = document.createElementNS(ns, 'circle');
      circle.setAttribute('cx', host.x);
      circle.setAttribute('cy', host.y);
      circle.setAttribute('r', 18);
      g.appendChild(circle);

      // Host icon
      const icon = document.createElementNS(ns, 'text');
      icon.setAttribute('x', host.x);
      icon.setAttribute('y', host.y + 1);
      icon.setAttribute('text-anchor', 'middle');
      icon.setAttribute('dominant-baseline', 'central');
      icon.setAttribute('fill', '#10b981');
      icon.setAttribute('font-size', '14');
      icon.textContent = '💻';
      g.appendChild(icon);

      // Label
      const label = document.createElementNS(ns, 'text');
      label.setAttribute('x', host.x);
      label.setAttribute('y', host.y + 32);
      label.setAttribute('class', 'topo-label');
      label.textContent = host.label;
      g.appendChild(label);

      nodeGroup.appendChild(g);
      this.nodes[host.id] = g;
    });

    this.svg.appendChild(nodeGroup);
  }

  _findNode(id) {
    return TOPO.switches.find(s => s.id === id) || TOPO.hosts.find(h => h.id === id);
  }

  setAttack(sourceId, targetId, active) {
    // Reset all
    Object.values(this.links).forEach(l => {
      l.setAttribute('class', 'topo-link');
    });
    document.querySelectorAll('.topo-node-host').forEach(n => {
      n.classList.remove('attacker', 'victim', 'blocked');
    });

    // Clear particles
    this.particleGroup.innerHTML = '';
    this.particles = [];

    if (!active) return;

    // Find path: source → parent switch → core → target parent switch → target
    const source = TOPO.hosts.find(h => h.id === sourceId);
    const target = TOPO.hosts.find(h => h.id === targetId);
    if (!source || !target) return;

    // Mark attacker & victim
    const srcNode = this.nodes[sourceId];
    const tgtNode = this.nodes[targetId];
    if (srcNode) srcNode.classList.add('attacker');
    if (tgtNode) tgtNode.classList.add('victim');

    // Build path
    const path = [];
    path.push({ from: sourceId, to: source.parent });
    if (source.parent !== target.parent) {
      path.push({ from: source.parent, to: 's1' });
      path.push({ from: 's1', to: target.parent });
    }
    path.push({ from: target.parent, to: targetId });

    // Highlight links
    path.forEach(seg => {
      const key1 = `${seg.from}-${seg.to}`;
      const key2 = `${seg.to}-${seg.from}`;
      const link = this.links[key1] || this.links[key2];
      if (link) link.setAttribute('class', 'topo-link attack');
    });

    // Create particles along attack path
    this._createParticles(path);
  }

  _createParticles(path) {
    const ns = 'http://www.w3.org/2000/svg';

    path.forEach(seg => {
      const from = this._findNode(seg.from);
      const to = this._findNode(seg.to);
      for (let i = 0; i < 3; i++) {
        const circle = document.createElementNS(ns, 'circle');
        circle.setAttribute('r', '3');
        circle.setAttribute('fill', '#ef4444');
        circle.setAttribute('filter', 'url(#attack-glow)');
        circle.setAttribute('opacity', '0.8');
        this.particleGroup.appendChild(circle);
        this.particles.push({
          el: circle,
          x1: from.x, y1: from.y,
          x2: to.x, y2: to.y,
          progress: i / 3,
          speed: 0.015 + Math.random() * 0.01,
        });
      }
    });

    this._animateParticles();
  }

  _animateParticles() {
    if (this.particles.length === 0) return;

    const animate = () => {
      this.particles.forEach(p => {
        p.progress += p.speed;
        if (p.progress > 1) p.progress -= 1;

        const x = p.x1 + (p.x2 - p.x1) * p.progress;
        const y = p.y1 + (p.y2 - p.y1) * p.progress;
        p.el.setAttribute('cx', x);
        p.el.setAttribute('cy', y);
      });

      if (state.attackRunning || demo.attackActive) {
        this.animFrame = requestAnimationFrame(animate);
      }
    };
    this.animFrame = requestAnimationFrame(animate);
  }

  stopAnimation() {
    if (this.animFrame) {
      cancelAnimationFrame(this.animFrame);
      this.animFrame = null;
    }
  }
}


// ============================================================
// CHART — Latency Line Chart (Canvas 2D)
// ============================================================
class LatencyChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width * window.devicePixelRatio;
    this.canvas.height = rect.height * window.devicePixelRatio;
    this.canvas.style.width = rect.width + 'px';
    this.canvas.style.height = rect.height + 'px';
    this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    this.w = rect.width;
    this.h = rect.height;
  }

  draw(data) {
    const ctx = this.ctx;
    const w = this.w;
    const h = this.h;

    ctx.clearRect(0, 0, w, h);

    if (data.length < 2) {
      ctx.fillStyle = '#64748b';
      ctx.font = '12px Inter';
      ctx.textAlign = 'center';
      ctx.fillText('Đang chờ dữ liệu...', w / 2, h / 2);
      return;
    }

    const values = data.map(d => d.value);
    const maxVal = Math.max(...values, 3) * 1.2;
    const minVal = 0;
    const padding = { top: 10, right: 10, bottom: 25, left: 40 };
    const chartW = w - padding.left - padding.right;
    const chartH = h - padding.top - padding.bottom;

    // Grid lines
    ctx.strokeStyle = 'rgba(100, 116, 139, 0.15)';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(w - padding.right, y);
      ctx.stroke();

      // Y labels
      const val = maxVal - (maxVal / 4) * i;
      ctx.fillStyle = '#64748b';
      ctx.font = '10px JetBrains Mono';
      ctx.textAlign = 'right';
      ctx.fillText(val.toFixed(1), padding.left - 6, y + 3);
    }

    // Y axis label
    ctx.save();
    ctx.fillStyle = '#64748b';
    ctx.font = '9px Inter';
    ctx.textAlign = 'center';
    ctx.translate(10, h / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('ms', 0, 0);
    ctx.restore();

    // Draw line
    const points = values.map((v, i) => ({
      x: padding.left + (i / (values.length - 1)) * chartW,
      y: padding.top + chartH - ((v - minVal) / (maxVal - minVal)) * chartH,
    }));

    // Gradient fill
    const gradient = ctx.createLinearGradient(0, padding.top, 0, h - padding.bottom);
    gradient.addColorStop(0, 'rgba(0, 212, 255, 0.2)');
    gradient.addColorStop(1, 'rgba(0, 212, 255, 0.0)');

    ctx.beginPath();
    ctx.moveTo(points[0].x, h - padding.bottom);
    points.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, h - padding.bottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Line
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      const xc = (points[i].x + points[i-1].x) / 2;
      const yc = (points[i].y + points[i-1].y) / 2;
      ctx.quadraticCurveTo(points[i-1].x, points[i-1].y, xc, yc);
    }
    ctx.lineTo(points[points.length-1].x, points[points.length-1].y);
    ctx.strokeStyle = '#00d4ff';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Current value dot
    const last = points[points.length - 1];
    ctx.beginPath();
    ctx.arc(last.x, last.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#00d4ff';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(last.x, last.y, 7, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(0, 212, 255, 0.3)';
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}


// ============================================================
// CHART — Doughnut Chart (Canvas 2D)
// ============================================================
class DoughnutChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const size = Math.min(rect.width, rect.height);
    this.canvas.width = size * window.devicePixelRatio;
    this.canvas.height = size * window.devicePixelRatio;
    this.canvas.style.width = size + 'px';
    this.canvas.style.height = size + 'px';
    this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    this.size = size;
  }

  draw(normal, ddos) {
    const ctx = this.ctx;
    const size = this.size;
    const cx = size / 2;
    const cy = size / 2;
    const r = size / 2 - 10;
    const innerR = r * 0.6;

    ctx.clearRect(0, 0, size, size);

    const total = normal + ddos;
    if (total === 0) {
      // Empty state
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.arc(cx, cy, innerR, 0, Math.PI * 2, true);
      ctx.fillStyle = 'rgba(100, 116, 139, 0.1)';
      ctx.fill();

      ctx.fillStyle = '#64748b';
      ctx.font = '11px Inter';
      ctx.textAlign = 'center';
      ctx.fillText('No data', cx, cy + 4);
      return;
    }

    const segments = [
      { value: normal, color: '#10b981', label: 'Normal' },
      { value: ddos, color: '#ef4444', label: 'DDoS' },
    ];

    let startAngle = -Math.PI / 2;
    segments.forEach(seg => {
      if (seg.value === 0) return;
      const angle = (seg.value / total) * Math.PI * 2;
      const gap = 0.03;

      ctx.beginPath();
      ctx.arc(cx, cy, r, startAngle + gap, startAngle + angle - gap);
      ctx.arc(cx, cy, innerR, startAngle + angle - gap, startAngle + gap, true);
      ctx.closePath();
      ctx.fillStyle = seg.color;
      ctx.fill();

      startAngle += angle;
    });

    // Center text
    const pct = total > 0 ? ((ddos / total) * 100).toFixed(0) : '0';
    ctx.fillStyle = '#e2e8f0';
    ctx.font = 'bold 18px JetBrains Mono';
    ctx.textAlign = 'center';
    ctx.fillText(`${pct}%`, cx, cy - 2);
    ctx.fillStyle = '#64748b';
    ctx.font = '9px Inter';
    ctx.fillText('DDoS', cx, cy + 14);
  }
}


// ============================================================
// SPARKLINE (Mini chart for stat cards)
// ============================================================
class Sparkline {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.resize();
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width * window.devicePixelRatio;
    this.canvas.height = rect.height * window.devicePixelRatio;
    this.canvas.style.width = rect.width + 'px';
    this.canvas.style.height = rect.height + 'px';
    this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    this.w = rect.width;
    this.h = rect.height;
  }

  draw(data, color = '#00d4ff') {
    if (!this.canvas || data.length < 2) return;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.w, this.h);

    const max = Math.max(...data) * 1.2 || 1;
    const step = this.w / (data.length - 1);

    // Convert hex to rgba for fill
    const hexToRgba = (hex, alpha) => {
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    };

    // Fill
    const grad = ctx.createLinearGradient(0, 0, 0, this.h);
    grad.addColorStop(0, hexToRgba(color, 0.2));
    grad.addColorStop(1, 'transparent');

    ctx.beginPath();
    ctx.moveTo(0, this.h);
    data.forEach((v, i) => {
      ctx.lineTo(i * step, this.h - (v / max) * this.h);
    });
    ctx.lineTo(this.w, this.h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    data.forEach((v, i) => {
      const x = i * step;
      const y = this.h - (v / max) * this.h;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
}


// ============================================================
// UI UPDATERS
// ============================================================
function updateClock() {
  const el = document.getElementById('header-clock');
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function updateStatusBadge() {
  const badge = document.getElementById('status-badge');
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  if (!badge) return;

  badge.className = 'status-badge';
  if (state.mode === 'live') {
    badge.classList.add('live');
    text.textContent = 'LIVE';
  } else if (state.mode === 'demo') {
    badge.classList.add('demo');
    text.textContent = 'DEMO';
  } else {
    badge.classList.add('offline');
    text.textContent = state.mode === 'connecting' ? 'CONNECTING' : 'OFFLINE';
  }
}

function updateStats() {
  // Latency
  const latEl = document.getElementById('stat-latency');
  if (latEl) latEl.textContent = state.latency.avg.toFixed(2);

  // Detection rate
  const detEl = document.getElementById('stat-detection');
  if (detEl) detEl.textContent = state.detectionRate.toFixed(1);

  // Total flows
  const flowEl = document.getElementById('stat-flows');
  if (flowEl) flowEl.textContent = state.totalFlows.toLocaleString();

  // Alerts
  const alertEl = document.getElementById('stat-alerts');
  if (alertEl) alertEl.textContent = state.totalAlerts.toLocaleString();

  // Sub stats
  const trackedEl = document.getElementById('stat-tracked');
  if (trackedEl) trackedEl.textContent = `Tracked: ${state.trackedFlows}`;

  const queueEl = document.getElementById('stat-queue');
  if (queueEl) queueEl.textContent = `Queue: ${state.queueData}/${state.queueResult}`;
}

function updateModelButtons() {
  document.querySelectorAll('.model-btn').forEach(btn => {
    const model = btn.dataset.model;
    btn.classList.toggle('active', model === state.activeModel);
  });
}

function updateAlertTimeline() {
  const list = document.getElementById('alert-list');
  const countBadge = document.getElementById('alert-count');
  if (!list) return;

  // Lọc chỉ lấy các cảnh báo thực sự (DDoS) để hiển thị trên danh sách
  const ddosAlerts = state.alerts.filter(a => a.label === 'DDoS');
  const displayAlerts = ddosAlerts.slice(-50).reverse();

  if (displayAlerts.length === 0) {
    list.innerHTML = '<div class="no-alerts">🛡️ Chưa có cảnh báo nào</div>';
  } else {
    list.innerHTML = displayAlerts.map(a => {
      const time = new Date(a.timestamp * 1000).toLocaleTimeString('vi-VN');
      const isDDoS = a.label === 'DDoS';
      return `
        <div class="alert-item ${isDDoS ? '' : 'normal'}">
          <div class="alert-time">${time}</div>
          <div class="alert-text">
            <strong>${isDDoS ? '⚠️ DDoS' : '✅ Normal'}</strong> — 
            ${a.flow_id ? a.flow_id.substring(0, 40) : 'N/A'}${a.flow_id && a.flow_id.length > 40 ? '...' : ''}
          </div>
          <div class="alert-meta">
            <span>Model: ${a.model}</span>
            <span>Conf: ${(a.confidence || 0).toFixed(4)}</span>
            <span>${(a.latency_ms || 0).toFixed(2)}ms</span>
          </div>
        </div>
      `;
    }).join('');
  }

  if (countBadge) {
    countBadge.textContent = state.alerts.filter(a => a.label === 'DDoS').length;
  }
}


// ============================================================
// EVENT HANDLERS
// ============================================================
let topoRenderer = null;
let latencyChart = null;
let doughnutChart = null;
let sparkLatency = null;
let pollTimer = null;

function initCharts() {
  latencyChart = new LatencyChart('latency-canvas');
  doughnutChart = new DoughnutChart('doughnut-canvas');
  sparkLatency = new Sparkline('spark-latency');
}

function initTopology() {
  topoRenderer = new TopologyRenderer('topology-container');
}

async function handleModelSwitch(modelName) {
  if (modelName === state.activeModel) return;

  if (state.mode === 'live') {
    const result = await apiPut('/api/model', { model: modelName });
    if (result && result.status === 'ok') {
      state.activeModel = modelName;
    }
  } else {
    // Demo mode — instant switch
    state.activeModel = modelName;
    // Reset latency history for demo
    state.latencyHistory = [];
    state.latency.count = 0;
  }
  updateModelButtons();
}

function handleLaunchAttack() {
  const type = document.getElementById('attack-type').value;
  const source = document.getElementById('attack-source').value;
  const target = document.getElementById('attack-target').value;

  state.attackRunning = true;
  state.attackType = type;
  state.attackSource = source;
  state.attackTarget = target;

  if (state.mode === 'demo') {
    demo.attackActive = true;
  }

  topoRenderer.setAttack(source, target, true);

  document.getElementById('btn-launch').disabled = true;
  document.getElementById('btn-stop').disabled = false;
}

function handleStopAttack() {
  state.attackRunning = false;

  if (state.mode === 'demo') {
    demo.attackActive = false;
  }

  topoRenderer.setAttack(null, null, false);
  topoRenderer.stopAnimation();

  document.getElementById('btn-launch').disabled = false;
  document.getElementById('btn-stop').disabled = true;
}

async function handleConnect() {
  const urlInput = document.getElementById('api-url');
  API_BASE = urlInput.value.replace(/\/$/, '');
  state.mode = 'connecting';
  updateStatusBadge();

  const ok = await fetchStats();
  if (ok) {
    state.mode = 'live';
    state.connected = true;
    demo.enabled = false;
    await fetchAlerts();
    await fetchModel();
  } else {
    state.mode = 'demo';
    state.connected = false;
    demo.enabled = true;
  }
  updateStatusBadge();
  updateModelButtons();
}


// ============================================================
// MAIN LOOP
// ============================================================
async function mainLoop() {
  if (state.mode === 'live') {
    await fetchStats();
    await fetchAlerts();
  } else if (state.mode === 'demo' || demo.enabled) {
    demoTick();
  }

  // Update UI
  updateStats();
  updateAlertTimeline();

  // Charts
  if (latencyChart) {
    latencyChart.draw(state.latencyHistory);
  }
  if (doughnutChart) {
    doughnutChart.draw(state.classificationData.normal, state.classificationData.ddos);
    // Update legend values
    const normalEl = document.getElementById('legend-normal');
    const ddosEl = document.getElementById('legend-ddos');
    if (normalEl) normalEl.textContent = state.classificationData.normal;
    if (ddosEl) ddosEl.textContent = state.classificationData.ddos;
  }
  if (sparkLatency && state.latencyHistory.length > 0) {
    sparkLatency.draw(state.latencyHistory.slice(-20).map(d => d.value), '#00d4ff');
  }

  updateClock();
}


// ============================================================
// INITIALIZATION
// ============================================================
document.addEventListener('DOMContentLoaded', async () => {
  // Init components
  initTopology();
  initCharts();

  // Model button events
  document.querySelectorAll('.model-btn').forEach(btn => {
    btn.addEventListener('click', () => handleModelSwitch(btn.dataset.model));
  });

  // Attack controls
  document.getElementById('btn-launch')?.addEventListener('click', handleLaunchAttack);
  document.getElementById('btn-stop')?.addEventListener('click', handleStopAttack);

  // Connect button
  document.getElementById('btn-connect')?.addEventListener('click', handleConnect);

  // Initial connect attempt
  await handleConnect();

  // Start main loop
  pollTimer = setInterval(mainLoop, POLL_INTERVAL);

  // Initial update
  updateModelButtons();
  updateClock();
  setInterval(updateClock, 1000);
});
