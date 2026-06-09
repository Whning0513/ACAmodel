#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import csv
import subprocess


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.stdout


gpu_rows = []
reader = csv.reader(
    run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
    ).splitlines()
)
for row in reader:
    if row:
        gpu_rows.append(
            {
                "index": row[0].strip(),
                "uuid": row[1].strip(),
                "used_mem_mb": int(row[2].strip()),
                "total_mem_mb": int(row[3].strip()),
            }
        )

compute_rows = []
reader = csv.reader(
    run(
        [
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ]
    ).splitlines()
)
for row in reader:
    if len(row) >= 4:
        compute_rows.append(
            {
                "uuid": row[0].strip(),
                "pid": row[1].strip(),
                "process_name": row[2].strip(),
                "used_gpu_memory": row[3].strip(),
            }
        )

print("GPU id | used memory | running vLLM PID | model alias | recommended_free")
print("---|---|---|---|---")
for gpu in gpu_rows:
    apps = [app for app in compute_rows if app["uuid"] == gpu["uuid"]]
    vllm_pid = ""
    model_alias = ""
    for app in apps:
        pid = app["pid"]
        cmdline = run(["ps", "-p", pid, "-o", "args="]).strip()
        if "vllm serve" in cmdline:
            vllm_pid = pid
            if "--served-model-name" in cmdline:
                parts = cmdline.split("--served-model-name", 1)[1].strip().split()
                if parts:
                    model_alias = parts[0]
            elif "/data/LLMs/" in cmdline:
                model_alias = cmdline.split("/data/LLMs/", 1)[1].split()[0]
            break
    recommended_free = "yes" if not apps and gpu["used_mem_mb"] < 4096 else "no"
    print(f"{gpu['index']} | {gpu['used_mem_mb']}/{gpu['total_mem_mb']} MB | {vllm_pid or '-'} | {model_alias or '-'} | {recommended_free}")
PY
