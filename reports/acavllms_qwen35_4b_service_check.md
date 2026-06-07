# ACAvllms Qwen3.5-4B Service Check

Date: 2026-06-06

## Scope

This check only covered the standardized four-step service flow:

1. `report_acavllms_versions.sh`
2. `start_acavllms_vllm.sh qwen35-4b 8024 1`
3. `check_vllm_server.sh 8024`
4. `stop_vllm_server.sh 8024`

No ACA experiment, smoke, or training was run.

## Step Results

### Step 1: version report

- Command:
  `bash /data/whn/ACA_model/scripts/report_acavllms_versions.sh`
- Result:
  success
- Output file:
  `/data/whn/ACA_model/reports/acavllms_versions.md`

### Step 2: start Qwen3.5-4B

- Command:
  `bash /data/whn/ACA_model/scripts/start_acavllms_vllm.sh qwen35-4b 8024 1`
- Result:
  failed
- Failure stage:
  vLLM engine initialization

## Root Cause

The failure was not caused by:

- `qwen3_5` config recognition
- ACA method logic
- model file corruption
- port conflict

The failure was caused by a CUDA driver/runtime mismatch in the new ACAvllms stack.

Observed error:

```text
RuntimeError: The NVIDIA driver on your system is too old (found version 12030).
Please update your GPU driver ...
```

Meaning:

- `ACAvllms` now has a newer serving stack:
  - `torch 2.11.0+cu130`
  - `vllm 0.22.1`
  - `transformers 5.10.2`
- but the machine driver reported by `nvidia-smi` is:
  - `Driver Version: 545.29.06`
  - `CUDA Version: 12.3`
- the new Torch build expects a newer driver/runtime than the current machine provides

So this check advanced past the old blocker:

- old blocker: `transformers/vllm` could not recognize `model_type=qwen3_5`

and reached the new blocker:

- new blocker: driver/runtime compatibility for the new Torch/vLLM stack

## Step 3: check server

- Command:
  `bash /data/whn/ACA_model/scripts/check_vllm_server.sh 8024`
- Result:
  not run

Reason:

- step 2 never produced a ready server
- `/v1/models` and `/v1/chat/completions` were therefore not available for validation

## Step 4: stop server

- Command:
  `bash /data/whn/ACA_model/scripts/stop_vllm_server.sh 8024`
- Result:
  success
- Output:
  - `STOPPED=1`
  - `PORT=8024`
  - `PID=2149257`

## Files

- log:
  `/data/whn/ACA_model/logs/vllm/qwen35-4b_8024.log`
- version report:
  `/data/whn/ACA_model/reports/acavllms_versions.md`

## Current Conclusion

Current status for `Qwen3.5-4B` under `ACAvllms`:

- `AutoConfig` recognition: success
- vLLM startup: failed
- `/v1/models`: unavailable
- `/v1/chat/completions`: unavailable

This means the `qwen3_5` architecture-recognition problem is resolved in `ACAvllms`,
but the service still cannot start until the CUDA driver / Torch / vLLM compatibility gap is resolved.
