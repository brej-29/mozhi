# Windows: run these from Git Bash, or copy the commands. Python via uv.
PY = .venv/Scripts/python.exe
LLM15 = data/raw/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
LLM05 = data/raw/models/qwen2.5-0.5b-instruct-q4_k_m.gguf

.PHONY: setup test run exe eval train train-j2 repro

setup:
	uv venv --python 3.11 .venv
	uv pip install --python $(PY) torch --index-url https://download.pytorch.org/whl/cu124
	uv pip install --python $(PY) -e ".[train,eval,dev]"
	# one package from one extra index, no dependency resolution against it (avoids dependency confusion)
	uv pip install --python $(PY) llama-cpp-python --no-deps --only-binary :all: --index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

test:
	$(PY) -m ruff check . && $(PY) -m pytest -q

run:
	$(PY) -m jarvis

exe:
	$(PY) -m PyInstaller packaging/jarvis.spec --noconfirm

train:
	for s in 0 1 2; do PYTHONPATH=. $(PY) training/train_joint.py --seed $$s --out models/aug_seed$$s; done

train-j2:
	PYTHONPATH=. $(PY) training/train_joint2.py --seeds 0,1,2 --epochs 3 --out models/joint2

# Fast systems on the full test set (about a minute)
eval:
	$(PY) -m jarvis.bench.run r0 --set full
	$(PY) -m jarvis.bench.run m1 --set full
	for s in 0 1 2; do $(PY) -m jarvis.bench.run j1 --model models/aug_seed$$s --set full; done

# LLM systems on the stratified subset (about an hour on CPU; models are GGUF downloads)
eval-llm:
	for m in $(LLM15) $(LLM05); do for s in l1 l0; do $(PY) -m jarvis.bench.run $$s --model $$m --set subset; done; done

repro:
	$(PY) bench/repro_v1_bugs.py
