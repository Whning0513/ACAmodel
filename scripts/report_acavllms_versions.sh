#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TMP_ROOT="${TMP_ROOT:-/data/whn/tmp}"
REPORT="$ROOT/reports/acavllms_versions.md"
mkdir -p "$ROOT/reports" "$TMP_ROOT/acavllms-pip-cache" "$TMP_ROOT/acavllms-hf" "$TMP_ROOT/acavllms-xdg"

source /data/miniconda3/bin/activate ACAvllms

export TMPDIR="$TMP_ROOT"
export PIP_CACHE_DIR="$TMP_ROOT/acavllms-pip-cache"
export HF_HOME="$TMP_ROOT/acavllms-hf"
export XDG_CACHE_HOME="$TMP_ROOT/acavllms-xdg"
export TRANSFORMERS_CACHE="$TMP_ROOT/acavllms-hf/transformers"

unset ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy

python - <<'PY' >"$REPORT"
import platform
import subprocess
from pathlib import Path

print("# ACAvllms Versions")
print()
print(f"- environment: `/data/miniconda3/envs/ACAvllms`")
print(f"- python: `{platform.python_version()}`")

for name in ["torch", "transformers", "vllm"]:
    try:
        mod = __import__(name)
        version = getattr(mod, "__version__", "?")
        if name == "torch":
            cuda = getattr(getattr(mod, "version", None), "cuda", None)
            print(f"- {name}: `{version}`")
            print(f"- torch cuda: `{cuda}`")
        else:
            print(f"- {name}: `{version}`")
    except Exception as exc:
        print(f"- {name}: `ERROR {type(exc).__name__}: {exc}`")

print()
print("## nvidia-smi")
print()
print("```text")
try:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total", "--format=csv,noheader,nounits"],
        text=True,
    )
    print(out.strip())
except Exception as exc:
    print(f"ERROR: {exc}")
print("```")

print()
print("## AutoConfig")
print()
paths = [
    "/data/LLMs/Qwen3.5-4B",
    "/data/LLMs/Qwen3.5-9B",
    "/data/LLMs/Qwen2.5-Coder-7B-Instruct",
]
try:
    from transformers import AutoConfig
except Exception as exc:
    print(f"- AutoConfig import failed: `{type(exc).__name__}: {exc}`")
else:
    for path in paths:
        try:
            cfg = AutoConfig.from_pretrained(path, trust_remote_code=True)
            print(f"- `{path}` -> `{cfg.model_type}` / `{cfg.__class__.__name__}`")
        except Exception as exc:
            print(f"- `{path}` -> `ERROR {type(exc).__name__}: {exc}`")
PY

echo "$REPORT"
