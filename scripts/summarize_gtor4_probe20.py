#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path("/data/whn/ACA_model")
OUTPUT_BASE = ROOT / "outputs" / "gtor4_probe20"
REPORT_PATH = ROOT / "reports" / "gtor4_probe20_three_model_report.md"
MODEL_ORDER = [
    ("qwen35-4b", "qwen35_4b"),
    ("qwen25-coder-7b", "qwen25_coder_7b"),
    ("qwen35-9b", "qwen35_9b"),
]
METHODS = ["BaseG", "BaseCG", "ITERG", "AgentG"]
TIER_ORDER = {
    "T0 broken": 0,
    "T1 invalid": 1,
    "T2 valid no-hit": 2,
    "T3 mixed-hit": 3,
    "T4 pure point": 4,
    "T5 pure family": 5,
    "T6 pure broad family": 6,
}
TIER_LABELS = [k for k, _ in sorted(TIER_ORDER.items(), key=lambda item: item[1])]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_run_dir(model_dir: Path) -> Path | None:
    runs_dir = model_dir / "runs"
    if not runs_dir.exists():
        return None
    runs = [p for p in runs_dir.iterdir() if p.is_dir()]
    return sorted(runs)[-1] if runs else None


def best_row(rows: list[dict]) -> dict:
    def key(row: dict) -> tuple:
        tier = TIER_ORDER.get(row["tier"], -1)
        hit_count = int(row.get("hit_count", 0) or 0)
        reward = float(row.get("reward_v1_score", 0) or 0)
        round_id = int(row.get("round_id", 0) or 0)
        return (tier, hit_count, reward, -round_id)

    return max(rows, key=key)


def scan_task_statuses(run_dir: Path) -> dict[tuple[str, str], dict]:
    out = {}
    for path in run_dir.glob("tasks/*/*/task_status.json"):
        status = load_json(path)
        method = path.parent.parent.name
        sid = path.parent.name
        out[(method, sid)] = status
    return out


def read_reward_rows(run_dir: Path) -> list[dict]:
    path = run_dir / "reward_v1_table.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_trajectory_stats(task_dir: Path) -> dict:
    stats = {
        "normalization_applied_count": 0,
        "context_too_long_warning_count": 0,
        "tool_call_parse_failure_count": 0,
    }
    traj = task_dir / "trajectory.jsonl"
    if traj.exists():
      for line in traj.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            meta = obj.get("normalization_meta") or {}
            if meta.get("normalization_applied"):
                stats["normalization_applied_count"] += 1
            blob = json.dumps(obj, ensure_ascii=False)
            if "context_too_long" in blob or "context-too-long" in blob:
                stats["context_too_long_warning_count"] += 1
            if "tool_call_parse_failure" in blob or "tool-call parse failure" in blob:
                stats["tool_call_parse_failure_count"] += 1
    trace = task_dir / "trace.json"
    if trace.exists():
        blob = trace.read_text(encoding="utf-8")
        if "context_too_long" in blob or "context-too-long" in blob:
            stats["context_too_long_warning_count"] += blob.count("context_too_long") + blob.count("context-too-long")
        if "tool_call_parse_failure" in blob or "tool-call parse failure" in blob:
            stats["tool_call_parse_failure_count"] += blob.count("tool_call_parse_failure") + blob.count("tool-call parse failure")
    return stats


def aggregate_run(model_alias: str, model_key: str) -> dict:
    model_dir = OUTPUT_BASE / model_key
    service_path = model_dir / "service_status.json"
    service = load_json(service_path) if service_path.exists() else {
        "model_alias": model_alias,
        "actual_port": None,
        "env": "local-vllm",
        "service_ok": False,
        "chat_ok": False,
        "aca_run_ok": False,
        "notes": "missing service_status.json",
    }
    run_dir = Path(service["run_dir"]) if service.get("run_dir") else latest_run_dir(model_dir)
    if not run_dir or not run_dir.exists():
        return {"service": service, "run_dir": None, "methods": {}}

    rows = read_reward_rows(run_dir)
    statuses = scan_task_statuses(run_dir)
    grouped_rows: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped_rows[(row["method"], row["candidate_id"])].append(row)

    methods = {}
    for method in METHODS:
        task_keys = sorted(k for k in statuses if k[0] == method)
        best_rows = {}
        latest_rows = {}
        tier_counter = Counter()
        latest_tier_counter = Counter()
        stop_counter = Counter()
        success_count = 0
        failed_count = 0
        parse_fail = 0
        no_inputs = 0
        compile_error = 0
        runtime_error = 0
        elapsed = []
        pure_count = 0
        hit_rates = []
        unique_hits = []
        improved_later = 0
        rounds_completed = []
        iterative_extra = Counter()

        for _, sid in task_keys:
            status = statuses[(method, sid)]
            stop_counter[str(status.get("stop_reason") or status.get("terminated_reason") or "unknown")] += 1
            if status.get("status") == "success":
                success_count += 1
            else:
                failed_count += 1
            if str(status.get("stop_reason") or status.get("terminated_reason")) == "llm_parse_failed":
                parse_fail += 1
            elapsed.append(float(status.get("elapsed_sec") or 0))

            task_rows = grouped_rows.get((method, sid), [])
            if not task_rows:
                continue
            best = best_row(task_rows)
            latest = max(task_rows, key=lambda row: int(row.get("round_id", 0) or 0))
            best_rows[sid] = best
            latest_rows[sid] = latest
            tier_counter[best["tier"]] += 1
            latest_tier_counter[latest["tier"]] += 1
            pure_count += 1 if str(best.get("Pure@16")).lower() == "true" else 0
            hit_rates.append(float(best.get("hit_rate", 0) or 0))
            unique_hits.append(float(best.get("unique_hit_count", 0) or 0))
            if int(best.get("seed_count", 0) or 0) == 0 or int(best.get("valid_count", 0) or 0) == 0:
                no_inputs += 1
            if str(best.get("compile_error", "")).lower() == "true":
                compile_error += 1
            if int(best.get("runtime_error_count", 0) or 0) > 0:
                runtime_error += 1
            rounds_completed.append(max(int(r.get("round_id", 0) or 0) for r in task_rows))

            if method in {"ITERG", "AgentG"}:
                first = min(task_rows, key=lambda row: int(row.get("round_id", 0) or 0))
                first_score = (TIER_ORDER.get(first["tier"], -1), float(first.get("reward_v1_score", 0) or 0))
                best_score = (TIER_ORDER.get(best["tier"], -1), float(best.get("reward_v1_score", 0) or 0))
                if best_score > first_score and int(best.get("round_id", 0) or 0) > int(first.get("round_id", 0) or 0):
                    improved_later += 1
                iterative_extra["best_hit_count_sum"] += int(best.get("hit_count", 0) or 0)
                task_dir = Path(best["task_dir"])
                extra = read_trajectory_stats(task_dir)
                iterative_extra.update(extra)

        task_count = len(task_keys)
        methods[method] = {
            "task_count": task_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "stop_reason_distribution": dict(stop_counter),
            "tier_distribution": {label: tier_counter.get(label, 0) for label in TIER_LABELS},
            "latest_tier_distribution": {label: latest_tier_counter.get(label, 0) for label in TIER_LABELS},
            "Pure@16_count": pure_count,
            "Pure@16_ratio": round(pure_count / task_count, 4) if task_count else 0.0,
            "average_hit_rate": round(sum(hit_rates) / len(hit_rates), 4) if hit_rates else 0.0,
            "average_unique_hit_count": round(sum(unique_hits) / len(unique_hits), 4) if unique_hits else 0.0,
            "invalid_rate": round(tier_counter.get("T1 invalid", 0) / task_count, 4) if task_count else 0.0,
            "broken_rate": round(tier_counter.get("T0 broken", 0) / task_count, 4) if task_count else 0.0,
            "llm_parse_failed_count": parse_fail,
            "no_inputs_generated_count": no_inputs,
            "compile_error_count": compile_error,
            "runtime_error_count": runtime_error,
            "average_task_latency_sec": round(sum(elapsed) / len(elapsed), 4) if elapsed else 0.0,
            "total_task_latency_sec": round(sum(elapsed), 4) if elapsed else 0.0,
            "max_task_latency_sec": round(max(elapsed), 4) if elapsed else 0.0,
            "avg_tier_score": round(sum(TIER_ORDER.get(r["tier"], 0) for r in best_rows.values()) / len(best_rows), 4) if best_rows else 0.0,
        }
        if method in {"ITERG", "AgentG"}:
            methods[method].update(
                {
                    "latest_tier": max(methods[method]["latest_tier_distribution"], key=lambda k: methods[method]["latest_tier_distribution"][k]) if task_count else "N/A",
                    "best_round_tier": max(methods[method]["tier_distribution"], key=lambda k: methods[method]["tier_distribution"][k]) if task_count else "N/A",
                    "best_hit_count_avg": round(iterative_extra["best_hit_count_sum"] / task_count, 4) if task_count else 0.0,
                    "whether_later_rounds_improved_count": improved_later,
                    "rounds_completed_avg": round(sum(rounds_completed) / len(rounds_completed), 4) if rounds_completed else 0.0,
                    "context_too_long_warning_count": iterative_extra["context_too_long_warning_count"],
                    "tool_call_parse_failure_count": iterative_extra["tool_call_parse_failure_count"],
                    "normalization_applied_count": iterative_extra["normalization_applied_count"],
                }
            )

    return {"service": service, "run_dir": run_dir, "methods": methods}


def model_method_rows(summary: dict) -> list[tuple]:
    rows = []
    for model_alias, model_key in MODEL_ORDER:
        payload = summary[model_alias]
        for method in METHODS:
            m = payload["methods"].get(method, {})
            td = m.get("tier_distribution", {})
            rows.append(
                (
                    model_alias,
                    method,
                    m.get("success_count", 0),
                    td.get("T0 broken", 0),
                    td.get("T1 invalid", 0),
                    td.get("T2 valid no-hit", 0),
                    td.get("T3 mixed-hit", 0),
                    td.get("T4 pure point", 0),
                    td.get("T5 pure family", 0),
                    td.get("T6 pure broad family", 0),
                    m.get("Pure@16_count", 0),
                    m.get("average_hit_rate", 0.0),
                    m.get("invalid_rate", 0.0),
                    m.get("broken_rate", 0.0),
                    m.get("llm_parse_failed_count", 0),
                    m.get("average_task_latency_sec", 0.0),
                    m.get("compile_error_count", 0),
                    m.get("no_inputs_generated_count", 0),
                    m.get("total_task_latency_sec", 0.0),
                )
            )
    return rows


def pick_best_model(summary: dict, method: str) -> str:
    ranked = []
    for model_alias, _ in MODEL_ORDER:
        m = summary[model_alias]["methods"].get(method, {})
        ranked.append((m.get("avg_tier_score", -1), m.get("average_hit_rate", -1), -m.get("broken_rate", 1), model_alias))
    ranked.sort(reverse=True)
    return ranked[0][-1]


def conclusion_lines(summary: dict) -> list[str]:
    lines = []
    completed_models = [model for model, _ in MODEL_ORDER if summary[model]["service"].get("aca_run_ok", False)]
    if not completed_models:
        return [
            "- 目前没有完整 probe20 run，以下比较结论暂不可用。",
            "- Qwen3.5-4B 是否可用：数据不足。",
            "- Qwen2.5-Coder-7B 是否最稳：数据不足。",
            "- Qwen3.5-9B 是否可用：数据不足。",
            "- 模型变大是否降低 T0/T1：数据不足。",
            "- 模型变大是否提高 T3/T4/T5/T6：数据不足。",
            "- 模型变大是否改善 AgentG：数据不足。",
            "- BaseCG 是否优于 BaseG：数据不足。",
            "- ITERG 是否优于 BaseCG：数据不足。",
            "- AgentG 是否优于 BaseCG/ITERG：数据不足。",
            "- AgentG 是否还主要受结构化输出/上下文问题限制：数据不足。",
            "- 后续路线判断：先完成至少一个完整 probe20 run。",
        ]
    service_ok = {
        model: (
            bool(summary[model]["service"]["service_ok"]),
            bool(summary[model]["service"]["chat_ok"]),
            bool(summary[model]["service"]["aca_run_ok"]),
        )
        for model, _ in MODEL_ORDER
    }
    agent_scores = {model: summary[model]["methods"].get("AgentG", {}).get("avg_tier_score", 0.0) for model, _ in MODEL_ORDER}
    baseg_scores = {model: summary[model]["methods"].get("BaseG", {}).get("avg_tier_score", 0.0) for model, _ in MODEL_ORDER}
    basecg_scores = {model: summary[model]["methods"].get("BaseCG", {}).get("avg_tier_score", 0.0) for model, _ in MODEL_ORDER}
    iterg_scores = {model: summary[model]["methods"].get("ITERG", {}).get("avg_tier_score", 0.0) for model, _ in MODEL_ORDER}

    lines.append(f"- Qwen3.5-4B 是否可用：{'可用' if all(service_ok['qwen35-4b']) else '不可用或未完整跑通'}。")
    lines.append(f"- Qwen2.5-Coder-7B 是否最稳：{'是' if pick_best_model(summary, 'BaseCG') == 'qwen25-coder-7b' else '否'}，以 BaseCG/整体 tier-hitrate 为主判断。")
    lines.append(f"- Qwen3.5-9B 是否可用：{'可用' if all(service_ok['qwen35-9b']) else '不可用或未完整跑通'}。")

    q35_4b_bad = sum(summary["qwen35-4b"]["methods"].get(m, {}).get("tier_distribution", {}).get("T0 broken", 0) + summary["qwen35-4b"]["methods"].get(m, {}).get("tier_distribution", {}).get("T1 invalid", 0) for m in METHODS)
    q35_9b_bad = sum(summary["qwen35-9b"]["methods"].get(m, {}).get("tier_distribution", {}).get("T0 broken", 0) + summary["qwen35-9b"]["methods"].get(m, {}).get("tier_distribution", {}).get("T1 invalid", 0) for m in METHODS)
    q35_4b_good = sum(sum(summary["qwen35-4b"]["methods"].get(m, {}).get("tier_distribution", {}).get(t, 0) for t in ["T3 mixed-hit", "T4 pure point", "T5 pure family", "T6 pure broad family"]) for m in METHODS)
    q35_9b_good = sum(sum(summary["qwen35-9b"]["methods"].get(m, {}).get("tier_distribution", {}).get(t, 0) for t in ["T3 mixed-hit", "T4 pure point", "T5 pure family", "T6 pure broad family"]) for m in METHODS)

    lines.append(f"- 模型变大是否降低 T0/T1：{'是' if q35_9b_bad < q35_4b_bad else '否或不明显'}。")
    lines.append(f"- 模型变大是否提高 T3/T4/T5/T6：{'是' if q35_9b_good > q35_4b_good else '否或不明显'}。")
    lines.append(f"- 模型变大是否改善 AgentG：{'是' if agent_scores['qwen35-9b'] > agent_scores['qwen35-4b'] else '否或不明显'}。")

    avg_baseg = sum(baseg_scores.values()) / len(baseg_scores)
    avg_basecg = sum(basecg_scores.values()) / len(basecg_scores)
    avg_iterg = sum(iterg_scores.values()) / len(iterg_scores)
    avg_agentg = sum(agent_scores.values()) / len(agent_scores)
    lines.append(f"- BaseCG 是否优于 BaseG：{'是' if avg_basecg > avg_baseg else '否或接近'}。")
    lines.append(f"- ITERG 是否优于 BaseCG：{'是' if avg_iterg > avg_basecg else '否或接近'}。")
    lines.append(f"- AgentG 是否优于 BaseCG/ITERG：{'是' if avg_agentg > max(avg_basecg, avg_iterg) else '否'}。")

    agent_limits = []
    for model_alias, _ in MODEL_ORDER:
        m = summary[model_alias]["methods"].get("AgentG", {})
        if m.get("context_too_long_warning_count", 0) > 0:
            agent_limits.append("上下文")
        if m.get("tool_call_parse_failure_count", 0) > 0 or m.get("llm_parse_failed_count", 0) > 0:
            agent_limits.append("结构化输出")
    limit_text = "、".join(sorted(set(agent_limits))) if agent_limits else "未观察到显式上下文/结构化输出主导"
    lines.append(f"- AgentG 是否还主要受结构化输出/上下文问题限制：{limit_text}。")

    if agent_scores["qwen25-coder-7b"] > avg_basecg or agent_scores["qwen35-9b"] > agent_scores["qwen35-4b"]:
        lines.append("- 后续路线判断：可继续做更大模型上的 AgentG / ITERG probe，但前提是当前服务稳定。")
    else:
        lines.append("- 后续路线判断：暂停 AgentG，主线回 BaseG / BaseCG / ITERG。")
    if avg_basecg > avg_baseg:
        lines.append("- 后续训练数据建议：优先 BaseCG。")
    if avg_iterg > avg_basecg:
        lines.append("- 后续训练数据建议：考虑 ITERG。")
    if not all(service_ok["qwen35-4b"]) or not all(service_ok["qwen35-9b"]):
        lines.append("- qwen3.5 服务路线：不再继续折腾未稳定的 qwen3.5 服务配置，优先可稳定服务模型。")
    return lines


def next_step_line(summary: dict) -> str:
    if not any(summary[model]["service"].get("aca_run_ok", False) for model, _ in MODEL_ORDER):
        return "下一步只建议一件事：先跑完第一个完整模型的 probe20，再谈 100-task / k=3 / training_records。"
    avg = {}
    for method in METHODS:
        avg[method] = sum(summary[m]["methods"].get(method, {}).get("avg_tier_score", 0.0) for m, _ in MODEL_ORDER) / len(MODEL_ORDER)
    best_method = max(avg, key=avg.get)
    if best_method == "AgentG":
        return "下一步只建议一件事：把 AgentG 扩到 100-task probe，再决定是否进入 training_records。"
    if best_method == "ITERG":
        return "下一步只建议一件事：先把 ITERG 扩到 100-task probe，确认 best-round 优势是否稳定。"
    if best_method == "BaseCG":
        return "下一步只建议一件事：先把 BaseCG 扩到 100-task probe，作为后续 rollout 主线。"
    return "下一步只建议一件事：先把 BaseG 扩到 100-task probe，验证简单方法的稳定上限。"


def main() -> None:
    summary = {model_alias: aggregate_run(model_alias, model_key) for model_alias, model_key in MODEL_ORDER}

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# GTOR4 Probe20 Three-Model Report", ""]

    lines.extend(["## 1. 服务状态", "", "| Model | Port | Env | Service OK | Chat OK | ACA Run OK | Notes |", "|---|---:|---|---|---|---|---|"])
    for model_alias, _ in MODEL_ORDER:
        service = summary[model_alias]["service"]
        lines.append(
            f"| {model_alias} | {service.get('actual_port', 'N/A')} | {service.get('env', 'local-vllm')} | "
            f"{service.get('service_ok', False)} | {service.get('chat_ok', False)} | {service.get('aca_run_ok', False)} | "
            f"{service.get('notes', '')} |"
        )

    lines.extend(["", "## 2. 三模型 × 四方法总表", "", "| Model | Method | Success | T0 | T1 | T2 | T3 | T4 | T5 | T6 | Pure@16 | AvgHit | Invalid | Broken | ParseFail | Latency | RawSec | CompileErr | NoInputs |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for row in model_method_rows(summary):
        lines.append(
            f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} | {row[7]} | {row[8]} | {row[9]} | {row[10]} | {row[11]:.4f} | {row[12]:.4f} | {row[13]:.4f} | {row[14]} | {row[15]:.2f} | {row[18]:.2f} | {row[16]} | {row[17]} |"
        )

    lines.extend(["", "## 3. 模型比较", ""])
    lines.extend(conclusion_lines(summary)[:6])

    lines.extend(["", "## 4. 方法比较", ""])
    lines.extend(conclusion_lines(summary)[6:10])

    lines.extend(["", "## 5. 后续路线判断", ""])
    lines.extend(conclusion_lines(summary)[10:])

    lines.extend(["", "## 6. Constraint", ""])
    qwen_constraint_mode = None
    for model_alias, _ in MODEL_ORDER:
        service = summary[model_alias]["service"]
        if service.get("qwen_output_constraint_mode"):
            qwen_constraint_mode = service.get("qwen_output_constraint_mode")
            break
    lines.append(f"- Fixed qwen output constraint mode: `{qwen_constraint_mode or 'unknown'}`.")
    lines.append("- Constraint effect should be judged mainly from `CompileErr` and `NoInputs` columns, especially for qwen35-4b / qwen35-9b GTOR rows.")

    lines.extend(["", "## 7. ITERG / AgentG 附加统计", ""])
    for model_alias, _ in MODEL_ORDER:
        for method in ["ITERG", "AgentG"]:
            m = summary[model_alias]["methods"].get(method, {})
            if not m:
                continue
            lines.append(f"- {model_alias} {method}: latest={m.get('latest_tier', 'N/A')}, best={m.get('best_round_tier', 'N/A')}, best_hit_avg={m.get('best_hit_count_avg', 0.0)}, later_improved={m.get('whether_later_rounds_improved_count', 0)}, rounds_avg={m.get('rounds_completed_avg', 0.0)}, context_warn={m.get('context_too_long_warning_count', 0)}, tool_parse_fail={m.get('tool_call_parse_failure_count', 0)}, normalization={m.get('normalization_applied_count', 0)}")

    lines.extend(["", "## 8. Recap", ""])
    servable = [model for model, _ in MODEL_ORDER if all((summary[model]["service"].get("service_ok", False), summary[model]["service"].get("chat_ok", False)))]
    completed = [model for model, _ in MODEL_ORDER if summary[model]["service"].get("aca_run_ok", False)]
    if completed:
        best_method = max(METHODS, key=lambda method: sum(summary[m]["methods"].get(method, {}).get("avg_tier_score", 0.0) for m, _ in MODEL_ORDER))
        agent_change = "改善" if summary["qwen35-9b"]["methods"].get("AgentG", {}).get("avg_tier_score", 0.0) > summary["qwen35-4b"]["methods"].get("AgentG", {}).get("avg_tier_score", 0.0) else "未明显改善"
        can_go_next = "可以进入 100-task" if completed else "暂不建议进入 100-task / k=3 / training_records"
    else:
        best_method = "数据不足"
        agent_change = "数据不足"
        can_go_next = "暂不建议进入 100-task / k=3 / training_records"
    lines.append(f"- 哪个模型能服务：{', '.join(servable) if servable else '无'}。")
    lines.append(f"- 哪个模型跑完 probe20：{', '.join(completed) if completed else '无'}。")
    lines.append(f"- 四方法谁最稳：{best_method}。")
    lines.append(f"- AgentG 是否随模型变大改善：{agent_change}。")
    lines.append(f"- 是否可以进入 100-task / k=3 / training_records：{can_go_next}。")
    lines.append(f"- {next_step_line(summary)}")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
