#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ACA_ROOT = Path("/data/whn/ACA")
if str(ACA_ROOT) not in sys.path:
    sys.path.insert(0, str(ACA_ROOT))

from agent.shared.generator_utils import extract_generator_code  # noqa: E402


CODE_PROMPTS = [
    "Write only Python code for a generator.py program. It must read one integer seed from stdin and print one integer n in [1, 100]. No markdown, no explanation.",
    "Return only valid Python code. The program reads a seed integer and prints two integers a b, each in [0, 10^6]. No prose.",
    "Produce only Python 3 code for generator.py. Read seed from stdin, use random.seed(seed), print a lowercase string of length 8. No comments or explanation.",
    "Output only Python code. The script reads one integer seed and prints first n then n integers, where 1 <= n <= 20. No markdown fences.",
    "Generate only executable Python code for generator.py. Read seed from stdin and print a simple undirected graph: n m then m edges. No explanation.",
]

SHORT_PROMPTS = [
    "Reply with exactly OK.",
    "Answer in one short sentence: what does Python's len do?",
    "Give one word only: the capital of France.",
    "Answer with one short line: 13 + 29 = ?",
    "Reply with exactly one lowercase word describing the color of the sky on a clear day.",
]


@dataclass
class ProbeResult:
    idx: int
    kind: str
    prompt: str
    ok: bool
    error: str | None
    content: str
    finish_reason: str | None
    content_length: int
    empty_response: bool
    has_thinking_block: bool
    has_python_code: bool
    extract_status: str
    extract_ok: bool


def post_chat(api_base: str, model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer local-vllm",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def looks_like_python(text: str) -> bool:
    markers = ("import ", "from ", "def ", "print(", "random.", "sys.stdin", "input(", "for ", "while ")
    return "```python" in text.lower() or any(m in text for m in markers)


def has_thinking_block(text: str) -> bool:
    lowered = text.lower()
    return "thinking process" in lowered or "<think>" in lowered or "</think>" in lowered


def run_probe(api_base: str, model: str) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    prompts = [("code", p, 256) for p in CODE_PROMPTS] + [("short", p, 64) for p in SHORT_PROMPTS]
    for idx, (kind, prompt, max_tokens) in enumerate(prompts, start=1):
        try:
            raw = post_chat(api_base, model, prompt, max_tokens)
            choice = raw["choices"][0]
            content = choice["message"].get("content") or ""
            finish_reason = choice.get("finish_reason")
            extract_status, extracted = extract_generator_code(content)
            results.append(
                ProbeResult(
                    idx=idx,
                    kind=kind,
                    prompt=prompt,
                    ok=True,
                    error=None,
                    content=content,
                    finish_reason=finish_reason,
                    content_length=len(content),
                    empty_response=(content.strip() == ""),
                    has_thinking_block=has_thinking_block(content),
                    has_python_code=looks_like_python(content),
                    extract_status=extract_status,
                    extract_ok=extracted is not None,
                )
            )
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            results.append(
                ProbeResult(
                    idx=idx,
                    kind=kind,
                    prompt=prompt,
                    ok=False,
                    error=f"HTTP {e.code}: {body}",
                    content="",
                    finish_reason=None,
                    content_length=0,
                    empty_response=True,
                    has_thinking_block=False,
                    has_python_code=False,
                    extract_status="request_error",
                    extract_ok=False,
                )
            )
        except Exception as e:  # noqa: BLE001
            results.append(
                ProbeResult(
                    idx=idx,
                    kind=kind,
                    prompt=prompt,
                    ok=False,
                    error=repr(e),
                    content="",
                    finish_reason=None,
                    content_length=0,
                    empty_response=True,
                    has_thinking_block=False,
                    has_python_code=False,
                    extract_status="request_error",
                    extract_ok=False,
                )
            )
    return results


def render_report(results: list[ProbeResult], output_path: Path, api_base: str, model: str) -> None:
    code_results = [r for r in results if r.kind == "code"]
    non_empty = sum(not r.empty_response for r in results)
    extractable_code = sum(r.extract_ok for r in code_results)
    empty_count = sum(r.empty_response for r in results)
    thinking_count = sum(r.has_thinking_block for r in results)
    lines = [
        "# qwen35-4b direct prompt probe",
        "",
        f"- API base: `{api_base}`",
        f"- Model: `{model}`",
        f"- Total prompts: `{len(results)}`",
        f"- Non-empty responses: `{non_empty}/{len(results)}`",
        f"- Empty responses: `{empty_count}`",
        f"- Thinking/reasoning block count: `{thinking_count}`",
        f"- Code prompts with extractable Python: `{extractable_code}/{len(code_results)}`",
        "",
        "## Per-prompt table",
        "",
        "| # | Kind | Empty | Thinking | Len | Python | Extractable | Finish |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.idx} | {r.kind} | {int(r.empty_response)} | {int(r.has_thinking_block)} | "
            f"{r.content_length} | {int(r.has_python_code)} | {int(r.extract_ok)} | {r.finish_reason or ''} |"
        )

    lines += ["", "## Details", ""]
    for r in results:
        lines += [
            f"### Prompt {r.idx} ({r.kind})",
            "",
            f"- Prompt: `{r.prompt}`",
            f"- Request OK: `{r.ok}`",
            f"- Error: `{r.error or ''}`",
            f"- Empty: `{r.empty_response}`",
            f"- Thinking block: `{r.has_thinking_block}`",
            f"- Content length: `{r.content_length}`",
            f"- Python-looking: `{r.has_python_code}`",
            f"- Extract status: `{r.extract_status}`",
            f"- Extractable: `{r.extract_ok}`",
            f"- Finish reason: `{r.finish_reason or ''}`",
            "",
            "```text",
            r.content[:4000],
            "```",
            "",
        ]

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8024/v1")
    parser.add_argument("--model", default="qwen35-4b")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    results = run_probe(args.api_base, args.model)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_report(results, output_path, args.api_base, args.model)


if __name__ == "__main__":
    main()
