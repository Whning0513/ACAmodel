# Reward v1 Summary

**Run path:** `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4`
**Task count:** 80
**Row count:** 167

## Method: AgentG

| Metric | Value |
|---|---|
| Round count | 80 |
| Task count | 20 |
| Invalid rate | 0.0000 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 55 | 275.00% |
| T1 invalid | 25 | 125.00% |
| T2 valid no-hit | 0 | 0.00% |
| T3 mixed-hit | 0 | 0.00% |
| T4 pure point | 0 | 0.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 0 | 0.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.0000 (0 tasks)
- **Average hit rate:** 0.0000
- **Average unique hit count:** 0.00
- **Invalid rate:** 0.0000
- **Average task latency:** 11.80s
- **Total task latency:** 236.0s
- **Max task latency:** 20.8s

### T6 Pure Broad Family

- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__00ee942db13e`
  - PID: atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__00ee942db13e/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__015e765262e3` | atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View | hit=3/16 | unique=3 | score=303.3
- `codecontests_incorrect__015e765262e3` | atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View | hit=3/16 | unique=3 | score=303.3

**Warning:** 42 rows have seed_count=0 (no_inputs_generated).

**Warning:** 20 rows have no generator_path.

## Method: BaseCG

| Metric | Value |
|---|---|
| Round count | 20 |
| Task count | 20 |
| Invalid rate | 0.1500 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 9 | 45.00% |
| T1 invalid | 3 | 15.00% |
| T2 valid no-hit | 3 | 15.00% |
| T3 mixed-hit | 4 | 20.00% |
| T4 pure point | 0 | 0.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 1 | 5.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.0500 (1 tasks)
- **Average hit rate:** 0.1437
- **Average unique hit count:** 2.30
- **Invalid rate:** 0.1500
- **Average task latency:** 12.74s
- **Total task latency:** 254.9s
- **Max task latency:** 182.9s

### T6 Pure Broad Family

- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__00ee942db13e`
  - PID: atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__00ee942db13e/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__015e765262e3` | atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View | hit=3/16 | unique=3 | score=303.3
- `codecontests_incorrect__015e765262e3` | atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View | hit=3/16 | unique=3 | score=303.3

**Warning:** 42 rows have seed_count=0 (no_inputs_generated).

**Warning:** 20 rows have no generator_path.

## Method: BaseG

| Metric | Value |
|---|---|
| Round count | 20 |
| Task count | 20 |
| Invalid rate | 0.0500 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 9 | 45.00% |
| T1 invalid | 1 | 5.00% |
| T2 valid no-hit | 5 | 25.00% |
| T3 mixed-hit | 2 | 10.00% |
| T4 pure point | 0 | 0.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 3 | 15.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.1500 (3 tasks)
- **Average hit rate:** 0.2406
- **Average unique hit count:** 3.85
- **Invalid rate:** 0.0500
- **Average task latency:** 3.58s
- **Total task latency:** 71.6s
- **Max task latency:** 5.5s

### T6 Pure Broad Family

- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__00ee942db13e`
  - PID: atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__00ee942db13e/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__015e765262e3` | atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View | hit=3/16 | unique=3 | score=303.3
- `codecontests_incorrect__015e765262e3` | atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View | hit=3/16 | unique=3 | score=303.3

**Warning:** 42 rows have seed_count=0 (no_inputs_generated).

**Warning:** 20 rows have no generator_path.

## Method: ITERG

| Metric | Value |
|---|---|
| Round count | 47 |
| Task count | 20 |
| Invalid rate | 0.1000 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 18 | 90.00% |
| T1 invalid | 8 | 40.00% |
| T2 valid no-hit | 16 | 80.00% |
| T3 mixed-hit | 4 | 20.00% |
| T4 pure point | 0 | 0.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 1 | 5.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.0500 (1 tasks)
- **Average hit rate:** 0.1437
- **Average unique hit count:** 2.30
- **Invalid rate:** 0.1000
- **Average task latency:** 47.17s
- **Total task latency:** 943.4s
- **Max task latency:** 730.8s

### T6 Pure Broad Family

- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__00ee942db13e`
  - PID: atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__00ee942db13e/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen25_coder_7b/runs/gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00c828799f38` | codeforces__cf_1328_F | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4
- `codecontests_incorrect__015e765262e3` | atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View | hit=3/16 | unique=3 | score=303.3
- `codecontests_incorrect__015e765262e3` | atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View | hit=3/16 | unique=3 | score=303.3

**Warning:** 42 rows have seed_count=0 (no_inputs_generated).

**Warning:** 20 rows have no generator_path.

