"""Capture the README and social images from a running server (python -m mozhi).

    pip install playwright pillow      (and Edge or Chrome)
    python bench/media.py http://127.0.0.1:8765 docs/images

Writes og.png (1200x630 share card), orb.gif (the four orb states) and decision.gif (a request being read).
"""

import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

url, out = sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)


def gif(frames, path, width, ms):
    imgs = []
    for raw in frames:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        imgs.append(im.quantize(colors=48, method=Image.MEDIANCUT, dither=Image.NONE))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms, loop=0, optimize=True, disposal=2)
    print(path, path.stat().st_size // 1024, "KB", len(imgs), "frames")


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")

    # share card
    pg = b.new_page(viewport={"width": 1200, "height": 630}, color_scheme="dark")
    pg.goto(url)
    pg.wait_for_selector("#status.ok", timeout=60000)
    pg.select_option("#lang", "ta")
    pg.fill("#text", "chennai weather enna")
    pg.press("#text", "Enter")
    pg.wait_for_selector(".slip .reply:not(:has(.shimmer))", timeout=30000)
    pg.wait_for_timeout(1800)
    pg.screenshot(path=str(out / "og.png"))

    # the decision slip, frame by frame
    pg.goto(url)
    pg.wait_for_selector("#status.ok", timeout=60000)
    pg.set_viewport_size({"width": 1100, "height": 760})
    pg.evaluate("localStorage.clear()")
    frames = []
    for text in ("what's the weather in lisbon", "play some jazz in the kitchen"):
        pg.fill("#text", text)
        pg.press("#text", "Enter")
        for _ in range(26):
            frames.append(pg.screenshot(clip={"x": 20, "y": 60, "width": 1060, "height": 640}))
            pg.wait_for_timeout(55)
        pg.wait_for_timeout(300)
    gif(frames[::2], out / "decision.gif", 640, 150)

    # the four orb states
    pg.goto(url)
    pg.wait_for_selector("#status.ok", timeout=60000)
    pg.evaluate("""async () => {
      const m = await import('/orb.js');
      const wrap = document.createElement('div');
      wrap.id = 'demo';
      wrap.style.cssText = 'position:fixed;inset:0;z-index:99;background:#0e121b;display:flex;gap:4px;align-items:center;justify-content:center';
      document.body.append(wrap);
      const orbs = {};
      for (const s of ['listening', 'thinking', 'speaking', 'declined']) {
        const c = document.createElement('canvas'); c.width = 360; c.height = 360; c.style.cssText = 'width:230px;height:230px';
        wrap.append(c); orbs[s] = m.createOrb(c); orbs[s].setState(s);
      }
      let t = 0;
      setInterval(() => {
        t += 0.1;
        const f = new Uint8Array(256).map((_, i) => Math.max(0, 210 - i * 2 + 60 * Math.sin(t * 3 + i * 0.3) + Math.random() * 40));
        orbs.listening.setSpectrum(f); orbs.listening.setLevel(0.5 + 0.4 * Math.sin(t * 2));
      }, 60);
      setInterval(() => orbs.speaking.pulse(0.9), 330);
    }""")
    pg.set_viewport_size({"width": 980, "height": 300})
    pg.wait_for_timeout(1500)
    frames = []
    for _ in range(48):
        frames.append(pg.screenshot())
        pg.wait_for_timeout(40)
    gif(frames[::2], out / "orb.gif", 700, 110)
    b.close()
