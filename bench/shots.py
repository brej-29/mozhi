"""Capture README screenshots from a running server (python -m mozhi). Needs `pip install playwright` and Edge or Chrome.

    python bench/shots.py http://127.0.0.1:8765 docs/images
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

url, out = sys.argv[1], Path(sys.argv[2])
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1, color_scheme="dark")
    pg.goto(url)
    pg.wait_for_selector("#status.ok", timeout=60000)
    for t in ["what's the weather in lisbon", "remind me to call mum tomorrow at 5 pm", "play some jazz in the kitchen",
              "save a note buy oat milk"]:
        pg.fill("#text", t)
        pg.press("#text", "Enter")
        pg.wait_for_selector(".send:not([disabled])", timeout=30000)
    pg.wait_for_timeout(2200)
    pg.screenshot(path=str(out / "talk.png"))
    pg.fill("#text", "who wrote the lord of the rings")
    pg.press("#text", "Enter")
    pg.wait_for_timeout(450)
    pg.screenshot(path=str(out / "thinking.png"))
    pg.wait_for_selector(".send:not([disabled])", timeout=30000)
    pg.set_viewport_size({"width": 390, "height": 844})
    pg.reload()
    pg.wait_for_selector("#status.ok", timeout=60000)
    pg.wait_for_timeout(600)
    pg.screenshot(path=str(out / "mobile.png"))
    ev = b.new_page(viewport={"width": 1100, "height": 900}, color_scheme="dark")
    ev.goto(url + "#evidence")
    ev.wait_for_selector("#ev-root h2", timeout=30000)
    for y in range(0, 6000, 500):  # scroll so every chart reveals
        ev.mouse.wheel(0, 500)
        ev.wait_for_timeout(120)
    ev.wait_for_timeout(1200)
    ev.screenshot(path=str(out / "evidence.png"), full_page=True)
    b.close()
print("saved")
