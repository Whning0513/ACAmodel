# Qwen3.5 CUDA 12.4 Intersection Report

## Scope

This report only covers environment-intersection validation for:

- `/data/package/cuda-12.4`
- `torch`
- `transformers`
- `vllm`
- Qwen3.5 local checkpoints

It does **not** run ACA, probe20, or training.

## 1. CUDA packages under `/data/package`

- Found:
  - `/data/package/cuda-11.8`
  - `/data/package/cuda-12.1`
  - `/data/package/cuda-12.4`
- Chosen route for this validation: `cuda-12.4`

## 2. CUDA 12.4 path verification

Observed:

- `nvcc --version` -> `release 12.4, V12.4.99`
- `nvidia-smi` -> `Driver Version: 545.29.06`, `CUDA Version: 12.3`

Interpretation:

- User-space CUDA 12.4 toolkit is available.
- Kernel driver reports CUDA capability `12.3`.
- torch cu124 works on driver 545.29.06 (forward-compatible).

## 3. Final environment: `ACAvllms124`

### Package versions

| Package | Version |
|---------|---------|
| python | 3.11 |
| torch | 2.6.0+cu124 |
| transformers | 5.2.0 |
| vllm | 0.8.5 |
| nvidia-cuda-runtime-cu12 | 12.4 |

All packages are CUDA 12.x — **no cu13 components**.

### Verification results

- `torch.cuda.is_available()` → **True**
- `torch.cuda.get_device_name(0)` → **OK**
- `AutoConfig.from_pretrained("/data/LLMs/Qwen3.5-4B")` → **OK** (Qwen3_5Config)
- `AutoConfig.from_pretrained("/data/LLMs/Qwen3.5-9B")` → **OK** (not further tested per scope)
- `import vllm` → **OK**

## 4. Compatibility patches applied

### 4.1 Tokenizer: `all_special_tokens_extended` (transformers 5.x)

**File:** `transformers/tokenization_utils_base.py`  
**Reason:** transformers 5.x uses `TokenizersBackend` which lacks `all_special_tokens_extended` property that vLLM 0.8.5 expects.

**Patch:** Added property delegation:
```python
@property
def all_special_tokens_extended(self) -> list[str]:
    return self.all_special_tokens
```

### 4.2 Model registry: Qwen3_5ForConditionalGeneration → qwen3

**File:** `vllm/model_executor/models/registry.py`  
**Reason:** vLLM 0.8.5 has no `qwen3_5.py` model file, but Qwen3.5's text backbone is architecturally similar to Qwen3 for layers that use standard attention.

**Patch:** Added registry entry:
```python
"Qwen3_5ForConditionalGeneration": ("qwen3", "Qwen3ForCausalLM"),
```

### 4.3 Config delegation: Qwen3_5Config.__getattr__ → text_config

**File:** `transformers/models/qwen3_5/configuration_qwen3_5.py`  
**Reason:** Qwen3_5Config stores model params (vocab_size, hidden_size, etc.) inside a nested `text_config` sub-config, but vLLM accesses these directly on the top-level config.

**Patch:** Added `__getattr__` delegation:
```python
def __getattr__(self, name):
    if name not in ("text_config", "vision_config", "_fields") and hasattr(self, "text_config"):
        try:
            return getattr(self.text_config, name)
        except AttributeError:
            pass
    raise AttributeError(f"{type(self).__name__} has no attribute {name!r}")
```

### 4.4 RoPE: partial_rotary_factor passthrough

**File:** `vllm/model_executor/models/qwen3.py`  
**Reason:** Qwen3.5 uses `partial_rotary_factor=0.25` (rotary_dim = head_dim * 0.25 = 64), but vLLM's qwen3.py doesn't pass this to `get_rope()`. Without it, rotary_dim stays at 256 and MRotaryEmbedding assertion fails (mrope_section sum 32 != rotary_dim/2 128).

**Patch:** Thread `partial_rotary_factor` from config through Qwen3DecoderLayer → Qwen3Attention → get_rope().

### 4.5 Weight name mapping: language_model prefix

**File:** `vllm/model_executor/models/qwen3.py`  
**Reason:** Qwen3.5 checkpoint uses `model.language_model.*` (multimodal naming), but vLLM's Qwen3ForCausalLM uses `self.model` (Qwen3Model). Weight names mismatch.

**Patch:** Added `WeightsMapper(orig_to_new_substr={"language_model.": ""})` in load_weights.

## 5. BLOCKER: Linear attention not implemented in vLLM 0.8.5

**Status: HARD FAIL — cannot be resolved with config/registry patches.**

### Root cause

Qwen3.5 uses a **hybrid architecture** with two layer types:

| Layer type | Count | Weight prefix | Implementation |
|-----------|-------|--------------|----------------|
| Linear attention (Mamba2-based) | 24/32 | `linear_attn.*` | **NOT in vLLM 0.8.5** |
| Full attention (standard) | 9/32 | `self_attn.*` | Present in qwen3.py |

(Note: layer 0 has both linear_attn and self_attn; sum >32)

The 24 linear attention layers use Mamba2-style weights:
- `linear_attn.in_proj_qkv.weight`
- `linear_attn.in_proj_a.weight`
- `linear_attn.in_proj_b.weight`
- `linear_attn.in_proj_z.weight`
- `linear_attn.conv1d.weight`
- `linear_attn.A_log`
- `linear_attn.dt_bias`
- `linear_attn.norm.weight`
- `linear_attn.out_proj.weight`

vLLM 0.8.5's `qwen3.py` only implements `Qwen3Attention` (standard attention). There is no linear attention module, no Mamba2 kernel, and no hybrid layer dispatch logic.

Additionally, the checkpoint contains ~200 visual encoder weights (`model.visual.*`) and MTP weights (`mtp.*`) which are not loadable by the text-only vLLM model.

### Attempts exhausted

1. Tokenizer compatibility → **PATCHED** (4.1)
2. Model registry mapping → **PATCHED** (4.2)
3. Config attribute delegation → **PATCHED** (4.3)
4. RoPE partial_rotary_factor → **PATCHED** (4.4)
5. Weight name mapping → **PATCHED** (4.5)
6. Linear attention implementation → **NOT PATCHABLE** — requires new model code + Mamba2 kernels

### What would be needed

A dedicated `qwen3_5.py` in vLLM with:
- `Qwen3_5LinearAttention` class (Mamba2-based)
- Hybrid layer dispatch based on `config.layer_types`
- Vision encoder weight skipping or loading
- MTP weight handling

This is beyond the scope of config/registry monkey-patching.

## 6. Conclusion

**Qwen3.5-4B cannot be served via vLLM 0.8.5 on CUDA 12.4.**

The CUDA 12.4 + torch 2.6.0+cu124 + transformers 5.2.0 + vLLM 0.8.5 intersection is otherwise viable (all imports, CUDA init, and config loading succeed). The blocker is architectural: vLLM 0.8.5 lacks linear attention (Mamba2) support required by Qwen3.5's hybrid layer architecture.

Per instructions: 9B was not tested since 4B failed.

### Potential paths forward (not explored in this report)

- vLLM ≥ 0.9.x or ≥ 0.10.x which may have native Qwen3.5 support with linear attention
- SGLang or other inference engines with Qwen3.5 support
- HuggingFace transformers direct inference (no vLLM) — works but much slower, no continuous batching

## 7. RESOLVED: vLLM 0.17.0 with native Qwen3.5 support

**Status: SUCCESS — Qwen3.5-4B served via vLLM 0.17.0 on GPU 1, port 8024.**

### Environment: `vllm017_full`

| Package | Version |
|---------|---------|
| python | 3.11 |
| torch | 2.10.0+cu128 |
| transformers | 4.57.6 |
| vllm | 0.17.0 |
| CUDA runtime | 12.8 |

All packages are CUDA 12.x — **no cu13 components**. CUDA 12.8 forward-compatible with driver 545 (CUDA 12.3 native).

### Why vLLM 0.17.0 works

vLLM 0.17.0 ships a native Qwen3.5 model implementation:
- `vllm/model_executor/models/qwen3_5.py` — `Qwen3_5GatedDeltaNet` for linear attention (Mamba2-style SSM), hybrid layer dispatch (`linear_attention` vs `full_attention`), `Qwen3_5DecoderLayer`
- `vllm/model_executor/models/qwen3_5_mtp.py` — Multi-Token Predictor support
- `vllm/transformers_utils/configs/qwen3_5.py` — `Qwen3_5Config`, `Qwen3_5TextConfig`
- `vllm/transformers_utils/configs/qwen3_5_moe.py` — `Qwen3_5MoeConfig` (MoE variant)

### Model architecture (observed from checkpoint)

- 33 layers total: 24 `linear_attention` + 9 `full_attention` (layer 0 has both)
- `partial_rotary_factor=0.25` (rotary_dim = 64 for head_dim 256)
- Weights use `model.language_model.*` naming (multimodal prefix)

### Required compat: AutoConfig registration

transformers 4.57.6 does not know `qwen3_5` model_type. Fixed via sitecustomize.py:

**File:** `/data/miniconda3/envs/vllm017_full/lib/python3.11/site-packages/sitecustomize.py`
```python
from transformers import AutoConfig
from vllm.transformers_utils.configs.qwen3_5 import Qwen3_5Config, Qwen3_5TextConfig
from vllm.transformers_utils.configs.qwen3_5_moe import Qwen3_5MoeConfig, Qwen3_5MoeTextConfig
AutoConfig.register('qwen3_5', Qwen3_5Config)
AutoConfig.register('qwen3_5_text', Qwen3_5TextConfig)
AutoConfig.register('qwen3_5_moe', Qwen3_5MoeConfig)
AutoConfig.register('qwen3_5_moe_text', Qwen3_5MoeTextConfig)
```

### Verification results

- `torch.cuda.is_available()` → **True**
- `AutoConfig.from_pretrained("/data/LLMs/Qwen3.5-4B")` → **OK** (Qwen3_5TextConfig)
- Model loading (LLM class) → **OK** (8.61 GiB, 7.9s)
- Text generation → **OK** (correct output)
- vLLM server (port 8024, GPU 1) → **OK** (ready in 41s)
- `/v1/models` → **OK** (returns `qwen35-4b`)
- `/v1/chat/completions` → **OK**

### Server configuration

```bash
vllm serve /data/LLMs/Qwen3.5-4B \
  --host 127.0.0.1 --port 8024 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.35 \
  --max-model-len 8192 --enforce-eager
```

### Running instance

| 项目 | 值 |
|------|-----|
| port | 8024 |
| GPU | 1 |
| PID | 2693968 |
| GPU 显存 | ~77696 MiB used / 3353 MiB free (含其他进程) |
| model 显存 | ~8.6 GiB |
| API base | `http://127.0.0.1:8024/v1` |

### Known caveats

- Linear attention layers trigger FLA shape warnings for short prompts (seq_len < num_heads) — non-critical
- Qwen3.5 outputs thinking/reasoning blocks by default — `content` 字段直接包含 `Thinking Process:` 前缀
- `--enable-auto-tool-choice` with `hermes` parser not tested (likely incompatible with Qwen3.5)
- Runbook: `/data/whn/ACA_model/docs/qwen35_vllm017_runbook.md`
