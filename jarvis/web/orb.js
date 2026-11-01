/* The orb: a canvas drawing whose motion is a readout of what Koottu is doing.
   idle      slow breathing, a drifting particle halo
   listening a spectrum ring driven by the real microphone frequencies, ripples on loud moments
   thinking  comets sweeping the ring and a constellation of nodes passing a signal around
   speaking  a rippling rim and a ring that pulses with the words as the voice reads them
   declined  everything settles to grey and the ring drops away
   Reduced motion gets one still frame per state. */

const COLORS = { // core, rim, accent
  idle: [[127, 224, 208], [108, 182, 240], [164, 122, 235]],
  listening: [[240, 176, 74], [255, 138, 92], [255, 214, 130]],
  thinking: [[164, 122, 235], [108, 182, 240], [240, 120, 200]],
  speaking: [[126, 212, 168], [108, 182, 240], [190, 255, 225]],
  declined: [[154, 162, 182], [108, 120, 150], [130, 140, 160]],
};
const TARGET = { // spin: particle drift, wob: blob wobble, bars: ring height, parts: halo energy, think: constellation, speak: rim ripple
  idle: { spin: 0.12, wob: 0.03, bars: 0.12, parts: 0.3, think: 0, speak: 0 },
  listening: { spin: 0.5, wob: 0.05, bars: 1, parts: 1, think: 0, speak: 0 },
  thinking: { spin: 1.3, wob: 0.07, bars: 0.28, parts: 1.2, think: 1, speak: 0 },
  speaking: { spin: 0.6, wob: 0.05, bars: 0.85, parts: 0.8, think: 0, speak: 1 },
  declined: { spin: 0.04, wob: 0.015, bars: 0, parts: 0.08, think: 0, speak: 0 },
};
const BARS = 72, PARTS = 110, NODES = 14, TAU = Math.PI * 2;
const mix = (a, b, k) => a + (b - a) * k;
const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
const mixc = (a, b, k) => [mix(a[0], b[0], k), mix(a[1], b[1], k), mix(a[2], b[2], k)];
const rnd = (() => { let s = 7; return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646; })();

export function createOrb(canvas) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const ctx = canvas.getContext("2d");
  const size = canvas.width, dpr = Math.min(devicePixelRatio || 1, 2);
  canvas.width = canvas.height = size * dpr;
  ctx.scale(dpr, dpr);
  const cx = size / 2, cy = size / 2, R = size * 0.2;

  let state = "idle", level = 0, smooth = 0, env = 0, t = 0, raf = 0, last = 0, spec = null, rippleGap = 0;
  let cur = COLORS.idle.map((c) => [...c]);
  const p = { ...TARGET.idle };
  const bars = new Float32Array(BARS);
  const ripples = [];
  const parts = Array.from({ length: PARTS }, () => ({ a: rnd() * TAU, r: 1.15 + rnd() * 0.95, z: rnd(), v: 0.4 + rnd() * 0.9, ph: rnd() * TAU, px: 0, py: 0 }));

  const barTarget = (i) => {
    const u = i / BARS, a = u * TAU;
    if (state === "listening") {
      const k = i < BARS / 2 ? i : BARS - 1 - i; // mirror so the ring is symmetrical
      const idx = spec ? Math.min(spec.length - 1, 1 + Math.floor(Math.pow(k / (BARS / 2), 1.5) * 90)) : 0;
      const v = spec ? spec[idx] / 255 : 0;
      return Math.max(v * 1.15, smooth * 0.35 * (0.6 + 0.4 * Math.sin(i * 0.7 + t * 5)));
    }
    if (state === "speaking") return env * (0.45 + 0.55 * Math.abs(Math.sin(i * 0.55 + t * 6.5))) * (0.7 + 0.3 * Math.sin(a * 3 - t * 2));
    if (state === "thinking") return 0.12 + 0.9 * (Math.pow(Math.max(0, Math.cos(a - t * 2.4)), 7) + 0.6 * Math.pow(Math.max(0, Math.cos(a + Math.PI - t * 1.7)), 7));
    return 0.1 + 0.06 * Math.sin(i * 0.5 + t * 1.2); // idle breathing
  };

  function draw() {
    ctx.clearRect(0, 0, size, size);
    const kick = 1 + smooth * 0.14 + env * 0.06 * p.speak;
    const rim = cur[1], core = cur[0], acc = cur[2];

    // soft glow behind everything
    ctx.globalCompositeOperation = "lighter";
    const glow = ctx.createRadialGradient(cx, cy, R * 0.5, cx, cy, size / 2); // fades to nothing exactly at the canvas edge
    glow.addColorStop(0, rgba(rim, 0.2 + 0.1 * smooth + 0.06 * env));
    glow.addColorStop(1, rgba(rim, 0));
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, size, size);

    // particle halo with short trails
    for (const q of parts) {
      const ang = q.a + t * p.spin * q.v;
      const rr = R * q.r * (1 + 0.05 * Math.sin(t * 1.3 + q.ph) + smooth * 0.18 * q.z + env * 0.1 * p.speak);
      const x = cx + Math.cos(ang) * rr, y = cy + Math.sin(ang) * rr * 0.94;
      const a = (0.1 + 0.55 * q.z) * Math.min(1, p.parts);
      if (a > 0.02) {
        ctx.strokeStyle = rgba(mixc(rim, acc, q.z), a * 0.5);
        ctx.lineWidth = 0.7 + q.z;
        ctx.beginPath(); ctx.moveTo(q.px || x, q.py || y); ctx.lineTo(x, y); ctx.stroke();
        ctx.fillStyle = rgba(mixc(rim, acc, q.z), a);
        ctx.beginPath(); ctx.arc(x, y, 0.7 + q.z * 1.5, 0, TAU); ctx.fill();
      }
      q.px = x; q.py = y;
    }

    // ripples
    for (let i = ripples.length - 1; i >= 0; i--) {
      const rp = ripples[i];
      const k = (t - rp.t0) / 1.4;
      if (k >= 1) { ripples.splice(i, 1); continue; }
      ctx.strokeStyle = rgba(core, (1 - k) * 0.5 * rp.s);
      ctx.lineWidth = 2.2 * (1 - k) + 0.4;
      ctx.beginPath(); ctx.arc(cx, cy, R * (1.15 + k * 1.5), 0, TAU); ctx.stroke();
    }

    // spectrum ring
    ctx.lineCap = "round";
    for (let i = 0; i < BARS; i++) {
      bars[i] = mix(bars[i], barTarget(i) * p.bars, state === "listening" ? 0.4 : 0.18);
      const a = (i / BARS) * TAU - Math.PI / 2;
      const r0 = R * 1.28 * (1 + smooth * 0.06), len = 3 + bars[i] * R * 0.95;
      const c = mixc(rim, acc, 0.5 + 0.5 * Math.sin(a * 2 + t));
      ctx.strokeStyle = rgba(c, 0.35 + 0.6 * Math.min(1, bars[i] * 1.4));
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
      ctx.lineTo(cx + Math.cos(a) * (r0 + len), cy + Math.sin(a) * (r0 + len));
      ctx.stroke();
    }

    // constellation while thinking
    if (p.think > 0.02) {
      const pts = [];
      for (let i = 0; i < NODES; i++) {
        const a = (i / NODES) * TAU + t * 0.55, r = R * (1.55 + 0.28 * Math.sin(t * 1.3 + i * 1.7));
        pts.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]);
      }
      ctx.lineWidth = 0.8;
      for (let i = 0; i < NODES; i++) for (let j = i + 1; j < NODES; j++) {
        const d = Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]);
        if (d < R * 1.25) { ctx.strokeStyle = rgba(acc, (1 - d / (R * 1.25)) * 0.5 * p.think); ctx.beginPath(); ctx.moveTo(...pts[i]); ctx.lineTo(...pts[j]); ctx.stroke(); }
      }
      pts.forEach(([x, y], i) => {
        const pulse = Math.max(0, 1 - (((t * 3 - i) % NODES) + NODES) % NODES / 3);
        ctx.fillStyle = rgba(mixc(acc, [255, 255, 255], pulse * 0.6), (0.35 + 0.65 * pulse) * p.think);
        ctx.beginPath(); ctx.arc(x, y, 1.6 + pulse * 3.2, 0, TAU); ctx.fill();
      });
    }

    // the fluid core: three stacked blobs, the rim ripples when speaking
    ctx.globalCompositeOperation = "source-over";
    for (let i = 0; i < 3; i++) {
      const scale = (1 - i * 0.09) * kick;
      ctx.beginPath();
      for (let k = 0; k <= 96; k++) {
        const a = (k / 96) * TAU;
        let w = Math.sin(3 * a + t * 1.1 + i * 2.1) + 0.6 * Math.sin(5 * a - t * 0.8 + i * 1.3) + 0.3 * Math.sin(2 * a + t * 1.7);
        w = w * (p.wob + smooth * 0.14) + p.speak * env * 0.11 * Math.sin(9 * a - t * 8 + i);
        const r = R * scale * (1 + w), ang = a + p.think * t * 0.35;
        const x = cx + Math.cos(ang) * r, y = cy + Math.sin(ang) * r;
        k ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.closePath();
      const g = ctx.createRadialGradient(cx - R * 0.25, cy - R * 0.3, R * 0.1, cx, cy, R * 1.3);
      g.addColorStop(0, rgba(core, 0.85 - i * 0.17));
      g.addColorStop(0.6, rgba(rim, 0.5 - i * 0.11));
      g.addColorStop(1, rgba(rim, 0));
      ctx.fillStyle = g;
      ctx.fill();
    }
    const hi = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.35, 0, cx - R * 0.3, cy - R * 0.35, R * 0.7);
    hi.addColorStop(0, "rgba(255,255,255,0.28)");
    hi.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = hi;
    ctx.beginPath(); ctx.arc(cx, cy, R * kick * 1.05, 0, TAU); ctx.fill();
    ctx.strokeStyle = rgba(mixc(core, [255, 255, 255], 0.5), 0.35);
    ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.arc(cx, cy, R * kick * 1.04, 0, TAU); ctx.stroke();
  }

  const goalColors = () => COLORS[state];

  function frame(now) {
    const dt = Math.min((now - last) / 1000 || 0.016, 0.05);
    if (state === "idle" && dt < 0.033 && raf) { raf = requestAnimationFrame(frame); return; } // idle runs at about 30 fps
    last = now;
    t += dt;
    smooth = mix(smooth, level, 0.3);
    // a speech-like envelope: syllable rhythm plus whatever word pulses arrived
    const speechBase = state === "speaking" ? 0.35 + 0.4 * Math.abs(Math.sin(t * 3.4)) * Math.abs(Math.sin(t * 1.3 + 1)) : 0;
    env = Math.max(mix(env, speechBase, 0.2), env * 0.92);
    const k = 1 - Math.pow(0.001, dt), tg = TARGET[state], goal = goalColors();
    for (const key in tg) p[key] = mix(p[key], tg[key], k * 1.4);
    cur.forEach((c, i) => c.forEach((_, j) => { c[j] = mix(c[j], goal[i][j], k); }));
    rippleGap -= dt;
    if (state === "listening" && smooth > 0.32 && rippleGap <= 0) { ripples.push({ t0: t, s: Math.min(1, smooth * 1.6) }); rippleGap = 0.28; }
    draw();
    raf = requestAnimationFrame(frame); // idle keeps breathing at 30 fps; the browser pauses it in a hidden tab
  }

  function kickstart() {
    if (reduced.matches) { cur = COLORS[state].map((c) => [...c]); Object.assign(p, TARGET[state]); draw(); return; }
    if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); }
  }

  draw();
  kickstart();
  return {
    setState(s) { if (s !== state) { state = s; if (s === "declined") ripples.push({ t0: t, s: 1 }); kickstart(); } },
    setLevel(v) { level = v; if (v > 0.01) kickstart(); },
    setSpectrum(a) { spec = a; },
    pulse(s = 1) { env = Math.min(1.2, env + 0.55 * s); if (!reduced.matches) ripples.push({ t0: t, s: 0.5 * s }); kickstart(); },
  };
}
