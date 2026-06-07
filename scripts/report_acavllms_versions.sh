#!/usr/bin/env bash
set -euo pipefail

REPORT="/data/whn/ACA_model/reports/acavllms_versions.md"
mkdir -p /data/whn/ACA_model/reports /data/whn/tmp/acavllms-pip-cache /data/whn/tmp/acavllms-hf /data/whn/tmp/acavllms-xdg

source /data/miniconda3/bin/activate ACAvllms

export TMPDIR=/data/whn/tmp
export PIP_CACHE_DIR=/data/whn/tmp/acavllms-pip-cache
export HF_HOME=/data/whn/tmp/acavllms-hf
export XDG_CACHE_HOME=/data/whn/tmp/acavllms-xdg
export TRANSFORMERS_CACHE=/data/whn/tmp/acavllms-hf/transformers

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
