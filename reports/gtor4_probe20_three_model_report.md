# GTOR4 Probe20 Three-Model Report

## 1. 服务状态

| Model | Port | Env | Service OK | Chat OK | ACA Run OK | Notes |
|---|---:|---|---|---|---|---|
| qwen35-4b | 8024 | vllm017_full | True | True | True | env=vllm017_full reason=preferred_env_ok; artifact_backfill=generator_placeholder_for_parse_failed_agentg |
| qwen25-coder-7b | 8017 | vllm017_full | True | True | True | env=vllm017_full reason=preferred_env_ok |
| qwen35-9b | 8029 | vllm017_full | True | True | True | env=vllm017_full reason=preferred_env_ok |

## 2. 三模型 × 四方法总表

| Model | Method | Success | T0 | T1 | T2 | T3 | T4 | T5 | T6 | Pure@16 | AvgHit | Invalid | Broken | ParseFail | Latency | RawSec | CompileErr | NoInputs |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen35-4b | BaseG | 15 | 13 | 3 | 1 | 2 | 1 | 0 | 0 | 1 | 0.0719 | 0.1500 | 0.6500 | 0 | 31.07 | 621.44 | 5 | 13 |
| qwen35-4b | BaseCG | 15 | 11 | 4 | 3 | 1 | 0 | 0 | 1 | 1 | 0.1219 | 0.2000 | 0.5500 | 0 | 25.93 | 518.59 | 5 | 13 |
| qwen35-4b | ITERG | 15 | 11 | 4 | 3 | 1 | 0 | 0 | 1 | 1 | 0.1313 | 0.2000 | 0.5500 | 0 | 31.75 | 635.08 | 5 | 13 |
| qwen35-4b | AgentG | 6 | 11 | 7 | 2 | 0 | 0 | 0 | 0 | 0 | 0.0000 | 0.3500 | 0.5500 | 7 | 66.28 | 1325.55 | 6 | 16 |
| qwen25-coder-7b | BaseG | 20 | 9 | 1 | 5 | 2 | 0 | 0 | 3 | 3 | 0.2406 | 0.0500 | 0.4500 | 0 | 3.58 | 71.65 | 0 | 4 |
| qwen25-coder-7b | BaseCG | 20 | 9 | 3 | 3 | 4 | 0 | 0 | 1 | 1 | 0.1437 | 0.1500 | 0.4500 | 0 | 12.74 | 254.80 | 0 | 6 |
| qwen25-coder-7b | ITERG | 20 | 9 | 2 | 4 | 4 | 0 | 0 | 1 | 1 | 0.1437 | 0.1000 | 0.4500 | 0 | 47.18 | 943.62 | 0 | 5 |
| qwen25-coder-7b | AgentG | 19 | 11 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0000 | 0.4500 | 0.5500 | 0 | 11.81 | 236.23 | 8 | 20 |
| qwen35-9b | BaseG | 19 | 9 | 0 | 4 | 4 | 0 | 0 | 3 | 3 | 0.2500 | 0.0000 | 0.4500 | 0 | 20.81 | 416.12 | 1 | 8 |
| qwen35-9b | BaseCG | 16 | 10 | 0 | 5 | 3 | 1 | 0 | 1 | 2 | 0.1906 | 0.0000 | 0.5000 | 0 | 17.45 | 348.94 | 4 | 9 |
| qwen35-9b | ITERG | 16 | 10 | 0 | 5 | 3 | 1 | 0 | 1 | 2 | 0.1906 | 0.0000 | 0.5000 | 0 | 27.80 | 556.04 | 4 | 9 |
| qwen35-9b | AgentG | 11 | 12 | 2 | 2 | 1 | 3 | 0 | 0 | 3 | 0.1906 | 0.1000 | 0.6000 | 8 | 45.05 | 901.02 | 6 | 11 |

## 3. 模型比较

- Qwen3.5-4B 是否可用：可用。
- Qwen2.5-Coder-7B 是否最稳：否，以 BaseCG/整体 tier-hitrate 为主判断。
- Qwen3.5-9B 是否可用：可用。
- 模型变大是否降低 T0/T1：是。
- 模型变大是否提高 T3/T4/T5/T6：是。
- 模型变大是否改善 AgentG：是。

## 4. 方法比较

- BaseCG 是否优于 BaseG：否或接近。
- ITERG 是否优于 BaseCG：是。
- AgentG 是否优于 BaseCG/ITERG：否。
- AgentG 是否还主要受结构化输出/上下文问题限制：结构化输出。

## 5. 后续路线判断

- 后续路线判断：可继续做更大模型上的 AgentG / ITERG probe，但前提是当前服务稳定。
- 后续训练数据建议：考虑 ITERG。

## 6. Constraint

- Fixed qwen output constraint mode: `auto`.
- Constraint effect should be judged mainly from `CompileErr` and `NoInputs` columns, especially for qwen35-4b / qwen35-9b GTOR rows.

## 7. ITERG / AgentG 附加统计

- qwen35-4b ITERG: latest=T0 broken, best=T0 broken, best_hit_avg=2.1, later_improved=0, rounds_avg=1.3, context_warn=0, tool_parse_fail=0, normalization=0
- qwen35-4b AgentG: latest=T0 broken, best=T0 broken, best_hit_avg=0.0, later_improved=1, rounds_avg=2.95, context_warn=0, tool_parse_fail=0, normalization=0
- qwen25-coder-7b ITERG: latest=T0 broken, best=T0 broken, best_hit_avg=2.3, later_improved=0, rounds_avg=2.35, context_warn=0, tool_parse_fail=0, normalization=0
- qwen25-coder-7b AgentG: latest=T0 broken, best=T0 broken, best_hit_avg=0.0, later_improved=2, rounds_avg=4.0, context_warn=0, tool_parse_fail=0, normalization=0
- qwen35-9b ITERG: latest=T0 broken, best=T0 broken, best_hit_avg=3.05, later_improved=0, rounds_avg=1.75, context_warn=0, tool_parse_fail=0, normalization=0
- qwen35-9b AgentG: latest=T0 broken, best=T0 broken, best_hit_avg=3.05, later_improved=2, rounds_avg=2.15, context_warn=0, tool_parse_fail=0, normalization=0

## 8. Recap

- 哪个模型能服务：qwen35-4b, qwen25-coder-7b, qwen35-9b。
- 哪个模型跑完 probe20：qwen35-4b, qwen25-coder-7b, qwen35-9b。
- 四方法谁最稳：BaseG。
- AgentG 是否随模型变大改善：改善。
- 是否可以进入 100-task / k=3 / training_records：可以进入 100-task。
- 下一步只建议一件事：先把 BaseG 扩到 100-task probe，验证简单方法的稳定上限。
