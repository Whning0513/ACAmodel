# ACAvllms Notes

- Use `/data/miniconda3/envs/ACAvllms` for Qwen3.5 local serving compatibility work.
- Do not modify `/data/miniconda3/envs/herald` for Qwen3.5 serving validation.
- Do not modify or move model files under `/data/LLMs`.
- Do not write downloads or caches into `~` or `/home/hengningwang`.
- Use these cache and temp locations:
  - `TMPDIR=/data/whn/tmp`
  - `PIP_CACHE_DIR=/data/whn/tmp/acavllms-pip-cache`
  - `HF_HOME=/data/whn/tmp/acavllms-hf`
  - `XDG_CACHE_HOME=/data/whn/tmp/acavllms-xdg`
- Standard service scripts live in `/data/whn/ACA_model/scripts`.
