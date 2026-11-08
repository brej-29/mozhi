# PyInstaller spec: one-file Windows build with the UI and the int8 router inside.
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(f"{ROOT}/mozhi/web", "mozhi/web"), (f"{ROOT}/models/joint", "models/joint"), (f"{ROOT}/models/joint2", "models/joint2"),
         (f"{ROOT}/mozhi/legacy/goal_excerpt.txt", "mozhi/legacy"),
         (f"{ROOT}/mozhi/legacy/components_excerpt.txt", "mozhi/legacy")]
datas += collect_data_files("dateparser") + collect_data_files("tzlocal")
hidden = collect_submodules("uvicorn") + collect_submodules("dateparser") + ["tokenizers", "onnxruntime"]

a = Analysis([f"{ROOT}/packaging/mozhi_app.py"], pathex=[ROOT], datas=datas, hiddenimports=hidden,
             excludes=["torch", "transformers", "llama_cpp", "sklearn", "pandas", "scipy", "matplotlib"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="mozhi", console=True, upx=False)
