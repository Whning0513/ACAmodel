# ACA_model How To Use

This directory contains the standard local serving tools for ACAvllms.

## Purpose

These scripts are for one thing:

- start a local vLLM server
- check whether the server is really usable
- stop the server safely
- record the ACAvllms environment versions

They are intended for these local models:

- `/data/LLMs/Qwen3.5-4B`
- `/data/LLMs/Qwen3.5-9B`
- `/data/LLMs/Qwen2.5-Coder-7B-Instruct`

The scripts use the isolated conda environment:

- `/data/miniconda3/envs/ACAvllms` (default)
- `/data/miniconda3/envs/vllm017_full` (CUDA 12.x + vllm 0.17.0, see `/data/whn/ACA_model/docs/vllm017_qwen35_serving.md`)

They do not use `herald`, and they should not download into `~`.

## Infrastructure Progress

The current progress is at the service-layer standardization stage.

What is already standardized:

- a dedicated environment: `ACAvllms`
- fixed local model aliases
- fixed temp and cache paths under `/data/whn/tmp`
- fixed background startup flow for vLLM
- fixed health-check flow
- fixed safe stop flow by PID file
- fixed version-report flow

Why this was needed:

- earlier tests mixed model issues with environment issues
- local proxy variables could interfere with `127.0.0.1`
- `/v1/models` could be healthy while real chat requests still failed
- manual startup made it easy to lose the PID, GPU choice, port, or log path
- `~` and `/tmp` were too risky for large serving installs and cache writes

What the current encapsulation does to prevent those problems:

- always activates `/data/miniconda3/envs/ACAvllms`
- always unsets proxy variables before local serving and local checks
- always writes cache and temp files into `/data/whn/tmp`
- always records a PID file and a log file
- always checks port occupancy before startup
- always verifies real chat output, not just `/v1/models`
- always stops by exact PID instead of broad `pkill`

What is not included yet:

- ACA smoke execution
- BaseG / AgentG experiment launching
- reward analysis
- training

So the current milestone is:

```text
model serving compatibility and process management are being standardized first
before any ACA experiment pipeline is resumed
```

## Technical Approach

The service-layer wrapper uses a few simple but important techniques:

- alias-to-model-path mapping
  so callers use `qwen35-4b` instead of hand-writing full local paths

- environment pinning
  so Qwen3.5 compatibility work stays isolated in `ACAvllms`

- cache redirection
  so downloads and temporary files avoid `~` and avoid unstable default locations

- nohup background serving
  so model servers survive after the shell command returns

- PID-file based lifecycle management
  so stop operations are targeted and safe

- two-stage health checks
  because a model list endpoint alone is not enough to prove the server is usable

- version reporting plus `AutoConfig` checks
  so architecture-recognition issues such as `qwen3_5` can be separated from runtime serving issues

## The Four Tools

### 1. `start_acavllms_vllm.sh`

Starts a local vLLM server in the background.

Usage:

```bash
bash /data/whn/ACA_model/scripts/start_acavllms_vllm.sh qwen35-4b 8024 1
bash /data/whn/ACA_model/scripts/start_acavllms_vllm.sh qwen35-9b 8029 1
bash /data/whn/ACA_model/scripts/start_acavllms_vllm.sh qwen25-coder-7b 8017 1
```

Arguments:

- `$1`: model alias
- `$2`: port
- `$3`: GPU id

Supported aliases:

- `qwen35-4b`
- `qwen35-9b`
- `qwen25-coder-7b`

What it does:

- activates `ACAvllms`
- sets cache and temp directories under `/data/whn/tmp`
- unsets proxy variables
- checks whether the port is already occupied
- starts vLLM with `nohup`
- saves:
  - pid file under `/data/whn/ACA_model/run/vllm`
  - log file under `/data/whn/ACA_model/logs/vllm`
- waits for `/v1/models` to become ready

If successful, it prints:

```text
VLLM_READY=1
MODEL_ALIAS=...
MODEL_PATH=...
PORT=...
GPU_ID=...
API_BASE=http://127.0.0.1:<PORT>/v1
PID=...
LOG=...
```

### 2. `check_vllm_server.sh`

Checks that the server is not only alive, but can also answer a real chat request.

Usage:

```bash
bash /data/whn/ACA_model/scripts/check_vllm_server.sh 8024
```

What it checks:

- `/v1/models`
- `/v1/chat/completions`

It sends a short prompt:

```text
Say hello in one short sentence.
```

Expected output looks like:

```text
MODELS_OK=1
CHAT_OK=1
CONTENT_LEN=...
CONTENT_PREVIEW=...
```

This is important because `/v1/models` can be healthy while real chat requests still fail.

### 3. `stop_vllm_server.sh`

Stops a server safely by PID file.

Usage:

```bash
bash /data/whn/ACA_model/scripts/stop_vllm_server.sh 8024
```

What it does:

- finds `/data/whn/ACA_model/run/vllm/*_<port>.pid`
- reads the exact PID
- kills only that PID
- checks that the port is released

It does not do broad `pkill -f Qwen`.

### 4. `report_acavllms_versions.sh`

Writes a version and compatibility report.

Usage:

```bash
bash /data/whn/ACA_model/scripts/report_acavllms_versions.sh
```

Output file:

```text
/data/whn/ACA_model/reports/acavllms_versions.md
```

The report includes:

- Python version
- torch version
- torch CUDA version
- transformers version
- vllm version
- `nvidia-smi` summary
- `AutoConfig` recognition results for:
  - `Qwen3.5-4B`
  - `Qwen3.5-9B`
  - `Qwen2.5-Coder-7B-Instruct`

## Standard Workflow

### Check the environment

```bash
bash /data/whn/ACA_model/scripts/report_acavllms_versions.sh
```

### Start 4B

```bash
bash /data/whn/ACA_model/scripts/start_acavllms_vllm.sh qwen35-4b 8024 1
```

### Check 4B

```bash
bash /data/whn/ACA_model/scripts/check_vllm_server.sh 8024
```

### Stop 4B

```bash
bash /data/whn/ACA_model/scripts/stop_vllm_server.sh 8024
```

### Start 9B

```bash
bash /data/whn/ACA_model/scripts/start_acavllms_vllm.sh qwen35-9b 8029 1
```

### Check 9B

```bash
bash /data/whn/ACA_model/scripts/check_vllm_server.sh 8029
```

### Stop 9B

```bash
bash /data/whn/ACA_model/scripts/stop_vllm_server.sh 8029
```

## Important Notes

- Do not use `herald` for this Qwen3.5 serving compatibility work.
- Do not modify files under `/data/LLMs`.
- Do not download into `~` or `/home/hengningwang`.
- Use `/data/whn/tmp` for all temporary files and caches.
- These scripts are only for local model serving management.
- They do not run ACA experiments, smoke tests, or training by themselves.
