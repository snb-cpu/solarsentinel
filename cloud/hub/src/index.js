// SolarSentinel hub on Cloudflare. One Durable Object holds all the state, so the Mac, Pratham's laptop and every
// web page see the same thing at the same time. It is a port of 2-ml-ai/api/server.py and keeps the same contract
// (docs/contract.md). If you change one, change the other.
import { DurableObject } from "cloudflare:workers";

const ARRAY_KW = 1.5, PEAK_SUN_H = 4.8, TARIFF_INR = 8.0, CLEAN_COST_INR = 2.0;
const ISC_A = 5.5, MIN_LUX = 20000, CMD_COOLDOWN_S = 30;
const TANK_L = 20.0, SPRAY_L_S = 0.2, TAP_L_S = 0.17, MIN_TANK_PCT = 20;
const ML_STALE_S = 8, ML_POLL_GRACE_S = 25, SETTLE_S = 25;
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" };
const MACHINE_POST = new Set(["/api/reading", "/api/status", "/api/weather", "/api/decision", "/api/simstate", "/api/sync"]);
const MACHINE_GET = new Set(["/api/command", "/api/ml/poll", "/api/simcmd"]);

const now = () => Date.now() / 1000;
const rnd = (x, n = 0) => { const f = 10 ** n; return Math.round(x * f) / f; };
const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
const hhmmss = () => new Date(Date.now() + 19800000).toISOString().slice(11, 19);       // India time, for people reading the log
const sum = (a) => a.reduce((x, y) => x + y, 0);

function builtinDecide(r, rain, ctx) {
  ctx = ctx || {};
  const t = r.temps_c, flat = t.flat(), med = [...flat].sort((a, b) => a - b)[Math.floor(flat.length / 2)], spread = Math.max(...flat) - med;
  const base = { panel_id: r.panel_id, heatmap: t.map((row) => row.map((x) => rnd(Math.min(1, Math.max(0, (x - med) / 12)), 2))), clean_cost_inr: CLEAN_COST_INR };
  if (r.ldr_lux < MIN_LUX) return { ...base, state: "ok", efficiency_loss_pct: 0.0, clean_now: false, loss_inr_per_day: 0.0, reason: "Low sunlight (night or heavy cloud). Analysis paused." };
  const expI = ISC_A * r.ldr_lux / 100000, corners = r.ldr_corners_lux || [];
  const uneven = corners.length > 1 && (Math.max(...corners) - Math.min(...corners)) / Math.max(mean(corners), 1) > 0.25;
  const loss = Math.max(0.0, (1 - r.current_a / expI) * 100);
  const cols = t[0].map((_, c) => mean(t.map((row) => row[c])));
  const hot = spread > 3 + 3 * Math.min(1, r.ldr_lux / 80000);
  let state;
  if (hot && !ctx.washed_hot) state = "dust";
  else if (hot && now() < (ctx.settle_until || 0)) state = "dust";
  else if (hot) state = loss > 12 ? "fault" : "hotspot";
  else if (uneven && loss > 3) state = "shading";
  else if (Math.min(...cols) < mean(flat) - 2 && loss > 20) state = "shading";
  else if (loss > 3) state = "dust";
  else state = "ok";
  const inr = loss / 100 * ARRAY_KW * PEAK_SUN_H * TARIFF_INR;
  if (state === "dust" && hot) {
    const go = !ctx.washed_hot;
    return { ...base, state, efficiency_loss_pct: rnd(loss, 1), clean_now: go, reason: go ? "Local hot patch, probably a bird dropping or dirt. Washing first to find out." : "Washed. Waiting for the panel to cool, then checking if the hot spot is gone.", loss_inr_per_day: rnd(inr, 1), hot: true };
  }
  let go, why;
  if (state === "fault" || state === "hotspot") [go, why] = [false, "A cell is overheating and washing will not fix it. No water used. Send a technician."];
  else if (state === "shading") [go, why] = [false, uneven ? "Uneven light across the panel (a shadow or passing cloud), not dirt. No wash." : "Part of the panel is in shade, not dirt. Washing will not help."];
  else if (state === "ok") [go, why] = [false, "Panel is clean and producing as expected."];
  else if (rain) [go, why] = [false, "Dust detected, but rain is forecast within 48 h. Letting the rain clean it."];
  else if (0 <= (r.tank_level_pct ?? 100) && (r.tank_level_pct ?? 100) < MIN_TANK_PCT) [go, why] = [false, "Dust detected, but the water tank is low. Refilling it from the tap first."];
  else if (inr > CLEAN_COST_INR) [go, why] = [true, `Dust is costing Rs ${inr.toFixed(0)}/day, more than the Rs ${CLEAN_COST_INR.toFixed(0)} wash. Cleaning now.`];
  else [go, why] = [false, "Dust loss is still smaller than the cost of a wash."];
  return { ...base, state, efficiency_loss_pct: rnd(loss, 1), clean_now: go, reason: why, loss_inr_per_day: rnd(inr, 1), hot };
}

export class Hub extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.p = {};
    this.weather = { rain_48h: false, day_factor: [1, 0.95, 0.9, 1, 1, 0.9, 1], ambient_c: null, raining: false };
    this.siteHist = []; this.washed = false; this.log = []; this.feed = []; this.simq = []; this.sim = null;
    this.clients = new Set(); this.ticker = null;                         // open /events streams
    this.mlseq = 0; this.mlbuf = []; this.mlWaiters = []; this.mlPollAt = 0;
    this.savedAt = 0;
    ctx.blockConcurrencyWhile(async () => {                              // survive the object being evicted from memory
      const s = await ctx.storage.get("state");
      if (s) Object.assign(this, s); else this.say("API started. Waiting for the panel nodes.");
    });
  }

  // ---------- small things ----------
  say(m) { this.log.push({ t: hhmmss(), ts: rnd(now(), 1), msg: m }); this.log = this.log.slice(-40); }
  mlConnected() { return now() - this.mlPollAt < ML_POLL_GRACE_S; }
  save() {
    if (now() - this.savedAt < 5) return;
    this.savedAt = now();
    const { p, weather, siteHist, washed, log, feed, simq, sim, mlseq } = this;
    this.ctx.storage.put("state", { p, weather, siteHist, washed, log, feed, simq, sim, mlseq }).catch(() => {});
  }
  json(body, code = 200) { return new Response(JSON.stringify(body), { status: code, headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": "no-store" } }); }

  // ---------- the brain: same steps as server.py ----------
  queueClean(pid, why) {
    const st = this.p[pid];
    st.pending = { action: "clean", water_ms: 4000, air_ms: 8000, why }; st.last_cmd = now();
    this.say(`${pid}: clean command sent (${why})`);
  }
  onReading(r) {
    const pid = r.panel_id || "P1";
    r.ts = new Date().toISOString().replace(/\.\d+Z$/, "Z");
    if (!this.p[pid]) {
      this.p[pid] = { washed_hot: false, settle_until: 0.0, reading: null, decision: null, source: "rules", ml_at: 0.0, mode: "active", sleep: null, rx: 0.0, history: [], pending: null, last_cmd: 0.0, prev_cs: 0, was_hot: false };
      this.say(`${pid}: node connected.`);
    }
    const st = this.p[pid]; st.rx = now(); st.reading = r;
    if (st.mode === "sleep") { this.say(`${pid}: woke up (daylight and dry).`); st.mode = "active"; st.sleep = null; }
    const cs = r.clean_state || 0, done = st.prev_cs === 2 && cs === 0;
    if (done) {
      this.say(`${pid}: cleaning finished.`); this.washed = true;
      if (st.was_hot) { st.washed_hot = true; st.settle_until = now() + SETTLE_S; }
    }
    if (cs !== st.prev_cs && cs === 1) this.say(`${pid}: water flush`);
    if (cs !== st.prev_cs && cs === 2) this.say(`${pid}: air dry`);
    st.prev_cs = cs;
    st.history.push({ p: rnd(r.voltage_v * r.current_a, 1), c: done }); st.history = st.history.slice(-90);
    if (pid === Object.keys(this.p).sort()[0]) {                         // one site-power point per round of readings
      this.siteHist.push({ p: rnd(sum(Object.values(this.p).map((x) => (x.history.length ? x.history[x.history.length - 1].p : 0))), 1), c: this.washed });
      this.siteHist = this.siteHist.slice(-90); this.washed = false;
    }
    const ml = this.mlConnected();
    if (ml) this.mlSend({ reading: r, weather: this.weather });          // the ML program decides...
    if (!(ml && now() - st.ml_at < ML_STALE_S)) {                        // ...unless it is offline or silent
      if (st.source === "ml") { this.say(`${pid}: ML program not answering, using built-in rules.`); st.source = "rules"; }
      const d = builtinDecide(r, this.weather.rain_48h, st); st.was_hot = !!d.hot;
      if (!d.hot && now() > st.settle_until) st.washed_hot = false;
      this.apply(pid, st, d);
    }
    this.push();
  }
  apply(pid, st, d) {
    const f = this.weather.day_factor, loss = d.efficiency_loss_pct;
    if ((d.forecast_kwh_7d || []).length !== 7 || !d.forecast_kwh_7d.some((x) => x)) {
      d.forecast_clean_kwh_7d = f.map((x) => rnd(ARRAY_KW * PEAK_SUN_H * x, 2));
      d.forecast_kwh_7d = d.forecast_clean_kwh_7d.map((c) => rnd(c * (1 - loss / 100), 2));
    }
    const prev = st.decision; st.decision = d;
    if (!prev || prev.state !== d.state || prev.clean_now !== d.clean_now) {   // the feed shows changes, not every reading
      this.feed.push({ ts: rnd(now(), 1), panel: pid, state: d.state, clean_now: d.clean_now, loss: d.efficiency_loss_pct, inr: d.loss_inr_per_day, reason: d.reason, source: st.source });
      this.feed = this.feed.slice(-60);
    }
    if (d.clean_now && st.prev_cs === 0 && !st.pending && now() - st.last_cmd > CMD_COOLDOWN_S) this.queueClean(pid, "AI decision: " + d.reason);
  }
  onStatus(b) {
    const st = this.p[b.panel_id];
    if (!st || b.mode !== "sleep") return;
    const why = { dark: "it is dark or heavily overcast", rain: "it is raining" }[b.reason] || b.reason;
    this.say(`${b.panel_id}: going to sleep because ${why}. Radio and sensors off; it looks at the sun every ${Math.floor((b.wake_s || 0) / 60)} min.`);
    st.mode = "sleep"; st.sleep = { reason: b.reason, wake_s: b.wake_s, since: now() };
    this.push();
  }
  onDecision(d) {
    const st = this.p[d.panel_id];
    if (!st || !("state" in d)) return;
    if (st.source !== "ml") { this.say(`${d.panel_id}: decisions now come from the ML program.`); st.source = "ml"; }
    st.ml_at = now(); this.apply(d.panel_id, st, d);
    this.push();
  }
  setWeather(body) {
    if (body.rain_48h !== this.weather.rain_48h) this.say(body.rain_48h ? "Weather feed: rain expected within 48 h" : "Weather feed: no rain expected");
    this.weather = body;
  }
  takeCommand(pid) {
    const st = this.p[pid], c = st && st.pending ? st.pending : {};
    if (st) st.pending = null;
    return { ...c, tap_hold: !!this.weather.rain_48h };
  }
  onSync(b) {
    for (const s of b.status || []) this.onStatus(s);
    if (b.weather) this.setWeather(b.weather);
    if (b.simstate != null) this.sim = b.simstate;
    for (const r of b.readings || []) this.onReading(r);
    const commands = {};
    for (const pid of b.panels || []) commands[pid] = this.takeCommand(pid);
    const simcmds = this.simq; this.simq = [];
    return { commands, simcmds };
  }
  onSim(body) {
    this.simq.push(body);
    const per = ["bird", "dirty", "shade", "hotspot", "crack", "repair"].includes(body.cmd);
    this.say(`Demo control: ${body.cmd}` + (per ? ` on panel ${parseInt(body.panel || 0, 10) + 1}` : ""));
  }
  onClean(body) {
    const ids = body.panel_id && this.p[body.panel_id] ? [body.panel_id] : Object.keys(this.p);
    for (const pid of ids) { const st = this.p[pid]; if (!st.pending && st.prev_cs === 0) this.queueClean(pid, "customer pressed Clean now"); }
  }

  // ---------- the ML program's long poll ----------
  mlSend(msg) {
    this.mlseq += 1; this.mlbuf = [...this.mlbuf, [this.mlseq, msg]].slice(-200);
    const w = this.mlWaiters; this.mlWaiters = [];
    w.forEach((x) => { clearTimeout(x.t); x.res(); });
  }
  async mlPoll(since, wait) {
    this.mlPollAt = now();
    if (since < 0) return { seq: this.mlseq, msgs: [] };
    if (this.mlseq <= since) await new Promise((res) => { const w = { res, t: setTimeout(() => { this.mlWaiters = this.mlWaiters.filter((x) => x !== w); res(); }, wait * 1000) }; this.mlWaiters.push(w); });
    this.mlPollAt = now();
    return { seq: this.mlseq, msgs: this.mlbuf.filter(([s]) => s > since).map(([, m]) => m) };
  }

  // ---------- what the web pages see ----------
  snapshot() {
    const t = now(), panels = Object.keys(this.p).sort().map((pid) => {
      const x = this.p[pid];
      return { id: pid, mode: x.mode, sleep: x.sleep, source: x.source, reading: x.reading, decision: x.decision, history: x.history, age_s: rnd(t - x.rx, 1), ml_age_s: x.ml_at ? rnd(t - x.ml_at, 1) : null };
    });
    const all = Object.values(this.p), ds = all.map((x) => x.decision).filter(Boolean), rd = all.map((x) => x.reading).filter(Boolean);
    const active = all.filter((x) => x.mode === "active");
    const site = {
      power_w: rnd(sum(active.filter((x) => x.history.length).map((x) => x.history[x.history.length - 1].p)), 1),
      node_mw: rnd(sum(active.filter((x) => x.reading).map((x) => x.reading.node_mw || 0)), 1),
      asleep: all.filter((x) => x.mode === "sleep").length,
      node_wh: rnd(sum(rd.map((r) => r.node_wh || 0)), 3),
      tap_l: rnd(sum(rd.map((r) => r.tap_s || 0)) * TAP_L_S, 1), spray_l: rnd(sum(rd.map((r) => r.spray_s || 0)) * SPRAY_L_S, 1),
      tap_open: rd.filter((r) => r.tap_open).length,
      loss_inr_per_day: rnd(sum(ds.map((d) => d.loss_inr_per_day)), 1), history: this.siteHist,
      forecast_kwh_7d: ds.length ? [0, 1, 2, 3, 4, 5, 6].map((i) => rnd(sum(ds.map((d) => d.forecast_kwh_7d[i])), 1)) : [],
      forecast_clean_kwh_7d: ds.length ? [0, 1, 2, 3, 4, 5, 6].map((i) => rnd(sum(ds.map((d) => d.forecast_clean_kwh_7d[i])), 1)) : [],
    };
    return { panels, site, weather: this.weather, log: this.log, feed: this.feed.slice(-30), ml: all.some((x) => x.source === "ml") ? "ML model" : "built-in rules", ml_connected: this.mlConnected(), sim: this.sim, now: rnd(t, 1),
      econ: { panel_kw: ARRAY_KW, tariff: TARIFF_INR, clean_cost: CLEAN_COST_INR, tank_l: TANK_L, tap_l_s: TAP_L_S, spray_l_s: SPRAY_L_S } };
  }
  push() {
    if (!this.clients.size) return;
    const data = new TextEncoder().encode(`data: ${JSON.stringify(this.snapshot())}\n\n`);
    for (const c of [...this.clients]) c.write(data).catch(() => this.clients.delete(c));
  }
  events() {
    const { readable, writable } = new TransformStream(), w = writable.getWriter();
    this.clients.add(w);
    w.write(new TextEncoder().encode(`data: ${JSON.stringify(this.snapshot())}\n\n`)).catch(() => this.clients.delete(w));
    if (!this.ticker) this.ticker = setInterval(() => { if (!this.clients.size) { clearInterval(this.ticker); this.ticker = null; } else this.push(); }, 1000);
    return new Response(readable, { headers: { ...CORS, "Content-Type": "text/event-stream", "Cache-Control": "no-cache" } });
  }

  // ---------- HTTP ----------
  async fetch(request) {
    const url = new URL(request.url), path = url.pathname, qs = url.searchParams;
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    const key = this.env.KEY, authorized = !key || request.headers.get("X-Key") === key || qs.get("key") === key;
    if (request.method === "GET") {
      if (MACHINE_GET.has(path) && !authorized) return this.json({ error: "key" }, 401);
      if (path === "/events") return this.events();
      if (path === "/api/state") return this.json(this.snapshot());
      if (path === "/api/command") return this.json(this.takeCommand(qs.get("panel") || "P1"));
      if (path === "/api/ml/poll") return this.json(await this.mlPoll(parseInt(qs.get("since") ?? "-1", 10), Math.min(parseFloat(qs.get("wait") ?? "20"), 25)));
      if (path === "/api/simcmd") { const cmds = this.simq; this.simq = []; return this.json({ cmds }); }
      if (path === "/" || path === "") return new Response("SolarSentinel API. Live state: /api/state, live stream: /events. See docs/contract.md.\n", { headers: { ...CORS, "Content-Type": "text/plain; charset=utf-8" } });
      return this.json({ error: "not found" }, 404);
    }
    if (request.method !== "POST") return this.json({ error: "method" }, 405);
    let body;
    try { body = JSON.parse((await request.text()) || "{}"); } catch (e) { return this.json({ error: "bad json" }, 400); }
    if (MACHINE_POST.has(path) && !authorized) return this.json({ error: "key" }, 401);
    let out = {};
    if (path === "/api/reading") this.onReading(body);
    else if (path === "/api/sync") out = this.onSync(body);
    else if (path === "/api/weather") this.setWeather(body);
    else if (path === "/api/decision") (Array.isArray(body) ? body : [body]).forEach((d) => this.onDecision(d));   // one verdict, or a batch
    else if (path === "/api/status") this.onStatus(body);
    else if (path === "/api/sim") this.onSim(body);
    else if (path === "/api/simstate") this.sim = body;
    else if (path === "/api/clean") this.onClean(body);
    else return this.json({ error: "not found" }, 404);
    this.save();
    return this.json(out);
  }
}

// Reached through a service or Durable Object binding from the Pages project (workers.dev is switched off in wrangler.toml).
// ?room=name picks a separate hub (the contract test uses "test"); with no room it is "main", the one everybody shares.
export default {
  async fetch(request, env) { return env.HUB.get(env.HUB.idFromName(new URL(request.url).searchParams.get("room") || "main")).fetch(request); },
};
