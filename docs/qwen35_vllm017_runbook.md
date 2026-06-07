# Qwen3.5-4B vLLM 0.17.0 Runbook

## 环境

| 项目 | 值 |
|------|-----|
| conda env name | `vllm017_full` |
| env path | `/data/miniconda3/envs/vllm017_full` |
| python | 3.11 |
| torch | 2.10.0+cu128 |
| CUDA runtime (用户态) | 12.8 |
| CUDA driver | 545.29.06 (native 12.3) |
| transformers | 4.57.6 |
| vllm | 0.17.0 |

所有依赖均为 CUDA 12.x，**无 cu13 组件**。CUDA 12.8 forward-compatible with driver 545。

## 模型

| 项目 | 值 |
|------|-----|
| model alias | `qwen35-4b` |
| model path | `/data/LLMs/Qwen3.5-4B` |
| model_type | `qwen3_5_text` (Qwen3_5TextConfig) |
| 架构 | 33 layers: 24 linear_attention + 9 full_attention (layer 0 has both) |
| 显存占用 | ~8.6 GiB (模型权重) |

## 当前运行实例

| 项目 | 值 |
|------|-----|
| port | 8024 |
| GPU | 1 |
| PID | 2693968 |
| GPU 显存 used/free | 77696 MiB / 3353 MiB (含其他进程) |
| API base | `http://127.0.0.1:8024/v1` |

## 为什么 vLLM 0.8.5 失败

Qwen3.5 使用 **hybrid 架构**，有 24 层 `linear_attention`（Mamba2 风格 SSM / Gated DeltaNet）：

```
linear_attn.in_proj_qkv.weight
linear_attn.in_proj_a.weight
linear_attn.in_proj_b.weight
linear_attn.in_proj_z.weight
linear_attn.conv1d.weight
linear_attn.A_log
linear_attn.dt_bias
linear_attn.norm.weight
linear_attn.out_proj.weight
```

vLLM 0.8.5 的 `qwen3.py` 只实现了 `Qwen3Attention`（标准 full attention），**没有线性注意力模块，也没有 hybrid layer dispatch 逻辑**。模型加载时 vLLM 遍历 checkpoint keys，遇到 `linear_attn.*` 权重时找不到对应的模块，直接报 `KeyError: linear_attn`。

这不是 config/registry monkey-patch 能解决的——需要完整的 Mamba2 kernel 实现和新的模型层代码。

## 为什么 vLLM 0.17.0 成功

vLLM 0.17.0 是实测可用的**最低版本**，内置了原生 Qwen3.5 实现：

- `vllm/model_executor/models/qwen3_5.py`
  - `Qwen3_5GatedDeltaNet` — Mamba2 风格 SSM，处理 linear attention 层
  - `Qwen3_5DecoderLayer` — hybrid dispatch：根据 layer type 分发到 `linear_attention` 或 `full_attention`
- `vllm/model_executor/models/qwen3_5_mtp.py` — Multi-Token Predictor
- `vllm/transformers_utils/configs/qwen3_5.py` — `Qwen3_5Config` / `Qwen3_5TextConfig`
- `vllm/transformers_utils/configs/qwen3_5_moe.py` — `Qwen3_5MoeConfig` (MoE 变体)

## sitecustomize.py 的作用

transformers 4.57.6 的 `AutoConfig` 不认识 `qwen3_5` / `qwen3_5_text` model_type——
`AutoConfig.from_pretrained("/data/LLMs/Qwen3.5-4B")` 会报 `Unknown model_type "qwen3_5"`。

但 vLLM 0.17.0 自带 config bridge 类（`Qwen3_5Config` / `Qwen3_5TextConfig`）。
只需在 transformers 启动时注册这些类到 `AutoConfig` 即可。

**文件:** `/data/miniconda3/envs/vllm017_full/lib/python3.11/site-packages/sitecustomize.py`

```python
"""Auto-register Qwen3.5 model config with transformers for vLLM 0.17.0 compat."""
from transformers import AutoConfig
from vllm.transformers_utils.configs.qwen3_5 import Qwen3_5Config, Qwen3_5TextConfig
from vllm.transformers_utils.configs.qwen3_5_moe import Qwen3_5MoeConfig, Qwen3_5MoeTextConfig

AutoConfig.register('qwen3_5', Qwen3_5Config)
AutoConfig.register('qwen3_5_text', Qwen3_5TextConfig)
AutoConfig.register('qwen3_5_moe', Qwen3_5MoeConfig)
AutoConfig.register('qwen3_5_moe_text', Qwen3_5MoeTextConfig)
```

这个文件在 Python 启动时自动执行，无需在脚本中手动 import。

## 启动命令

### 方式一：标准脚本

```bash
GPU_MEMORY_UTILIZATION=0.35 \
ENABLE_AUTO_TOOL_CHOICE=0 \
VLLM_CONDA_ENV=vllm017_full \
bash /data/whn/ACA_model/scripts/start_acavllms_vllm.sh qwen35-4b 8024 1
```

### 方式二：直接启动（绕过 conda activate 问题）

当前用户 `source activate` 可能被 `~/.hermes/hermes-agent/venv/bin` 覆盖 PATH。
此时用直接启动：

```bash
export PATH="/data/miniconda3/envs/vllm017_full/bin:$PATH"
export PYTHONNOUSERSITE=1
export TMPDIR=/data/whn/tmp
export HF_HOME=/data/whn/tmp/acavllms-hf
export XDG_CACHE_HOME=/data/whn/tmp/acavllms-xdg
export TRANSFORMERS_CACHE=/data/whn/tmp/acavllms-hf/transformers
export CUDA_VISIBLE_DEVICES=1
unset ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy

mkdir -p /data/whn/ACA_model/run/vllm /data/whn/ACA_model/logs/vllm

nohup vllm serve /data/LLMs/Qwen3.5-4B \
  --host 127.0.0.1 \
  --port 8024 \
  --dtype auto \
  --api-key local-vllm \
  --served-model-name qwen35-4b \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.35 \
  --max-model-len 8192 \
  --enforce-eager \
  > /data/whn/ACA_model/logs/vllm/qwen35-4b_8024.log 2>&1 &

echo "$!" > /data/whn/ACA_model/run/vllm/qwen35-4b_8024.pid
```

### 参数说明

| 参数 | 值 | 原因 |
|------|-----|------|
| `--gpu-memory-utilization` | 0.35 | GPU 1 可用 ~32 GB，设置偏高会导致 OOM |
| `--enforce-eager` | 1 | 禁用 CUDA graph，节省显存 |
| `--max-model-len` | 8192 | 与现有 ACAvllms 配置一致 |
| `--tensor-parallel-size` | 1 | 4B 模型单卡足够 |
| `ENABLE_AUTO_TOOL_CHOICE` | 0 | hermes parser 不兼容 Qwen3.5 |

## 验证命令

### /v1/models

```bash
curl -sS -H "Authorization: Bearer local-vllm" \
  "http://127.0.0.1:8024/v1/models"
```

预期: `{"object":"list","data":[{"id":"qwen35-4b",...}]}`

### /v1/chat/completions

```bash
curl -sS -H "Authorization: Bearer local-vllm" \
  -H "Content-Type: application/json" \
  "http://127.0.0.1:8024/v1/chat/completions" \
  -d '{
    "model":"qwen35-4b",
    "messages":[{"role":"user","content":"Say hello in one short sentence."}],
    "max_tokens":50,
    "temperature":0.0
  }'
```

预期: 返回 chat completion JSON，choices[0].message.content 非空。

### 使用标准检查脚本

```bash
bash /data/whn/ACA_model/scripts/check_vllm_server.sh 8024
```

### 停止服务

```bash
bash /data/whn/ACA_model/scripts/stop_vllm_server.sh 8024
# 或:
kill $(cat /data/whn/ACA_model/run/vllm/qwen35-4b_8024.pid)
```

## 已知问题

### Qwen3.5 thinking/reasoning block

模型默认在 chat completions 中输出 `Thinking Process:` 推理块：

```
Thinking Process:

1.  **Analyze the Request:**
    *   Task: Say hello
    *   Constraint: One short sentence
...
```

这与 Qwen3 的 `--reasoning-parser qwen3` 机制不同——Qwen3.5 的 thinking token 直接出现在
`content` 字段中，而不是 `reasoning_content`。在 ACA agent 场景下，`extract_generator_code`
需要能容忍这个 prefix，否则可能找不到代码块。

### FLA shape 警告（非致命）

短 prompt 时（seq_len < num_heads=32），FLA linear attention ops 输出 `UserWarning`。
不影响推理正确性。

### source activate 不可靠

当前用户 `~/.hermes/hermes-agent/venv/bin` 在 PATH 最前面，即使 `conda activate` 后也会被覆盖。
始终使用 `/data/miniconda3/envs/vllm017_full/bin/python` 或手动 `export PATH=...`。
