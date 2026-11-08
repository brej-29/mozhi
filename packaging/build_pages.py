"""Build the static site for GitHub Pages: the UI plus the int8 router, which then runs in the browser.

    python packaging/build_pages.py site
The onnxruntime-web files are downloaded from a pinned npm release and checked against the SHA-256
hashes in packaging/vendor.json, so the page loads nothing from third parties at run time.
"""

import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
cache = root / ".vendor_cache"

shutil.rmtree(out, ignore_errors=True)  # may fail if a server is running inside it; copytree overwrites
shutil.copytree(root / "mozhi" / "web", out, dirs_exist_ok=True)
for source, target in (("joint", "model"), ("joint2", "model2")):
    (out / target).mkdir(exist_ok=True)
    for name in ("model.int8.onnx", "tokenizer.json", "meta.json"):
        shutil.copy(root / "models" / source / name, out / target / name)

(out / "vendor" / "ort").mkdir(parents=True, exist_ok=True)
cache.mkdir(exist_ok=True)
for name, meta in json.loads((root / "packaging" / "vendor.json").read_text()).items():
    f = cache / name
    if not f.exists():
        f.write_bytes(urllib.request.urlopen(meta["url"], timeout=120).read())
    digest = hashlib.sha256(f.read_bytes()).hexdigest()
    if digest != meta["sha256"]:
        f.unlink()
        sys.exit(f"{name}: hash {digest} does not match the pinned {meta['sha256']}")
    shutil.copy(f, out / "vendor" / "ort" / name)

(out / "config.js").write_text("window.MOZHI_STATIC = true;\n", encoding="utf-8")
(out / ".nojekyll").write_text("", encoding="utf-8")
print("built", out)
