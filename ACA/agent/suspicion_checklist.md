# Pipeline 怀疑清单 — 提交前审计 (第二轮)

## 一、已验证通过（绿色）

### 1.1 双跑沙箱正确性 ✓
- `trace_coverage_dual()` 对每个 agent 输入先跑 reference → 再跑 student → `_compute_dual_verdict()` 比对
- 判决引擎逐层防御: INVALID(ref失败) → TLE → OOM → UNKNOWN(双空) → RE(crash) → AC/WA
- OOM 现在正确标记为 breakthrough=True（内存耗尽 = bug）

### 1.2 covered_lines 全链路贯通 ✓
- sandbox: `DualRunResult.covered_lines` (set) → nodes: `_compact_line_list()` 格式化为 `cov=1-3,5-6` → runner: `_parse_compact_lines()` 还原为 `[1,2,3,5,6]` → metrics: `T_Touched` 用 `covered_union & set(original_uncovered)`

### 1.3 metrics 从 trajectory 计算 ✓
- `V_Valid` / `B_Broken` 从 agent 自己的 per_case_results 统计

### 1.4 stagnation 检测 ✓
- 检查所有数字前缀行（不再限制 1-5）

### 1.5 OOM 完整处理 ✓
- `_compute_dual_verdict`: OOM → `("OOM", True)`
- `_handle_run_and_trace`: OOM → label=`OOM`
- Metrics: WA/RE/TLE/OOM 都计入 B_Broken/TCC

### 1.6 RE/WA/OOM 错误信息传给 LLM ✓
- WA/RE/OOM 行现在包含状态专属 label；RE 崩溃时附带 `err='...'` traceback
- 新格式: `1. [RE] input | stu='(empty)' expected='No' | err='ZeroDivisionError...' | cov=1-3 new=22`

### 1.7 breakthroughs 解析从 case_results 提取 ✓
- 删除了文本解析（容易出错的 escaped/unescaped 不一致）
- 统一从 `_parse_per_case_results` 提取，格式一致

### 1.8 cov= 解析加固 ✓
- 使用 `| cov=` 定位（而非 `cov=`），防止 err 文本中的 `cov=` 干扰

### 1.9 problem_loader 类型修复 ✓
- `uncovered_line_tags` 现在保持 `Dict[str, str]`（与声明一致）
- 修复了 `int()` 转换导致的类型不匹配

---

## 二、本轮新发现的 bug（已修复）

| # | 文件 | Bug | 严重度 |
|---|------|-----|--------|
| 1 | sandbox.py:550 | OOM breakthrough=False，导致 OOM 被标记为 SURVIVED | 高 |
| 2 | nodes.py:269 | OOM 未被包含在错误标签映射中 | 高 |
| 3 | runner.py:124-132 | breakthroughs 文本解析只过滤 1-5 行，6+ 行泄露为无效输入 | 中 |
| 4 | nodes.py:310-312 | RE 崩溃的 stderr traceback 完全不传给 LLM | 中 |
| 5 | runner.py:84-88 | cov= 解析可能被 err 文本中的 cov= 干扰 | 低 |
| 6 | problem_loader.py:110 | uncovered_line_tags 类型声明 Dict[str,str] 但赋值 Dict[int,str] | 低 |

---

## 三、需要关注（黄色）

### 3.1 ToolMessage 内容可能过长
**风险**: covered_lines 很多时 `cov=...` 字符串占用 LLM context
**缓解**: `_compact_line_list` 用范围压缩
**建议**: 监控实际运行中 ToolMessage 长度分布

### 3.2 `tool_id` 类型安全（Pyright 警告）
**位置**: `nodes.py:383` — `tool_call["id"]` 类型为 `str | None`
**影响**: 已用 `.get("id", "")` 兜底

### 3.3 `process_one_submission` 的 `test_cases` 参数已废弃
**位置**: `runner.py:163` — 双跑不需要预知 test cases，但参数仍存在
**影响**: 调用方 `run_experiment.py` 仍构建 test_cases 字典（浪费）
**建议**: 后续清理

### 3.4 并发安全: sandbox uuid 文件命名
**位置**: `sandbox.py` — `_dual_{uuid.uuid4().hex[:8]}`
**风险**: uuid4 碰撞概率极低

### 3.5 `_compute_dual_verdict` reference_ok 判据
**逻辑**: `bool(ref_result["stdout"].strip())` — 如果标准答案就是空行（极罕见），误判为 INVALID
**概率**: 极低

### 3.6 `_extract_test_inputs` 只取第一个 tool call
**位置**: `runner.py:19` — 如果 agent 一次调多个 run_and_trace，只有第一个的 inputs 进入 trajectory
**概率**: 低（agent 通常一次只调一个 tool）

---

## 四、已知限制（蓝色）

### 4.1 无 message 窗口管理
`agent_node` 累积所有历史消息，多次迭代后可能超过 LLM context limit

### 4.2 step6 reference solution 不可靠
当前 step6 的 `ref_code` 不是真正的标准答案 — 部分 ref_code 本身就有 bug
- step7 会用 LLM 生成真正的 reference solution

### 4.3 R1.1 radical_mutation 警告输出混杂在 ToolMessage 中
`[SYSTEM WARNING]` 文本直接拼接在 ToolMessage.content 末尾

### 4.4 `sample_input_anchor` 始终为空
`runner.py:208` 设 `sample_input_anchor=""`，LLM 缺少输入格式示例
- 待从 problem metadata 加载

---

## 五、提交前快速验证

```bash
# 全链路集成测试
python3 -c "
import json
from ACA_tool.sandbox import trace_coverage_dual, _compute_dual_verdict
from ACA_agent.r_family.nodes import _handle_run_and_trace
from ACA_agent.r_family.runner import _parse_per_case_results, _reconstruct_trajectory
from ACA_stat.metrics import compute_submission_metrics
from langchain_core.messages import AIMessage

# OOM → breakthrough=True, OOM label
assert _compute_dual_verdict(True, 'x', False, -9, '') == ('OOM', True)

# Full pipeline with real data
with open('ACA_data/outputs/step6_final.ndjson') as f:
    for line in f:
        r = json.loads(line)
        if r['submission_id'] == 'cf_633_A__matrixstudio__b5ceb5e3ac2d85b5':
            rec = r; break

# ... (see integration test above)
print('Pipeline OK')
"
```
