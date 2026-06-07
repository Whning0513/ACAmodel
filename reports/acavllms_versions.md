# ACAvllms Versions

- environment: `/data/miniconda3/envs/ACAvllms`
- python: `3.12.13`
- torch: `2.11.0+cu130`
- torch cuda: `13.0`
- transformers: `5.10.2`
- vllm: `0.22.1`

## nvidia-smi

```text
0, NVIDIA A800 80GB PCIe, 64750, 81920
1, NVIDIA A800 80GB PCIe, 48958, 81920
2, NVIDIA A800 80GB PCIe, 61313, 81920
3, NVIDIA A800 80GB PCIe, 61313, 81920
4, NVIDIA A800 80GB PCIe, 66987, 81920
5, NVIDIA A800 80GB PCIe, 70011, 81920
6, NVIDIA A800 80GB PCIe, 72881, 81920
7, NVIDIA A800 80GB PCIe, 66523, 81920
```

## AutoConfig

- `/data/LLMs/Qwen3.5-4B` -> `qwen3_5` / `Qwen3_5Config`
- `/data/LLMs/Qwen3.5-9B` -> `qwen3_5` / `Qwen3_5Config`
- `/data/LLMs/Qwen2.5-Coder-7B-Instruct` -> `qwen2` / `Qwen2Config`

## vllm017_full (Qwen3.5 native support, CUDA 12.x)

- environment: `/data/miniconda3/envs/vllm017_full`
- python: `3.11`
- torch: `2.10.0+cu128`
- torch cuda: `12.8`
- transformers: `4.57.6`
- vllm: `0.17.0`

vLLM 0.8.5 没有 Qwen3.5 的线性注意力实现。0.17.0 是实测可用的最低版本。
0.22.1 (ACAvllms) 也支持 Qwen3.5，但耦合了 cu130。

详细文档: `/data/whn/ACA_model/docs/vllm017_qwen35_serving.md`
