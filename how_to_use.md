# ACA_model How To Use

This directory contains the standard local serving tools for ACAvllms.

For the reusable probe20 experiment workflow, see:

- `docs/probe20_reusable_ops_runbook.md`
- `docs/portability_handoff.md`

## First Read

如果你是第一次接手这个目录，先抓住下面几件事：

1. 这个仓库现在已经尽量做成“可搬走”的形态了。
2. `ACA` 的最小运行核心和主数据集已经 vendored 进仓库内的 `ACA/`。
3. 真正还依赖外部机器环境的，主要只剩：
   - 模型权重
   - conda / vLLM 环境
   - NVIDIA 驱动和 CUDA
4. 当前默认实验入口已经不是零散 python 命令，而是 `scripts/` 里的包装脚本。

## What Is In This Repo

当前仓库内，和运行最相关的目录是：

- `ACA/`
  vendored 的 ACA 最小运行子集，包括：
  - `run_experiment.py`
  - `agent/`
  - `tool/`
  - `stat/`
  - `scripts/analyze_generator_reward_v1.py`
  - `data/waFocusedData_submit_0526_final/`

- `scripts/`
  本仓库自己的启动、监控、包装、审计脚本。

- `tasksets/`
  当前只保留了 `probe20` 的任务集：
  - `gtor_probe20_ids.txt`

- `outputs/`
  当前只保留了最新一组 `gtor4_probe20` 输出。

- `reports/`
  当前只保留了少量仍有直接价值的汇总和环境记录。

## What Is Still External

下面这些东西没有收进仓库，仍然要靠目标机器自己准备：

- 模型目录：
  - `/data/LLMs/Qwen3.5-4B`
  - `/data/LLMs/Qwen3.5-9B`
  - `/data/LLMs/Qwen2.5-Coder-7B-Instruct`

- conda 环境：
  - `ACAvllms124`
  - `vllm017_full`

- 系统工具：
  - `nvidia-smi`
  - `curl`
  - `ss`
  - `gpustat`（推荐，但不是绝对必须）

## Recommended Reading Order

建议按这个顺序看：

1. `docs/portability_handoff.md`
   看清楚哪些已经跟仓库走，哪些还必须外置

2. `docs/probe20_reusable_ops_runbook.md`
   看当前 `probe20` 的推荐运行方式

3. 这份 `how_to_use.md`
   看服务层脚本、状态词和日常操作

## Current Recommended Workflow

如果只是想跑当前保留的 `probe20` 实验，不要自己拼命令，直接用下面两步：

### 1. 先看 GPU 建议

```bash
cd /data/whn/ACA_model
bash scripts/recommend_gtor4_probe20_dual.sh
```

它会打印：

- 当前 GPU 显存快照
- 推荐 GPU
- 推荐 `gpu_memory_utilization`
- 一条可以直接复制执行的命令

### 2. 直接用安全包装脚本启动

```bash
cd /data/whn/ACA_model
bash scripts/run_gtor4_probe20_dual_safe.sh
```

默认行为：

- 先 `7B`
- 再 `9B`
- 模型间串行
- 模型内少量并行
- 自带进度条、ETA、状态汇总和最终诊断

## Current Token / Context Defaults

当前这套双模型对齐配置默认是：

- `7B`
  - `max_model_len=8192`
  - `llm_max_tokens=2048`

- `9B`
  - `max_model_len=8192`
  - `llm_max_tokens=2048`

但要明确一点：

- 这套是“对齐试验配置”
- 不是已经完全证明长期稳定的“绝对稳态默认值”

最近的实际结论是：

- `16384 / 4096` 太重，当前机器显存不够
- `8192 / 2048` 能启动，但 7B 仍然可能在运行中掉服务

也就是说，资源上游约束仍然是：

- VRAM

## Current Environment Split

当前推荐环境分工是：

- `qwen25-coder-7b -> ACAvllms124`
- `qwen35-9b -> vllm017_full`
- `qwen35-4b -> vllm017_full`

不要为了表面统一，把 7B 和 9B 硬塞进同一个服务环境。

## Why The Wrappers Exist

这些包装脚本不是为了“好看”，而是为了避开最常见的人为问题：

- 手工切错 conda 环境
- 本地代理污染 `127.0.0.1`
- 启动后只看 `/v1/models`，没做真实 chat 自检
- PID 丢失，最后只能 `pkill`
- 两个模型同时抢显存
- 上下文和输出 token 改大后，没有及时看到这是显存问题而不是“脚本玄学”

## Current Retention Policy

为了方便后续搬运和 GitHub 提交，这个目录已经做了收缩：

- `reports/` 只留当前仍有直接价值的少量汇总
- `outputs/` 只留最新一组 `gtor4_probe20`
- `tasksets/` 只留 `probe20`
- `tests/` 保持不动

如果你要恢复历史细节，优先去 Git 历史里找，而不是继续把本地目录堆大。

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

## Status Terminology

后面所有实验记录、启动日志、汇总报告，统一按下面这套词来写，不混着说：

- `崩溃`
  只指进程或流程非预期退出。
  例子：vLLM 进程直接死掉，`run_experiment` 半路退出，watchdog 没等到正常收尾。

- `无输出`
  只指模型调用或方法执行后，没有产出有效内容。
  例子：LLM 返回空字符串、解析后没有 generator、任务最终没有有效结果文件。

- `错误`
  只指明确可定位的报错、异常或非法状态。
  例子：`KV_CACHE_INSUFFICIENT`、端口占用、模型权重不兼容、compile error、runtime error。

- `哑火`
  只指流程跑完了，但方法没有打出有效结果。
  例子：20 条任务都正常执行到终态，但 `success=0`。

推荐用法：

- 服务没起来：写 `启动失败` 或具体错误名，不写 `无输出`
- 跑到一半死掉：写 `崩溃` 或 `运行中断`
- 模型回了空内容：写 `无输出`
- 有明确异常栈或错误码：写 `错误`
- 全程跑完但结果几乎全失败：写 `哑火`，不写 `崩溃`

最近这组 probe20 里：

- `7B AgentG` 属于 `哑火`
- 之前 `9B` 在错误环境里起不来，属于 `启动失败`
- `KV cache` 不够、`linear_attn.A_log` 不兼容，属于 `错误`

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
