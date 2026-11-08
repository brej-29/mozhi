/* Ambient signal field, theme choice and state labels. No network or dependencies. */
export function initHUD() {
  const root = document.documentElement,
    button = document.querySelector("#theme-toggle"),
    name = document.querySelector("#theme-name");
  const light = matchMedia("(prefers-color-scheme: light)"),
    reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let theme = "";
  try {
    theme = localStorage.getItem("mozhi-theme") || "";
  } catch {
    /* private storage */
  }
  if (theme !== "light" && theme !== "dark") theme = "";
  function apply() {
    if (theme) root.dataset.theme = theme;
    const isLight = theme ? theme === "light" : light.matches;
    button.setAttribute(
      "aria-label",
      "Switch to " + (isLight ? "dark" : "light") + " theme",
    );
    name.textContent = isLight ? "Dark" : "Light";
    paintColors();
    draw(0);
  }
  button.addEventListener("click", () => {
    theme = (theme ? theme === "light" : light.matches) ? "dark" : "light";
    try {
      localStorage.setItem("mozhi-theme", theme);
    } catch {
      /* private storage */
    }
    apply();
  });
  const canvas = document.querySelector("#sky"),
    ctx = canvas.getContext("2d");
  let width = 0,
    height = 0,
    raf = 0,
    ink = "",
    accent = "";
  const points = new Float32Array(48 * 3);
  for (let i = 0; i < 48; i++) {
    points[i * 3] = ((i * 73.13) % 101) / 101;
    points[i * 3 + 1] = ((i * 37.79) % 103) / 103;
    points[i * 3 + 2] = 0.5 + (i % 5) * 0.2;
  }
  function paintColors() {
    const style = getComputedStyle(root);
    ink = style.getPropertyValue("--line").trim();
    accent = style.getPropertyValue("--mint").trim();
  }
  function draw(t) {
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = ink;
    ctx.lineWidth = 0.6;
    const drift = reduced.matches ? 0 : t * 0.000009;
    for (let i = 0; i < 7; i++) {
      ctx.beginPath();
      ctx.ellipse(
        width * 0.35,
        height * 0.45,
        width * (0.35 + i * 0.075),
        height * (0.18 + i * 0.04),
        -0.32 + drift,
        0,
        Math.PI * 2,
      );
      ctx.stroke();
    }
    ctx.fillStyle = accent;
    ctx.globalAlpha = 0.35;
    for (let i = 0; i < 48; i++) {
      const x =
          (points[i * 3] * width + drift * width * points[i * 3 + 2]) % width,
        y = points[i * 3 + 1] * height;
      ctx.beginPath();
      ctx.arc(x, y, points[i * 3 + 2], 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
  function frame(t) {
    raf = 0;
    if (document.hidden || reduced.matches) return;
    draw(t);
    raf = requestAnimationFrame(frame);
  }
  function resume() {
    cancelAnimationFrame(raf);
    raf = 0;
    root.toggleAttribute("data-paused", document.hidden);
    if (!document.hidden) {
      draw(0);
      if (!reduced.matches) raf = requestAnimationFrame(frame);
    }
  }
  function resize() {
    width = Math.min(innerWidth, 1600);
    height = Math.min(innerHeight, 1100);
    canvas.width = width;
    canvas.height = height;
    draw(0);
  }
  const labels = {
    idle: "Ready when you are",
    listening: "Listening to you",
    thinking: "Connecting the dots",
    speaking: "Speaking with you",
    declined: "A limit, clearly stated",
  };
  const update = () => {
    document.querySelector("#signal-state").textContent =
      labels[document.body.dataset.state] || labels.idle;
  };
  new MutationObserver(update).observe(document.body, {
    attributes: true,
    attributeFilter: ["data-state"],
  });
  addEventListener("resize", resize);
  document.addEventListener("visibilitychange", resume);
  reduced.addEventListener("change", resume);
  light.addEventListener("change", apply);
  paintColors();
  resize();
  apply();
  resume();
  update();
}
