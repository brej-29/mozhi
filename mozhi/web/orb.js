/* A signal sphere. Its spectrum and speech impulses come from the app. */
const TAU = Math.PI * 2;
const PALETTES = {
  idle: [125, 235, 195],
  listening: [247, 198, 118],
  thinking: [183, 164, 247],
  speaking: [138, 243, 206],
  declined: [160, 181, 180],
};
export function createOrb(canvas) {
  const ctx = canvas.getContext("2d");
  const size = Math.min(canvas.width, 480),
    dpr = Math.min(devicePixelRatio || 1, 1.5);
  canvas.width = canvas.height = Math.round(size * dpr);
  ctx.scale(dpr, dpr);
  const mid = size / 2,
    R = size * 0.32,
    reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const colors = new Array(36),
    backColors = new Array(36);
  const body = ctx.createRadialGradient(
    mid - R * 0.4,
    mid - R * 0.45,
    0,
    mid,
    mid,
    R * 1.1,
  );
  body.addColorStop(0, "#235548");
  body.addColorStop(0.45, "#12382e");
  body.addColorStop(0.82, "#09251f");
  body.addColorStop(1, "#061412");
  let state = "idle",
    level = 0,
    smooth = 0,
    spectrum = null,
    impulse = 0,
    raf = 0,
    last = 0,
    time = 0,
    visible = true;
  const observer = new IntersectionObserver((entries) => {
    visible = entries[0].isIntersecting;
    resume();
  });
  observer.observe(canvas);
  function palette() {
    const c = PALETTES[state] || PALETTES.idle;
    for (let i = 0; i < 36; i++) {
      colors[i] =
        "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + (0.35 + i / 48) + ")";
      backColors[i] = "rgba(" + c[0] + "," + c[1] + "," + c[2] + ",.10)";
    }
  }
  const glow = ctx.createRadialGradient(mid, mid, 0, mid, mid, size * 0.49);
  glow.addColorStop(0, "rgba(96,216,173,.10)");
  glow.addColorStop(0.65, "rgba(96,216,173,.025)");
  glow.addColorStop(1, "rgba(96,216,173,0)");
  function draw() {
    ctx.clearRect(0, 0, size, size);
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, size, size);
    const energy = smooth * 0.16 + impulse * 0.055,
      spin = time * (state === "thinking" ? 0.52 : 0.12);
    ctx.fillStyle = body;
    ctx.beginPath();
    ctx.ellipse(mid, mid, R, R * 0.965, 0, 0, TAU);
    ctx.fill();
    ctx.lineWidth = 0.85;
    // Latitude ribbons rotate across the near hemisphere. Depth controls their light.
    for (let j = 0; j < 36; j++) {
      const lat = -1.48 + (j / 35) * 2.96,
        y0 = Math.sin(lat),
        radius = Math.cos(lat),
        front = j / 35;
      ctx.beginPath();
      for (let k = 0; k <= 100; k++) {
        const a = (k / 100) * TAU,
          x = radius * Math.cos(a),
          z = radius * Math.sin(a);
        const warp =
          Math.sin(a * 3 + lat * 5 + time * 0.7) * (0.018 + energy) +
          (state === "thinking" ? Math.sin(a * 6 - time * 3) * 0.02 : 0);
        const xx = x * Math.cos(spin) + z * Math.sin(spin),
          zz = z * Math.cos(spin) - x * Math.sin(spin);
        const yy = y0 * 0.92 + zz * 0.28 + warp;
        const scale = 1 + energy + warp;
        const px = mid + xx * R * scale,
          py = mid + yy * R * scale;
        if (k === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = colors[Math.min(35, Math.round(front * 35))];
      ctx.stroke();
    }
    // Meridians cross the woven surface and keep its volume readable.
    ctx.lineWidth = 0.5;
    for (let j = 0; j < 20; j++) {
      const a = (j / 20) * TAU + spin;
      ctx.beginPath();
      for (let k = 0; k <= 64; k++) {
        const lat = -Math.PI / 2 + (k / 64) * Math.PI,
          rad = Math.cos(lat),
          x = rad * Math.cos(a),
          z = rad * Math.sin(a);
        const px = mid + x * R * (1 + energy),
          py = mid + (Math.sin(lat) * 0.92 + z * 0.28) * R * (1 + energy);
        if (k === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = Math.sin(a) > 0 ? colors[12] : backColors[0];
      ctx.stroke();
    }
    // Real microphone frequencies make the outer ring rise; word boundaries kick it.
    const ring = R * 1.22;
    ctx.lineWidth = 1.3;
    ctx.lineCap = "round";
    for (let i = 0; i < 96; i++) {
      const a = (i / 96) * TAU - Math.PI / 2;
      const f = spectrum
        ? spectrum[
            Math.min(
              spectrum.length - 1,
              Math.floor((i < 48 ? i : 95 - i) * 1.7) + 1,
            )
          ] / 255
        : 0;
      const wave =
        state === "thinking"
          ? Math.pow(Math.max(0, Math.cos(a - time * 2)), 9) * 0.23
          : state === "speaking"
            ? impulse * (0.04 + 0.11 * Math.abs(Math.sin(i * 0.7 + time * 5)))
            : 0;
      const len = 1.4 + (f * 0.32 + smooth * 0.07 + wave) * R;
      ctx.strokeStyle = i % 8 === 0 ? colors[26] : backColors[0];
      ctx.beginPath();
      ctx.moveTo(mid + Math.cos(a) * ring, mid + Math.sin(a) * ring);
      ctx.lineTo(
        mid + Math.cos(a) * (ring + len),
        mid + Math.sin(a) * (ring + len),
      );
      ctx.stroke();
    }
    // Orbital nodes move only when motion is allowed.
    for (let i = 0; i < 5; i++) {
      const a = (i / 5) * TAU + time * 0.11,
        r = R * (1.36 + i * 0.025);
      ctx.fillStyle = colors[15 + i * 3];
      ctx.beginPath();
      ctx.arc(
        mid + Math.cos(a) * r,
        mid + Math.sin(a) * r * (0.76 + i * 0.04),
        1.2,
        0,
        TAU,
      );
      ctx.fill();
    }
  }
  function frame(now) {
    raf = 0;
    if (document.hidden || !visible || reduced.matches) return;
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    time += dt;
    smooth += (level - smooth) * 0.22;
    impulse *= Math.pow(0.08, dt);
    draw();
    raf = requestAnimationFrame(frame);
  }
  function resume() {
    cancelAnimationFrame(raf);
    raf = 0;
    last = performance.now();
    if (reduced.matches) {
      smooth = 0;
      impulse = 0;
      time = 0;
      draw();
    } else if (!document.hidden && visible) raf = requestAnimationFrame(frame);
  }
  reduced.addEventListener("change", resume);
  document.addEventListener("visibilitychange", resume);
  palette();
  draw();
  resume();
  return {
    setState(s) {
      if (PALETTES[s]) {
        state = s;
        palette();
        if (reduced.matches) draw();
      }
    },
    setLevel(v) {
      level = v;
    },
    setSpectrum(v) {
      spectrum = v;
    },
    pulse(v = 1) {
      impulse = Math.min(1.4, impulse + v);
    },
  };
}
