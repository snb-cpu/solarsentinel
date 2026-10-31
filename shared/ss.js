/* SolarSentinel shared front-end code. Plain script, no build step, no libraries.
   Used by the customer app, the ML console and the hardware console.
   API address, in this order: ?api=... (and remembered), window.SS_API (shared/config.js), the page's own address when
   it is served by the API on port 8000, the remembered ?api=, else http://localhost:8000. */
(function () {
  'use strict';
  const SS = (window.SS = {});
  const q = new URLSearchParams(location.search);

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode: fine */ } },
  };
  SS.store = store;
  SS.query = q;

  /* ---------- API ---------- */
  let api = q.get('api');
  if (api) store.set('ss_api', api);
  api = api || window.SS_API || (/^https?:$/.test(location.protocol) && location.port === '8000' ? location.origin : '') || store.get('ss_api') || 'http://localhost:8000';
  SS.api = api.replace(/\/+$/, '');
  SS.local = !q.get('api') && !window.SS_API && location.port === '8100';   // served by the simulator itself
  SS.get = (path) => fetch(SS.api + path, { cache: 'no-store' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  SS.post = (path, body) => fetch(SS.api + path, { method: 'POST', body: JSON.stringify(body || {}) });   // text/plain, so no CORS preflight

  /* Live snapshots: server-sent events, with a plain poll as the safety net.
     A hidden tab closes its stream after 20 s, so forgotten tabs do not use up the Cloudflare quota. */
  SS.feed = function (onSnap, onState) {
    let es = null, hideT = null, last = 0;
    const say = (s) => onState && onState(s);
    function open() {
      if (es) return;
      es = new EventSource(SS.api + '/events');
      es.onopen = () => say('live');
      es.onmessage = (e) => { last = Date.now(); say('live'); try { onSnap(JSON.parse(e.data)); } catch (err) { console.error(err); } };
      es.onerror = () => {
        say('retrying');
        if (es && es.readyState === 2) { es = null; setTimeout(open, 3000); }
      };
    }
    setInterval(async () => {
      if (document.hidden || Date.now() - last < 4000) return;
      try { const m = await SS.get('/api/state'); last = Date.now(); say('polling'); onSnap(m); } catch (e) { say('offline'); }
    }, 2500);
    document.addEventListener('visibilitychange', () => {
      clearTimeout(hideT);
      if (document.hidden) hideT = setTimeout(() => { if (es) { es.close(); es = null; } }, 20000);
      else open();
    });
    open();
  };

  /* ---------- small helpers ---------- */
  const nf = (n, d = 0) => Number(n).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });
  SS.fmt = {
    n: nf,
    w: (w) => nf(w, 0) + ' W',
    mw: (m) => (m >= 1000 ? nf(m / 1000, 2) + ' W' : (m < 10 ? nf(m, 1) : nf(m, 0)) + ' mW'),
    inr: (v) => '₹' + nf(v, 0),
    ago: (s) => (s == null ? 'never' : s < 1.5 ? 'just now' : s < 90 ? Math.round(s) + ' s ago' : Math.round(s / 60) + ' min ago'),
    time: (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  };
  SS.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  SS.html = (h) => { const t = document.createElement('template'); t.innerHTML = h.trim(); return t.content.firstElementChild; };
  SS.sun = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="5" fill="#FFC21A" stroke="currentColor" stroke-width="2"/><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3M4.6 4.6l2.1 2.1M17.3 17.3l2.1 2.1M4.6 19.4l2.1-2.1M17.3 6.7l2.1-2.1" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/></svg>';

  /* ---------- panel states ---------- */
  SS.STATE = { ok: 'Healthy', dust: 'Dusty', shading: 'Shaded', hotspot: 'Hot cell', fault: 'Cracked cell', washing: 'Washing', drying: 'Drying', asleep: 'Asleep', offline: 'Offline' };
  SS.chip = (key, text) => `<span class="state s-${key}"><i></i>${SS.esc(text || SS.STATE[key] || key)}</span>`;
  SS.panelStatus = (p) => {
    const r = p.reading || {}, d = p.decision || {};
    if (p.mode === 'sleep') return 'asleep';
    if (p.age_s > 8) return 'offline';
    if (r.clean_state === 1) return 'washing';
    if (r.clean_state === 2) return 'drying';
    return d.state || 'ok';
  };
  const list = (a) => (a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]);
  /* One plain sentence about the whole plant, most urgent thing first. */
  SS.headline = (m) => {
    const P = m.panels || [];
    if (!P.length) return { tone: 'asleep', title: 'Waiting for the panels', body: 'No panel has reported yet.' };
    const by = {};
    P.forEach((p) => { (by[SS.panelStatus(p)] = by[SS.panelStatus(p)] || []).push(p.id); });
    const inr = Math.round((m.site && m.site.loss_inr_per_day) || 0);
    if (by.offline) return { tone: 'fault', title: list(by.offline) + (by.offline.length > 1 ? ' have' : ' has') + ' stopped reporting', body: 'Check the power and Wi-Fi at the panel node.' };
    if (by.fault || by.hotspot) {
      const ids = (by.fault || []).concat(by.hotspot || []);
      return { tone: 'fault', title: list(ids) + (ids.length > 1 ? ' have' : ' has') + ' a damaged cell', body: 'A wash cannot fix it, so no water is used. Send a technician.' };
    }
    if (by.washing || by.drying) {
      const ids = (by.washing || []).concat(by.drying || []);
      return { tone: 'washing', title: list(ids) + (ids.length > 1 ? ' are' : ' is') + ' being washed', body: 'Water first, then the blower dries the glass.' };
    }
    if (by.dust) return { tone: 'dust', title: list(by.dust) + (by.dust.length > 1 ? ' are' : ' is') + ' dusty', body: 'Dust is costing about ' + SS.fmt.inr(inr) + ' a day. The AI washes when that is worth more than the wash.' };
    if (by.shading) return { tone: 'shading', title: list(by.shading) + (by.shading.length > 1 ? ' are' : ' is') + ' in shade', body: 'That is a shadow or a cloud, not dirt, so there is no wash.' };
    if (by.asleep && by.asleep.length === P.length) {
      const rain = P.some((p) => p.sleep && p.sleep.reason === 'rain');
      return { tone: 'asleep', title: rain ? 'It is raining. The panels are asleep.' : 'It is dark. The panels are asleep.', body: rain ? 'The rain is washing the panels and filling the tank.' : 'They wake by themselves when the sun is up. Sleeping keeps the node from using the energy it saves.' };
    }
    return { tone: 'ok', title: 'All ' + P.length + ' panels are clean and producing', body: 'Nothing needs doing.' };
  };

  /* ---------- theme ---------- */
  SS.theme = (btn) => {
    const set = (t) => { document.documentElement.dataset.theme = t; store.set('ss_theme', t); if (btn) { btn.textContent = t === 'dark' ? 'Light mode' : 'Dark mode'; btn.setAttribute('aria-pressed', t === 'dark'); } };
    set(store.get('ss_theme') === 'dark' ? 'dark' : 'light');
    if (btn) btn.onclick = () => set(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  };

  /* ---------- heat map: smooth, relative to the panel's own median, blue = cooler, red = hotter ---------- */
  const RAMP = [[-1, [31, 78, 153]], [-0.6, [92, 143, 208]], [-0.25, [183, 208, 234]], [0, [239, 237, 230]], [0.25, [246, 201, 163]], [0.55, [238, 138, 84]], [0.8, [217, 70, 26]], [1, [142, 27, 18]]];
  const ramp = (t) => {
    t = Math.max(-1, Math.min(1, t));
    for (let k = 1; k < RAMP.length; k++) {
      if (t <= RAMP[k][0]) { const [a, ca] = RAMP[k - 1], [b, cb] = RAMP[k], u = (t - a) / (b - a); return ca.map((c, j) => c + (cb[j] - c) * u); }
    }
    return RAMP[RAMP.length - 1][1];
  };
  const scaleOf = (temps) => {
    const s = temps.flat().sort((a, b) => a - b), med = s[Math.floor(s.length / 2)];
    return { med, lo: Math.max(5, med - s[0]), hi: Math.max(7, s[s.length - 1] - med), min: s[0], max: s[s.length - 1] };
  };
  const tOf = (v, sc) => (v >= sc.med ? Math.min(1, (v - sc.med) / sc.hi) : -Math.min(1, (sc.med - v) / sc.lo));
  const off = document.createElement('canvas'); off.width = 96; off.height = 48;
  const octx = off.getContext('2d');
  function drawHeat(cv, temps, pulse) {
    const R = temps.length, C = temps[0].length, dpr = window.devicePixelRatio || 1;
    const W = Math.max(2, Math.round(cv.clientWidth * dpr)), H = Math.max(2, Math.round(cv.clientHeight * dpr));
    if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
    const sc = scaleOf(temps), img = octx.createImageData(96, 48), sig = 0.17, rgbAt = [];
    for (let y = 0; y < 48; y++) for (let x = 0; x < 96; x++) {
      const u = (x + 0.5) / 96, v = (y + 0.5) / 48; let sw = 0, st = 0;
      for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) {
        const dx = u - (c + 0.5) / C, dy = (v - (r + 0.5) / R) * 0.5, w = Math.exp(-(dx * dx + dy * dy) / (2 * sig * sig));
        sw += w; st += w * temps[r][c];
      }
      const rgb = ramp(tOf(st / sw, sc)), i = (y * 96 + x) * 4;
      img.data[i] = rgb[0]; img.data[i + 1] = rgb[1]; img.data[i + 2] = rgb[2]; img.data[i + 3] = 255; rgbAt.push(rgb);
    }
    octx.putImageData(img, 0, 0);
    const ctx = cv.getContext('2d');
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(off, 0, 0, W, H);
    ctx.strokeStyle = 'rgba(22,25,28,.30)'; ctx.lineWidth = 1.5 * dpr;
    for (let c = 1; c < C; c++) { ctx.beginPath(); ctx.moveTo(W * c / C, 0); ctx.lineTo(W * c / C, H); ctx.stroke(); }
    for (let r = 1; r < R; r++) { ctx.beginPath(); ctx.moveTo(0, H * r / R); ctx.lineTo(W, H * r / R); ctx.stroke(); }
    const fs = Math.max(13, Math.min(20, H / dpr / 8.5)) * dpr;
    ctx.font = `700 ${fs}px "Atkinson Hyperlegible Next",system-ui,sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
    let hot = null;
    for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) {
      const x = W * (c + 0.5) / C, y = H * (r + 0.5) / R, t = temps[r][c];
      const rgb = rgbAt[Math.min(47, Math.floor(y / H * 48)) * 96 + Math.min(95, Math.floor(x / W * 96))];
      const dark = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255 < 0.5;
      ctx.fillStyle = dark ? '#fff' : '#16191C'; ctx.strokeStyle = dark ? 'rgba(0,0,0,.35)' : 'rgba(255,255,255,.55)'; ctx.lineWidth = 4 * dpr;
      ctx.beginPath(); ctx.arc(x, y - fs * 0.95, 2.6 * dpr, 0, 7); ctx.fill();
      ctx.strokeText(t.toFixed(1) + '°', x, y + fs * 0.1); ctx.fillText(t.toFixed(1) + '°', x, y + fs * 0.1);
      if (t === sc.max && sc.max - sc.med > 4) hot = [x, y];
    }
    if (hot) {
      const rad = H / 5 + (pulse || 0) * H / 40;
      ctx.lineWidth = 5 * dpr; ctx.strokeStyle = '#16191C'; ctx.beginPath(); ctx.arc(hot[0], hot[1], rad, 0, 7); ctx.stroke();
      ctx.lineWidth = 2.5 * dpr; ctx.strokeStyle = '#fff'; ctx.beginPath(); ctx.arc(hot[0], hot[1], rad, 0, 7); ctx.stroke();
    }
    return sc;
  }
  SS.heat = {
    ramp, scaleOf, tOf,
    /* attach to a canvas; call .set(temps) with each new reading */
    mount(cv) {
      let temps = null, pulse = 0, sc = null;
      const redraw = () => { if (temps) sc = drawHeat(cv, temps, pulse); return sc; };
      if (window.ResizeObserver) new ResizeObserver(redraw).observe(cv);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(redraw);
      setInterval(() => { if (sc && sc.max - sc.med > 4 && !document.hidden) { pulse = (Math.sin(Date.now() / 280) + 1) / 2; redraw(); } }, 120);
      return { set(t) { temps = t; return redraw(); } };
    },
    /* nine swatches plus the real temperatures they stand for */
    legend(el, sc) {
      if (!sc) return;
      el.innerHTML = `<span class="num">${(sc.med - sc.lo).toFixed(0)}° and cooler</span><span class="sw">${[-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1].map((t) => `<i style="background:rgb(${ramp(t).map(Math.round)})"></i>`).join('')}</span><span class="num">${(sc.med + sc.hi).toFixed(0)}° and hotter</span>`;
    },
  };

  /* ---------- charts (SVG drawn at the real pixel width, so text stays readable) ---------- */
  const nice = (v) => { const p = Math.pow(10, Math.floor(Math.log10(v))), f = v / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p; };
  function tipFor(el) {
    let t = el.querySelector('.tip');
    if (!t) { t = document.createElement('div'); t.className = 'tip'; t.hidden = true; el.appendChild(t); }
    return t;
  }
  SS.chart = {
    /* data: [{p: watts, c: true if a wash just finished}] */
    line(el, data, opt) {
      opt = opt || {};
      const W = el.clientWidth || 560, H = opt.h || 230, m = { l: 52, r: 16, t: 16, b: 30 }, n = data.length;
      if (n < 2) { el.innerHTML = '<p class="empty">Collecting data…</p>'; return; }
      const max = nice(Math.max(...data.map((d) => d.p), opt.min || 50) * 1.08), unit = opt.unit || 'W';
      const X = (i) => m.l + i * (W - m.l - m.r) / (n - 1), Y = (v) => H - m.b - v / max * (H - m.t - m.b);
      let g = '', mk = '', lastX = -99;
      [0, 0.5, 1].forEach((f) => { const y = Y(max * f); g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}"/><text x="${m.l - 8}" y="${y + 4}" text-anchor="end">${SS.fmt.n(max * f)}${f === 1 ? ' ' + unit : ''}</text>`; });
      data.forEach((d, i) => {
        if (d.c && X(i) - lastX > 70) {
          lastX = X(i); const near = X(i) > W - m.r - 60;      // keep the word inside the chart near the right edge
          mk += `<line x1="${X(i)}" x2="${X(i)}" y1="${m.t}" y2="${H - m.b}"/><text x="${near ? X(i) - 5 : X(i) + 5}" y="${m.t + 11}"${near ? ' text-anchor="end"' : ''}>washed</text>`;
        }
      });
      const pts = data.map((d, i) => `${X(i).toFixed(1)},${Y(d.p).toFixed(1)}`).join(' '), last = data[n - 1];
      let svg = el.querySelector('svg');
      const html = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${SS.esc(opt.label || 'Power over time')}"><g class="g">${g}</g><g class="mk">${mk}</g><polyline class="ln" points="${pts}"/>` +
        `<circle cx="${X(n - 1)}" cy="${Y(last.p)}" r="5" fill="var(--ink)" stroke="var(--paper)" stroke-width="2"/><text x="${m.l}" y="${H - 8}">earlier</text><text x="${W - m.r}" y="${H - 8}" text-anchor="end">now</text><line id="xh" y1="${m.t}" y2="${H - m.b}" stroke="var(--ink3)" stroke-dasharray="3 3" visibility="hidden"/></svg>`;
      const keep = el.querySelector('.tip'); el.innerHTML = html; if (keep) el.appendChild(keep);
      const tip = tipFor(el);
      el.onpointermove = (e) => {
        const r = el.getBoundingClientRect(), x = e.clientX - r.left, i = Math.max(0, Math.min(n - 1, Math.round((x - m.l) / (W - m.l - m.r) * (n - 1))));
        const xh = el.querySelector('#xh'); xh.setAttribute('x1', X(i)); xh.setAttribute('x2', X(i)); xh.setAttribute('visibility', 'visible');
        tip.hidden = false; tip.style.left = X(i) + 'px'; tip.style.top = Y(data[i].p) + 'px';
        tip.textContent = SS.fmt.n(data[i].p) + ' ' + unit + (data[i].c ? ', wash finished' : '') + (i === n - 1 ? ' (now)' : '');
      };
      el.onpointerleave = () => { tip.hidden = true; const xh = el.querySelector('#xh'); if (xh) xh.setAttribute('visibility', 'hidden'); };
    },
    /* now[]: with today's dirt, clean[]: if the panels were clean, both kWh per day */
    bars(el, now, clean, opt) {
      opt = opt || {};
      const W = el.clientWidth || 560, H = opt.h || 230, m = { l: 8, r: 8, t: 26, b: 34 }, n = now.length;
      if (!n) { el.innerHTML = '<p class="empty">No forecast yet.</p>'; return; }
      const max = Math.max(...now, ...(clean || []), 1) * 1.05, slot = (W - m.l - m.r) / n, bw = Math.min(46, slot * 0.56);
      const labels = opt.labels || now.map((_, i) => (i === 0 ? 'Today' : new Date(Date.now() + i * 864e5).toLocaleDateString('en-IN', { weekday: 'short' }))), base = H - m.b;
      let s = `<line x1="${m.l}" x2="${W - m.r}" y1="${base}" y2="${base}" stroke="var(--ink)" stroke-width="1.5"/>`;
      now.forEach((v, i) => {
        const cx = m.l + slot * (i + 0.5), x = cx - bw / 2, hN = v / max * (base - m.t), c = (clean && clean[i]) || v, hC = c / max * (base - m.t);
        s += `<rect x="${x}" y="${base - hC}" width="${bw}" height="${hC}" fill="none" stroke="var(--ink3)" stroke-width="1.5" stroke-dasharray="4 3"/>` +
          `<rect x="${x}" y="${base - hN}" width="${bw}" height="${hN}" fill="var(--ink2)"/>` +
          `<text x="${cx}" y="${base - Math.max(hN, hC) - 7}" text-anchor="middle" style="font-weight:700;fill:var(--ink)">${v.toFixed(1)}</text>` +
          `<text x="${cx}" y="${H - 10}" text-anchor="middle">${SS.esc(labels[i] || '')}</text><rect class="hit" data-i="${i}" x="${cx - slot / 2}" y="0" width="${slot}" height="${H}" fill="transparent"/>`;
      });
      const keep = el.querySelector('.tip'); el.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${SS.esc(opt.label || 'Seven day forecast')}">${s}</svg>`; if (keep) el.appendChild(keep);
      const tip = tipFor(el);
      el.onpointermove = (e) => {
        const h = e.target.closest && e.target.closest('.hit'); if (!h) return;
        const i = +h.dataset.i, c = (clean && clean[i]) || now[i], lost = Math.max(0, c - now[i]);
        tip.hidden = false; tip.style.left = (m.l + slot * (i + 0.5)) + 'px'; tip.style.top = (base - Math.max(now[i], c) / max * (base - m.t) - 18) + 'px';
        tip.textContent = `${labels[i]}: ${now[i].toFixed(1)} kWh with today's dirt, ${c.toFixed(1)} kWh if clean` + (lost > 0.04 ? `, ${lost.toFixed(1)} kWh lost` : '');
      };
      el.onpointerleave = () => { tip.hidden = true; };
    },
  };

  /* ---------- demo controls: the same buttons everywhere ---------- */
  SS.controls = function (root, send, opt) {
    opt = opt || {};
    const SPEEDS = [[0, 'Pause'], [1, '1×'], [10, '10×'], [60, '60×'], [120, '120×'], [300, '300×'], [1200, '1200×']];
    const btn = (attrs, text) => `<button class="btn sm" ${attrs} aria-pressed="false">${text}</button>`;
    let S = null, sel = opt.sel || 0, built = 0;
    function build(n) {
      built = n;
      root.classList.add('ctl');
      root.innerHTML =
        (opt.panelPicker === false ? '' : `<h3>Panel</h3><div class="row" data-k="pick">${Array.from({ length: n }, (_, i) => btn(`data-p="${i}"`, 'P' + (i + 1))).join('')}</div>`) +
        `<h3>Cause trouble on <span data-k="name"></span></h3><p class="hint">Dirt, faults and weather the simulator puts on the panel.</p><div class="row">` +
        [['cloud', 'Passing cloud'], ['dirty', 'Make dirty now'], ['bird', 'Bird dropping'], ['shade', 'Shade', 'f'], ['hotspot', 'Hotspot', 'f'], ['crack', 'Cracked cell', 'f'], ['drain', 'Drain the tank'], ['repair', 'Repair faults']]
          .map(([c, t, f]) => btn(`data-c="${c}"` + (f ? ` data-f="${c}"` : ''), t)).join('') + '</div>' +
        '<h3>Whole site</h3><div class="row">' +
        [['storm', 'Dust storm (1 h)', 'storm'], ['rain_forecast', 'Rain forecast', 'forecast_rain'], ['rain_now', 'Start rain now'], ['timer', '2 h backup timer', 'timer']]
          .map(([c, t, g]) => btn(`data-c="${c}"` + (g ? ` data-g="${g}"` : ''), t)).join('') + '</div>' +
        '<h3>Skip ahead</h3><p class="hint">The day and night logic runs the whole way.</p><div class="row">' +
        [[7.3, 'To morning'], [12, 'To noon'], [17.5, 'To dusk'], [20, 'To night']].map(([v, t]) => btn(`data-c="skip" data-v="${v}"`, t)).join('') + '</div>' +
        '<h3>Time scale</h3><div class="row">' + SPEEDS.map(([v, t]) => btn(`data-c="speed" data-v="${v}" data-s="${v}"`, t)).join('') + '</div><p class="hint" data-k="speed" style="margin:8px 0 0"></p>';
    }
    root.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.p !== undefined) { sel = +b.dataset.p; if (opt.onSelect) opt.onSelect(sel); if (S) update(S); }
      else if (b.dataset.c) send(b.dataset.c, b.dataset.v !== undefined ? { value: +b.dataset.v } : {});
    });
    function update(s) {
      S = s;
      const n = (s.panels || []).length || 3;
      if (built !== n) build(n);
      if (sel >= n) sel = 0;
      const nm = root.querySelector('[data-k=name]'); if (nm) nm.textContent = (s.panels[sel] || {}).id || 'P' + (sel + 1);
      root.querySelectorAll('[data-p]').forEach((b) => b.setAttribute('aria-pressed', +b.dataset.p === sel));
      const f = ((s.panels || [])[sel] || {}).faults || {};
      root.querySelectorAll('[data-f]').forEach((b) => b.setAttribute('aria-pressed', !!f[b.dataset.f]));
      root.querySelectorAll('[data-g]').forEach((b) => b.setAttribute('aria-pressed', !!s[b.dataset.g]));
      root.querySelectorAll('[data-s]').forEach((b) => b.setAttribute('aria-pressed', +b.dataset.s === s.speed));
      const sp = root.querySelector('[data-k=speed]');
      if (sp) sp.textContent = s.speed === 0 ? 'Paused.' : `${s.speed}×: one real second is ${s.speed >= 60 ? (s.speed / 60).toFixed(1) + ' simulated minutes' : s.speed + ' simulated seconds'}, so a whole day takes ${(86400 / s.speed / 60).toFixed(1)} real minutes.`;
    }
    return { update, get sel() { return sel; }, set sel(v) { sel = v; if (S) update(S); } };
  };

  document.addEventListener('DOMContentLoaded', () => { if (document.fonts && document.fonts.load) document.fonts.load('700 16px "Atkinson Hyperlegible Next"'); });
})();
