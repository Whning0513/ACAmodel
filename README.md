# ACA_model

This directory is the working area for the next ACA model-serving steps.

## Local model sources

These models already exist locally and should be reused instead of downloaded again:

- `/data/LLMs/Qwen3.5-4B`
- `/data/LLMs/Qwen3.5-9B`
- `/data/LLMs/Qwen2.5-Coder-7B-Instruct`

## Model links in this workspace

`/data/whn/models/qwen` currently contains symlinks:

- `Qwen3.5-4B -> /data/LLMs/Qwen3.5-4B`
- `Qwen3.5-9B -> /data/LLMs/Qwen3.5-9B`
- `Qwen2.5-Coder-7B-Instruct -> /data/LLMs/Qwen2.5-Coder-7B-Instruct`

## vLLM setup

An existing vLLM installation was found here:

- `/data/miniconda3/envs/herald/bin/vllm`
- Version: `0.7.3`

The local launcher script is:

- `/data/whn/scripts/serve_qwen_vllm.sh`

It prefers `vllm` from `PATH`, and otherwise falls back to:

- `/data/miniconda3/envs/herald/bin/vllm`

## Example: start a local server

Serve `Qwen3.5-4B` on port `8000`:

```bash
PORT=8000 /data/whn/scripts/serve_qwen_vllm.sh Qwen3.5-4B
```

## Client environment

Point ACA scripts to the local OpenAI-compatible endpoint:

```bash
export LLM_API_BASE=http://127.0.0.1:8000/v1
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
export LLM_API_KEY=local-vllm
export OPENAI_API_KEY=local-vllm
export LLM_MODEL=Qwen3.5-4B
```

Relevant ACA code already supports this style of endpoint through env vars such as:

- `LLM_API_BASE`
- `OPENAI_BASE_URL`
- `LLM_MODEL`

## ACAvllms Standard Scripts

Standard Qwen serving scripts now live here:

- `/data/whn/ACA_model/scripts/start_acavllms_vllm.sh`
- `/data/whn/ACA_model/scripts/check_vllm_server.sh`
- `/data/whn/ACA_model/scripts/stop_vllm_server.sh`
- `/data/whn/ACA_model/scripts/report_acavllms_versions.sh`

Supported aliases:

- `qwen35-4b`
- `qwen35-9b`
- `qwen25-coder-7b`

Example flow:

```bash
bash /data/whn/ACA_model/scripts/report_acavllms_versions.sh
bash /data/whn/ACA_model/scripts/start_acavllms_vllm.sh qwen35-4b 8024 1
bash /data/whn/ACA_model/scripts/check_vllm_server.sh 8024
bash /data/whn/ACA_model/scripts/stop_vllm_server.sh 8024
```

## vLLM Environments

本机有三个 vLLM conda 环境：

| env | vllm | torch | CUDA | 用途 |
|-----|------|-------|------|------|
| `herald` | 0.7.3 | — | — | 旧 ACA 实验，勿用于 Qwen3.5 |
| `ACAvllms` | 0.22.1 | 2.11.0+cu130 | 13.0 | 当前 master env |
| `vllm017_full` | 0.17.0 | 2.10.0+cu128 | 12.8 | Qwen3.5 最低可用验证，CUDA 12.x |

`vllm017_full` 是唯一 CUDA 12.x 的 Qwen3.5 可用环境。详细 runbook: `/data/whn/ACA_model/docs/qwen35_vllm017_runbook.md`

## Qwen3.5-4B 当前运行实例

| 项目 | 值 |
|------|-----|
| env | `vllm017_full` (vllm 0.17.0) |
| port | 8024 |
| GPU | 1 |
| PID | 2693968 |
| API base | `http://127.0.0.1:8024/v1` |

```bash
# 验证
curl -sS -H "Authorization: Bearer local-vllm" http://127.0.0.1:8024/v1/models
# 停止
kill $(cat /data/whn/ACA_model/run/vllm/qwen35-4b_8024.pid)
```

## Notes

- Do not re-download the three Qwen models above.
- Prefer serving from the existing local model directories.
- `/tmp` is nearly full on this machine, so temporary files should prefer `/data/whn/tmp`.
- For ACAvllms work, do not download into `~` or `/home/hengningwang`; use `/data/whn/tmp` caches only.
