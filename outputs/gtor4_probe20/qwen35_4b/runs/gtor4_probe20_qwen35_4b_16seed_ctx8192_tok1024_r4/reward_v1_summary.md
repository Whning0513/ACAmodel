# Reward v1 Summary

**Run path:** `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_4b/runs/gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4`
**Task count:** 80
**Row count:** 125

## Method: AgentG

| Metric | Value |
|---|---|
| Round count | 59 |
| Task count | 20 |
| Invalid rate | 0.0000 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 36 | 180.00% |
| T1 invalid | 20 | 100.00% |
| T2 valid no-hit | 3 | 15.00% |
| T3 mixed-hit | 0 | 0.00% |
| T4 pure point | 0 | 0.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 0 | 0.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.0000 (0 tasks)
- **Average hit rate:** 0.0000
- **Average unique hit count:** 0.00
- **Invalid rate:** 0.0000
- **Average task latency:** 66.28s
- **Total task latency:** 1325.7s
- **Max task latency:** 115.0s

### T6 Pure Broad Family

- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_4b/runs/gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_4b/runs/gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`

### T4 Pure Point

- `codecontests_incorrect__019ebd1ee1bb` | atcoder__p03986 AtCoder Grand Contest 005 - STring | hit=16/16 | unique=1 | score=416.11

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=9/16 | unique=9 | score=309.9
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__01251420ec1b` | aizu__p02257 Prime Numbers | hit=1/16 | unique=1 | score=301.11

**Warning:** 35 rows have seed_count=0 (no_inputs_generated).

**Warning:** 14 rows have no generator_path.

## Method: BaseCG

| Metric | Value |
|---|---|
| Round count | 20 |
| Task count | 20 |
| Invalid rate | 0.2000 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 11 | 55.00% |
| T1 invalid | 4 | 20.00% |
| T2 valid no-hit | 3 | 15.00% |
| T3 mixed-hit | 1 | 5.00% |
| T4 pure point | 0 | 0.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 1 | 5.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.0500 (1 tasks)
- **Average hit rate:** 0.1219
- **Average unique hit count:** 1.95
- **Invalid rate:** 0.2000
- **Average task latency:** 25.92s
- **Total task latency:** 518.4s
- **Max task latency:** 36.5s

### T6 Pure Broad Family

- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_4b/runs/gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_4b/runs/gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`

### T4 Pure Point

- `codecontests_incorrect__019ebd1ee1bb` | atcoder__p03986 AtCoder Grand Contest 005 - STring | hit=16/16 | unique=1 | score=416.11

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=9/16 | unique=9 | score=309.9
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__01251420ec1b` | aizu__p02257 Prime Numbers | hit=1/16 | unique=1 | score=301.11

**Warning:** 35 rows have seed_count=0 (no_inputs_generated).

**Warning:** 14 rows have no generator_path.

## Method: BaseG

| Metric | Value |
|---|---|
| Round count | 20 |
| Task count | 20 |
| Invalid rate | 0.2000 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 13 | 65.00% |
| T1 invalid | 3 | 15.00% |
| T2 valid no-hit | 1 | 5.00% |
| T3 mixed-hit | 2 | 10.00% |
| T4 pure point | 1 | 5.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 0 | 0.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.0500 (1 tasks)
- **Average hit rate:** 0.0719
- **Average unique hit count:** 0.40
- **Invalid rate:** 0.2000
- **Average task latency:** 31.07s
- **Total task latency:** 621.3s
- **Max task latency:** 57.7s

### T6 Pure Broad Family

- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_4b/runs/gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_4b/runs/gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`

### T4 Pure Point

- `codecontests_incorrect__019ebd1ee1bb` | atcoder__p03986 AtCoder Grand Contest 005 - STring | hit=16/16 | unique=1 | score=416.11

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=9/16 | unique=9 | score=309.9
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__01251420ec1b` | aizu__p02257 Prime Numbers | hit=1/16 | unique=1 | score=301.11

**Warning:** 35 rows have seed_count=0 (no_inputs_generated).

**Warning:** 14 rows have no generator_path.

## Method: ITERG

| Metric | Value |
|---|---|
| Round count | 26 |
| Task count | 20 |
| Invalid rate | 0.2000 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 11 | 55.00% |
| T1 invalid | 10 | 50.00% |
| T2 valid no-hit | 3 | 15.00% |
| T3 mixed-hit | 1 | 5.00% |
| T4 pure point | 0 | 0.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 1 | 5.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.0500 (1 tasks)
- **Average hit rate:** 0.1313
- **Average unique hit count:** 1.80
- **Invalid rate:** 0.2000
- **Average task latency:** 31.75s
- **Total task latency:** 634.9s
- **Max task latency:** 89.1s

### T6 Pure Broad Family

- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_4b/runs/gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_4b/runs/gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`

### T4 Pure Point

- `codecontests_incorrect__019ebd1ee1bb` | atcoder__p03986 AtCoder Grand Contest 005 - STring | hit=16/16 | unique=1 | score=416.11

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=9/16 | unique=9 | score=309.9
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__01251420ec1b` | aizu__p02257 Prime Numbers | hit=1/16 | unique=1 | score=301.11

**Warning:** 35 rows have seed_count=0 (no_inputs_generated).

**Warning:** 14 rows have no generator_path.

