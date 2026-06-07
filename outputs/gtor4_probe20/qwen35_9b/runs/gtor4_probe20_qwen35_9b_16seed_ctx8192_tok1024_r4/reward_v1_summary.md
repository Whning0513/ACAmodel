# Reward v1 Summary

**Run path:** `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4`
**Task count:** 80
**Row count:** 118

## Method: AgentG

| Metric | Value |
|---|---|
| Round count | 43 |
| Task count | 20 |
| Invalid rate | 0.0500 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 31 | 155.00% |
| T1 invalid | 2 | 10.00% |
| T2 valid no-hit | 6 | 30.00% |
| T3 mixed-hit | 1 | 5.00% |
| T4 pure point | 3 | 15.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 0 | 0.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.1500 (3 tasks)
- **Average hit rate:** 0.1906
- **Average unique hit count:** 0.45
- **Invalid rate:** 0.0500
- **Average task latency:** 45.05s
- **Total task latency:** 900.9s
- **Max task latency:** 98.6s

### T6 Pure Broad Family

- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__007b42817639`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__007b42817639/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`

### T4 Pure Point

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=16/16 | unique=1 | score=416.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=16/16 | unique=1 | score=416.14
- `codecontests_incorrect__01843bdac324` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=16/16 | unique=1 | score=416.1
- `codecontests_incorrect__016403d6ce05` | atcoder__p03150 KEYENCE Programming Contest 2019 - KEYENCE String | hit=16/16 | unique=1 | score=416.11
- `codecontests_incorrect__016403d6ce05` | atcoder__p03150 KEYENCE Programming Contest 2019 - KEYENCE String | hit=16/16 | unique=1 | score=416.11

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__009bbfe1d0fb` | codeforces__cf_1037_B | hit=6/16 | unique=6 | score=306.61
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4

**Warning:** 23 rows have seed_count=0 (no_inputs_generated).

**Warning:** 8 rows have no generator_path.

## Method: BaseCG

| Metric | Value |
|---|---|
| Round count | 20 |
| Task count | 20 |
| Invalid rate | 0.0000 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 10 | 50.00% |
| T1 invalid | 0 | 0.00% |
| T2 valid no-hit | 5 | 25.00% |
| T3 mixed-hit | 3 | 15.00% |
| T4 pure point | 1 | 5.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 1 | 5.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.1000 (2 tasks)
- **Average hit rate:** 0.1906
- **Average unique hit count:** 2.30
- **Invalid rate:** 0.0000
- **Average task latency:** 17.44s
- **Total task latency:** 348.8s
- **Max task latency:** 42.1s

### T6 Pure Broad Family

- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__007b42817639`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__007b42817639/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`

### T4 Pure Point

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=16/16 | unique=1 | score=416.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=16/16 | unique=1 | score=416.14
- `codecontests_incorrect__01843bdac324` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=16/16 | unique=1 | score=416.1
- `codecontests_incorrect__016403d6ce05` | atcoder__p03150 KEYENCE Programming Contest 2019 - KEYENCE String | hit=16/16 | unique=1 | score=416.11
- `codecontests_incorrect__016403d6ce05` | atcoder__p03150 KEYENCE Programming Contest 2019 - KEYENCE String | hit=16/16 | unique=1 | score=416.11

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__009bbfe1d0fb` | codeforces__cf_1037_B | hit=6/16 | unique=6 | score=306.61
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4

**Warning:** 23 rows have seed_count=0 (no_inputs_generated).

**Warning:** 8 rows have no generator_path.

## Method: BaseG

| Metric | Value |
|---|---|
| Round count | 20 |
| Task count | 20 |
| Invalid rate | 0.0000 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 9 | 45.00% |
| T1 invalid | 0 | 0.00% |
| T2 valid no-hit | 4 | 20.00% |
| T3 mixed-hit | 4 | 20.00% |
| T4 pure point | 0 | 0.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 3 | 15.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.1500 (3 tasks)
- **Average hit rate:** 0.2500
- **Average unique hit count:** 4.00
- **Invalid rate:** 0.0000
- **Average task latency:** 20.79s
- **Total task latency:** 415.8s
- **Max task latency:** 37.4s

### T6 Pure Broad Family

- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__007b42817639`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__007b42817639/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`

### T4 Pure Point

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=16/16 | unique=1 | score=416.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=16/16 | unique=1 | score=416.14
- `codecontests_incorrect__01843bdac324` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=16/16 | unique=1 | score=416.1
- `codecontests_incorrect__016403d6ce05` | atcoder__p03150 KEYENCE Programming Contest 2019 - KEYENCE String | hit=16/16 | unique=1 | score=416.11
- `codecontests_incorrect__016403d6ce05` | atcoder__p03150 KEYENCE Programming Contest 2019 - KEYENCE String | hit=16/16 | unique=1 | score=416.11

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__009bbfe1d0fb` | codeforces__cf_1037_B | hit=6/16 | unique=6 | score=306.61
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4

**Warning:** 23 rows have seed_count=0 (no_inputs_generated).

**Warning:** 8 rows have no generator_path.

## Method: ITERG

| Metric | Value |
|---|---|
| Round count | 35 |
| Task count | 20 |
| Invalid rate | 0.0000 |

### Tier Distribution

| Tier | Count | Ratio |
|---|---|---|
| T0 broken | 10 | 50.00% |
| T1 invalid | 0 | 0.00% |
| T2 valid no-hit | 20 | 100.00% |
| T3 mixed-hit | 3 | 15.00% |
| T4 pure point | 1 | 5.00% |
| T5 pure family | 0 | 0.00% |
| T6 pure broad family | 1 | 5.00% |

### Key Metrics

- **Pure@16 task ratio:** 0.1000 (2 tasks)
- **Average hit rate:** 0.1906
- **Average unique hit count:** 2.30
- **Invalid rate:** 0.0000
- **Average task latency:** 27.80s
- **Total task latency:** 556.0s
- **Max task latency:** 165.3s

### T6 Pure Broad Family

- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseCG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__007b42817639`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__007b42817639/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`
- `codecontests_incorrect__019ebd1ee1bb`
  - PID: atcoder__p03986 AtCoder Grand Contest 005 - STring
  - Hit count: 16/16, Unique: 16
  - Score: 617.61
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/BaseG/codecontests_incorrect__019ebd1ee1bb/generator_code_round_1.py`
- `codecontests_incorrect__015e765262e3`
  - PID: atcoder__p03072 AtCoder Beginner Contest 124 - Great Ocean View
  - Hit count: 16/16, Unique: 16
  - Score: 617.6
  - Generator: `/data/whn/ACA_model/outputs/gtor4_probe20/qwen35_9b/runs/gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4/tasks/ITERG/codecontests_incorrect__015e765262e3/generator_code_round_1.py`

### T4 Pure Point

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=16/16 | unique=1 | score=416.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=16/16 | unique=1 | score=416.14
- `codecontests_incorrect__01843bdac324` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=16/16 | unique=1 | score=416.1
- `codecontests_incorrect__016403d6ce05` | atcoder__p03150 KEYENCE Programming Contest 2019 - KEYENCE String | hit=16/16 | unique=1 | score=416.11
- `codecontests_incorrect__016403d6ce05` | atcoder__p03150 KEYENCE Programming Contest 2019 - KEYENCE String | hit=16/16 | unique=1 | score=416.11

### T3 Mixed-Hit (top samples)

- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__002576ec6455` | codeforces__cf_1230_A | hit=11/16 | unique=11 | score=312.1
- `codecontests_incorrect__00873750250e` | atcoder__p02975 AtCoder Grand Contest 035 - XOR Circle | hit=11/16 | unique=11 | score=312.14
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__009bbfe1d0fb` | codeforces__cf_1037_B | hit=6/16 | unique=6 | score=306.61
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=6/16 | unique=6 | score=306.6
- `codecontests_incorrect__00ee942db13e` | atcoder__p02603 M-SOLUTIONS Programming Contest 2020 - Road to Millionaire | hit=4/16 | unique=4 | score=304.4

**Warning:** 23 rows have seed_count=0 (no_inputs_generated).

**Warning:** 8 rows have no generator_path.

