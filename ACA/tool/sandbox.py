#!/usr/bin/env python3
"""Single-run sandbox with coverage tracing.

Public API:
  - execute_code(code, stdin_input, timeout, memory_mb) -> ExecutionResult
  - trace_coverage(code, stdin_input, timeout, memory_mb) -> CoverageResult
  - trace_coverage_batch(code, test_inputs, timeout, memory_mb) -> List[CoverageResult]
  - get_candidate_lines(code) -> List[int]
  - compute_uncovered_lines(code, candidate_lines, covered_lines) -> List[int]
  - trace_coverage_dual(code, ref_code, test_inputs, timeout, memory_mb) -> List[DualRunResult]

Agent must use trace_coverage_dual() — reference is always executed fresh,
output compared inline. String matching against pre-stored outputs is forbidden.
outputs_match/normalize_output live in ACA_data/scripts/output_utils.py
for pipeline (step4/5/6) use only.

Coverage is line-level only (sys.settrace). else/elif/except/finally headers
receive no bytecode line events — we apply a line-level logical coverage
augmentation (行覆盖的逻辑补全) to repair header visibility in both directions.
This is NOT branch coverage: we track whether a header's body was entered, not
which branch edges were taken or how many times.
"""

import ast
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import List, Optional, Set

from ACA.tool.input_validation import validate_input_by_pid


# ── Data types ──────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """Pure execution result (no coverage tracing)."""
    stdout: str
    stderr: str
    exit_code: Optional[int]   # None = killed by timeout
    timed_out: bool
    status: str                # "OK" | "RE" | "TLE"


@dataclass
class CoverageResult(ExecutionResult):
    """Coverage-traced execution result."""
    covered_lines: List[int] = field(default_factory=list)


@dataclass
class DualRunResult:
    """Result of dual-run (reference + student) for a single test input.

    WA-focused: timeout confirmed by conditional pure run.
    """
    status: str                # "AC" | "WA" | "RE" | "TIMEOUT" | "TRACE_TIMEOUT" | "INVALID" | "SPEC_INVALID" | "UNKNOWN"
    breakthrough: bool         # True if student fails against a healthy reference
    stdout: str                # student stdout
    stderr: str                # student stderr
    covered_lines: List[int]   # student covered lines
    expected_output: str       # reference stdout (empty if ref failed)
    reference_ok: bool         # reference ran successfully
    error: str                 # execution error message if any
    ref_stdout: str = ""       # full reference stdout
    ref_stderr: str = ""       # full reference stderr
    ref_returncode: Optional[int] = None
    validator_ok: Optional[bool] = None
    validator_reason: str = ""
    has_validator: bool = False
    validator_path: str = ""
    pure_status: str = ""
    trace_status: str = ""
    coverage_available: bool = True


# ── Memory limit ────────────────────────────────────────────────────────

def _set_memory_limit(max_bytes: int):
    resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))


# ── Line-level logical coverage augmentation ────────────────────────────
# sys.settrace never fires line events for else/elif/except/finally
# headers (no bytecode). The two functions below repair header visibility
# via indentation-based body scanning. This is a line-level heuristic, NOT
# branch coverage — there is no CFG, no true/false edge counter, and no
# branch-taken frequency. Call it "行覆盖的逻辑补全".

def _propagate_label_coverage(code: str, covered: set) -> set:
    """Line-level repair: if any body line under a label header is covered, mark the header.

    sys.settrace never fires line events for else/elif/try/except/finally
    headers, so covered body lines must propagate upward to the header.
    This is purely line-level — it does not count branch edges.
    """
    lines = code.split("\n")
    result = set(covered)

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_label = (
            re.match(r'else\s*:', stripped) is not None or
            re.match(r'elif\b', stripped) is not None or
            re.match(r'try\s*:', stripped) is not None or
            stripped.startswith("except") or
            re.match(r'finally\s*:', stripped) is not None
        )
        if not is_label:
            continue
        label_ln = i + 1

        label_indent = len(line) - len(line.lstrip())
        for j in range(i + 1, len(lines)):
            body = lines[j]
            if not body.strip() or body.strip().startswith("#"):
                continue
            body_indent = len(body) - len(body.lstrip())
            if body_indent <= label_indent:
                break
            if (j + 1) in covered:
                result.add(label_ln)
                break

    return result


def _augment_uncovered_else_blocks(code: str, uncovered: set) -> set:
    """Line-level repair: if ALL body lines under a label header are uncovered, add header.

    sys.settrace never fires line events for else/elif/except/finally header
    lines, so we augment from the uncovered direction to catch these.
    This is purely line-level — it does not count branch edges.
    """
    lines = code.split("\n")
    result = set(uncovered)

    for i, line in enumerate(lines):
        stripped = line.strip()
        is_label = (
            re.match(r'else\s*:', stripped) is not None or
            re.match(r'elif\b', stripped) is not None or
            re.match(r'try\s*:', stripped) is not None or
            stripped.startswith("except") or
            re.match(r'finally\s*:', stripped) is not None
        )
        if not is_label:
            continue
        label_ln = i + 1
        if label_ln in result:
            continue

        label_indent = len(line) - len(line.lstrip())
        body_lines = []
        for j in range(i + 1, len(lines)):
            body = lines[j]
            if not body.strip() or body.strip().startswith("#"):
                continue
            body_indent = len(body) - len(body.lstrip())
            if body_indent <= label_indent:
                break
            body_lines.append(j + 1)

        if not body_lines:
            continue
        if all(bl in uncovered for bl in body_lines):
            result.add(label_ln)

    return result


# ── Subprocess wrappers ─────────────────────────────────────────────────

def _run_in_subprocess(code: str, stdin_input: str, timeout: float,
                       memory_mb: int, with_trace: bool,
                       code_path: str = None, sandbox_dir: str = None,
                       cpu_time_limit: float = None,
                       memory_limit_mb: int = 0) -> dict:
    """Execute code in a subprocess, returning raw result dict.

    Args:
        code_path: If provided, reuse existing code file.
        sandbox_dir: If provided, reuse existing sandbox (updates stdin files only).
        cpu_time_limit: If set, apply RLIMIT_CPU to the subprocess (seconds).
        memory_limit_mb: If set, strict judging memory limit for MLE detection.
    """
    safe_input = (stdin_input or "").rstrip() + "\n"

    own_code = code_path is None
    own_sandbox = sandbox_dir is None

    if own_code:
        code_fd, code_path = tempfile.mkstemp(suffix=".py")
        os.write(code_fd, code.encode())
        os.close(code_fd)

    if own_sandbox:
        sandbox_dir = tempfile.mkdtemp(prefix="aca_sandbox_")

    # Students read stdin from different filenames — write to all common aliases
    for alias in ["__stdin__.txt", "q1.input", "input.txt", "data.in", "stdin.txt"]:
        with open(os.path.join(sandbox_dir, alias), "w") as f:
            f.write(safe_input)

    output_fd, output_path = tempfile.mkstemp(suffix=".json")
    os.close(output_fd)

    if with_trace:
        wrapper_code = _make_trace_wrapper(code_path, sandbox_dir, output_path, memory_mb,
                                           memory_limit_mb=memory_limit_mb)
    else:
        wrapper_code = _make_exec_wrapper(code_path, sandbox_dir, memory_mb, cpu_time=cpu_time_limit,
                                          memory_limit_mb=memory_limit_mb)

    wrapper_fd, wrapper_path = tempfile.mkstemp(suffix=".py")
    os.write(wrapper_fd, wrapper_code.encode())
    os.close(wrapper_fd)

    try:
        proc = subprocess.Popen(
            [sys.executable, wrapper_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True,
        )
        t0 = time.perf_counter()
        try:
            stdout, stderr = proc.communicate(input=safe_input, timeout=timeout)
            exit_code = proc.returncode
            elapsed = time.perf_counter() - t0
            # Detect CPU time kill: RLIMIT_CPU triggers SIGXCPU (soft) then
            # SIGKILL (hard). With SIG_DFL, the process dies on SIGXCPU.
            if cpu_time_limit is not None and exit_code is not None and exit_code < 0:
                sigxcpu = getattr(signal, 'SIGXCPU', 24)
                sigkill = getattr(signal, 'SIGKILL', 9)
                timed_out = (exit_code in (-sigxcpu, -sigkill))
            else:
                timed_out = False
            # Detect memory limit kill: RLIMIT_AS triggers SIGKILL/SIGSEGV
            memory_killed = False
            if memory_limit_mb and exit_code is not None and exit_code < 0:
                sigkill = getattr(signal, 'SIGKILL', 9)
                sigsegv = getattr(signal, 'SIGSEGV', 11)
                memory_killed = (exit_code in (-sigkill, -sigsegv))
        except subprocess.TimeoutExpired:
            proc.terminate()  # SIGTERM — trace wrapper dumps coverage before exit
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()   # SIGKILL — last resort for stubborn processes
                proc.wait()
            elapsed = time.perf_counter() - t0
            stdout, stderr = "", "(timed out)"
            exit_code = None
            timed_out = True
            memory_killed = False
    except Exception as e:
        stdout, stderr = "", str(e)
        exit_code = -1
        timed_out = False
        memory_killed = False

    covered_lines = []
    if with_trace:
        try:
            with open(output_path) as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                covered_lines = raw.get("covered_lines", [])
        except (json.JSONDecodeError, OSError):
            pass

    # Cleanup
    if own_code:
        try: os.unlink(code_path)
        except OSError: pass
    try: os.unlink(wrapper_path)
    except OSError: pass
    try: os.unlink(output_path)
    except OSError: pass
    if own_sandbox:
        shutil.rmtree(sandbox_dir, ignore_errors=True)

    return {
        "stdout": stdout or "",
        "stderr": stderr or "",
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed": elapsed,
        "covered_lines": covered_lines,
        "memory_killed": memory_killed,
    }


def _make_trace_wrapper(code_path: str, sandbox_dir: str, output_path: str,
                        memory_mb: int = 0, memory_limit_mb: int = 0) -> str:
    """Generate a self-contained Python script that runs target code with sys.settrace.

    The generated script:
      1. chdir to sandbox (where stdin files live)
      2. Set memory limit via RLIMIT_AS
      3. Install a sys.settrace hook that records every line hit in target file
      4. exec() the target code with __name__='__main__' so if __name__ blocks fire
      5. Write covered_lines JSON to output_path on exit
    """
    mem_line = ""
    if memory_limit_mb:
        mem_line = f"import resource; resource.setrlimit(resource.RLIMIT_AS,({memory_limit_mb}*1024*1024,)*2)\n"
    elif memory_mb:
        mem_line = f"import resource; resource.setrlimit(resource.RLIMIT_AS,({memory_mb}*1024*1024,)*2)\n"
    return (
        "import sys, json, os, atexit, signal as _signal\n"
        f"os.chdir({sandbox_dir!r})\n"
        f"{mem_line}"
        f"sp = os.path.join({sandbox_dir!r}, '__stdin__.txt')\n"
        "if os.path.exists(sp):\n"
        "    sys.stdin = open(sp, 'r')\n"
        "sys.setrecursionlimit(300000)\n"
        "covered = set()\n"
        # sys.settrace callback: record every 'line' event in the target file only
        "def t(f,e,a):\n"
        f"    if e=='line' and os.path.abspath(f.f_code.co_filename)==os.path.abspath({code_path!r}):\n"
        "        covered.add(f.f_lineno)\n"
        "    return t\n"
        "sys.settrace(t)\n"
        # Ensure coverage data survives timed-out kill (SIGTERM + atexit)
        f"def _aca_flush():\n"
        f"    try: json.dump({{'covered_lines':sorted(covered)}},open({output_path!r},'w'))\n"
        f"    except: pass\n"
        "atexit.register(_aca_flush)\n"
        "_signal.signal(_signal.SIGTERM, lambda *a: (_aca_flush(), sys.exit(0)))\n"
        "ec=0\n"
        "try:\n"
        # exec with custom globals so the target code sees __name__='__main__'
        f"    exec(compile(open({code_path!r}).read(),{code_path!r},'exec'),"
        '{"__name__":"__main__","__file__":' f'{code_path!r}' "})\n"
        "except SystemExit as e:\n"
        "    ec=e.code if isinstance(e.code,int) else 0\n"
        "except BaseException:\n"
        "    import traceback; traceback.print_exc()\n"
        "    ec=1\n"
        "sys.settrace(None)\n"
        "_aca_flush()\n"
        "sys.exit(ec)\n"
    )


def _make_exec_wrapper(code_path: str, sandbox_dir: str,
                       memory_mb: int = 0, cpu_time: float = None,
                       memory_limit_mb: int = 0) -> str:
    limits = ""
    if memory_limit_mb:
        # Strict judging memory limit — used for MLE confirmation (step 3)
        limits += f"import resource; resource.setrlimit(resource.RLIMIT_AS,({memory_limit_mb}*1024*1024,)*2)\n"
    elif memory_mb:
        limits += f"import resource; resource.setrlimit(resource.RLIMIT_AS,({memory_mb}*1024*1024,)*2)\n"
    if cpu_time:
        # RLIMIT_CPU requires integer seconds. ceil() to ensure at least 1s.
        # Soft < hard so SIGXCPU fires first, then SIGKILL if unhandled.
        cpu_int = max(1, int(cpu_time + 0.999))
        limits += "import signal; signal.signal(signal.SIGXCPU, signal.SIG_DFL)\n"
        limits += f"import resource; resource.setrlimit(resource.RLIMIT_CPU,({cpu_int},{cpu_int}*2))\n"
    return (
        "import sys, os\n"
        f"os.chdir({sandbox_dir!r})\n"
        f"{limits}"
        f"sp = os.path.join({sandbox_dir!r}, '__stdin__.txt')\n"
        "if os.path.exists(sp):\n"
        "    sys.stdin = open(sp, 'r')\n"
        "sys.setrecursionlimit(300000)\n"
        "ec=0\n"
        "try:\n"
        f"    exec(compile(open({code_path!r}).read(),{code_path!r},'exec'),"
        '{"__name__":"__main__","__file__":' f'{code_path!r}' "})\n"
        "except SystemExit as e:\n"
        "    ec=e.code if isinstance(e.code,int) else 0\n"
        "except BaseException:\n"
        "    import traceback; traceback.print_exc()\n"
        "    ec=1\n"
        "sys.exit(ec)\n"
    )


# ── Internal output comparison (dual-run only) ──────────────────────────
# Token-based comparison matches Codeforces/AtCoder behavior:
# whitespace (spaces, tabs, newlines) is treated as token delimiter, so
# "0\n0\n0" and "0 0 0" are equivalent after normalization.

def _normalize_token(t: str) -> str:
    try:
        if "." not in t and "e" not in t.lower():
            return str(int(t))
    except ValueError:
        pass
    try:
        v = float(t)
        if v == int(v):
            return str(int(v))
        return repr(v)
    except (ValueError, OverflowError):
        return t


def _tokenize(s: str) -> list:
    """Split by all whitespace, normalize each token. Empty output → []."""
    return [_normalize_token(t) for t in s.split()]


def _outputs_equal(ref_output: str, stu_output: str) -> bool:
    """Token-based dual-run comparison — whitespace = delimiter, like CF/AtCoder.
    Reference output is ALWAYS freshly computed by trace_coverage_dual."""
    return _tokenize(ref_output) == _tokenize(stu_output)


# ── Public API ──────────────────────────────────────────────────────────

def execute_code(
    code: str,
    stdin_input: str = "",
    timeout: float = 10.0,
    memory_mb: int = 256,
) -> ExecutionResult:
    """Execute code without coverage tracing."""
    r = _run_in_subprocess(code, stdin_input, timeout, memory_mb, with_trace=False)
    status = "OK"
    if r["timed_out"]:
        status = "TLE"
    elif r["exit_code"] is not None and r["exit_code"] != 0:
        status = "RE"
    return ExecutionResult(
        stdout=r["stdout"], stderr=r["stderr"],
        exit_code=r["exit_code"], timed_out=r["timed_out"], status=status,
    )


def trace_coverage(
    code: str,
    stdin_input: str = "",
    timeout: float = 10.0,
    memory_mb: int = 256,
) -> CoverageResult:
    """Execute code with coverage tracing. covered_lines includes else/except propagation."""
    r = _run_in_subprocess(code, stdin_input, timeout, memory_mb, with_trace=True)
    status = "OK"
    if r["timed_out"]:
        status = "TLE"
    elif r["exit_code"] is not None and r["exit_code"] != 0:
        status = "RE"
    covered = _propagate_label_coverage(code, set(r["covered_lines"]))
    return CoverageResult(
        stdout=r["stdout"], stderr=r["stderr"],
        exit_code=r["exit_code"], timed_out=r["timed_out"], status=status,
        covered_lines=sorted(covered),
    )


def trace_coverage_batch(
    code: str,
    test_inputs: List[str],
    timeout: float = 10.0,
    memory_mb: int = 256,
) -> List[CoverageResult]:
    """Batch coverage tracing: code file and sandbox created once, reused across cases.

    Reduces ~60% temp file I/O compared to repeated trace_coverage() calls.
    """
    code_fd, code_path = tempfile.mkstemp(suffix=".py")
    os.write(code_fd, code.encode())
    os.close(code_fd)

    sandbox_dir = tempfile.mkdtemp(prefix="aca_sandbox_")

    results = []
    try:
        for stdin_input in test_inputs:
            r = _run_in_subprocess(
                code, stdin_input, timeout, memory_mb,
                with_trace=True,
                code_path=code_path, sandbox_dir=sandbox_dir,
            )
            status = "OK"
            if r["timed_out"]:
                status = "TLE"
            elif r["exit_code"] is not None and r["exit_code"] != 0:
                status = "RE"
            covered = _propagate_label_coverage(code, set(r["covered_lines"]))
            results.append(CoverageResult(
                stdout=r["stdout"], stderr=r["stderr"],
                exit_code=r["exit_code"], timed_out=r["timed_out"], status=status,
                covered_lines=sorted(covered),
            ))
    finally:
        try: os.unlink(code_path)
        except OSError: pass
        shutil.rmtree(sandbox_dir, ignore_errors=True)

    return results


def trace_coverage_dual(
    code: str,
    ref_code: str,
    test_inputs: List[str],
    timeout: float = 10.0,
    memory_mb: int = 256,
    pid: str = None,
) -> List[DualRunResult]:
    """Dual-run: ref + student trace, with pure-run fallback for verdicts.

    2-step per test_input:
      1. Run reference code WITHOUT trace → get expected_output
      2. Run student code WITH trace → get coverage + actual output
      3. If trace times out, run student code WITHOUT trace and use that pure run
         to decide AC/WA/RE/TIMEOUT. Coverage becomes unavailable for that input.

    Args:
        pid: Problem ID (e.g. "cf_691_D"), used for validator lookup.
    """
    # cpu_time_limit resolution order:
    #   1. Explicit caller-supplied value (takes precedence, set below)
    #   2. Parquet time limit × python_multiplier (platform's actual C++ limit)
    #   3. Reference execution time × 2 (fallback, works for ALL problems)
    # Resolved after step 1 runs so we have ref_elapsed.

    # Pre-compile both code files once
    code_fd, code_path = tempfile.mkstemp(suffix=".py")
    os.write(code_fd, code.encode())
    os.close(code_fd)

    ref_fd, ref_path = tempfile.mkstemp(suffix=".py")
    os.write(ref_fd, ref_code.encode())
    os.close(ref_fd)

    sandbox_dir = tempfile.mkdtemp(prefix="aca_dual_")
    results: List[DualRunResult] = []

    try:
        for stdin_input in test_inputs:
            safe_input = (stdin_input or "").rstrip() + "\n"

            validator_result = validate_input_by_pid(pid, stdin_input)
            if not validator_result["ok"]:
                results.append(DualRunResult(
                    status="SPEC_INVALID",
                    breakthrough=False,
                    stdout="",
                    stderr="",
                    covered_lines=[],
                    expected_output="",
                    reference_ok=False,
                    error=f"SPEC_INVALID: {validator_result['reason']}",
                    validator_ok=False,
                    validator_reason=validator_result["reason"],
                    has_validator=validator_result["has_validator"],
                    validator_path=validator_result["validator_path"] or "",
                ))
                continue

            # Update stdin files in sandbox
            for alias in ["__stdin__.txt", "q1.input", "input.txt", "data.in", "stdin.txt"]:
                with open(os.path.join(sandbox_dir, alias), "w") as f:
                    f.write(safe_input)

            # ── Step 1: Run reference (no trace) ──────────────────────────
            ref_result = _run_in_subprocess(
                ref_code, stdin_input, timeout, memory_mb, with_trace=False,
                code_path=ref_path, sandbox_dir=sandbox_dir,
            )
            ref_elapsed = ref_result["elapsed"]
            reference_ok = (
                ref_result["exit_code"] is not None
                and ref_result["exit_code"] == 0
                and not ref_result["timed_out"]
                and bool(ref_result["stdout"].strip())
            )
            expected_output = ref_result["stdout"] if reference_ok else ""

            # ── Step 2: Run student code (with trace) ─────────────────────
            stu_result = _run_in_subprocess(
                code, stdin_input, timeout, memory_mb, with_trace=True,
                code_path=code_path, sandbox_dir=sandbox_dir,
            )

            # Coverage
            covered_raw = stu_result["covered_lines"]
            covered = sorted(_propagate_label_coverage(code, set(covered_raw)))

            stu_timed_out = stu_result["timed_out"]

            pure_result = None
            if stu_timed_out and reference_ok:
                pure_result = _run_in_subprocess(
                    code, stdin_input, timeout, memory_mb, with_trace=False,
                    code_path=code_path, sandbox_dir=sandbox_dir,
                )

            # ── Compute verdict from the pure run if trace timed out ─────
            coverage_available = not stu_timed_out
            if stu_timed_out and pure_result is not None:
                verdict_result = pure_result
                covered = []
                trace_status = "TRACE_TIMEOUT"
            else:
                verdict_result = stu_result
                trace_status = "OK"

            stu_return_code = verdict_result["exit_code"]
            stu_stdout = verdict_result["stdout"] or ""
            stu_stderr = verdict_result["stderr"] or ""
            status, breakthrough = _compute_dual_verdict(
                reference_ok, expected_output,
                verdict_result["timed_out"], stu_return_code, stu_stdout,
            )

            results.append(DualRunResult(
                status=status,
                breakthrough=breakthrough,
                stdout=stu_stdout,
                stderr=stu_stderr,
                covered_lines=covered,
                expected_output=expected_output,
                reference_ok=reference_ok,
                error=stu_stderr[:200] if status == "RE" else "",
                ref_stdout=ref_result.get("stdout", ""),
                ref_stderr=ref_result.get("stderr", ""),
                ref_returncode=ref_result.get("exit_code"),
                validator_ok=True,
                validator_reason=validator_result["reason"],
                has_validator=validator_result["has_validator"],
                validator_path=validator_result["validator_path"] or "",
                pure_status=status if pure_result is not None else "",
                trace_status=trace_status,
                coverage_available=coverage_available,
            ))

    finally:
        try: os.unlink(code_path)
        except OSError: pass
        try: os.unlink(ref_path)
        except OSError: pass
        shutil.rmtree(sandbox_dir, ignore_errors=True)

    return results


def _compute_dual_verdict(
    reference_ok: bool,
    expected_output: str,
    stu_timed_out: bool,
    stu_return_code,
    stu_stdout: str,
) -> tuple:
    """Compute (status, breakthrough) for one concrete student execution."""
    if not reference_ok:
        return ("INVALID", False)

    if stu_timed_out:
        return ("TIMEOUT", False)

    ref_clean = (expected_output or "").strip()
    stu_clean = (stu_stdout or "").strip()

    if not ref_clean and not stu_clean:
        return ("UNKNOWN", False)

    if not ref_clean:
        return ("UNKNOWN", False)

    if stu_return_code is not None and stu_return_code != 0:
        return ("RE", True)

    if _outputs_equal(expected_output, stu_stdout):
        return ("AC", False)
    else:
        return ("WA", True)


def get_candidate_lines(code: str) -> List[int]:
    """Return sorted executable line numbers via AST scanning.

    Excludes: blank lines, comments, imports, def/class headers, decorators.
    These are NOT executable — they can never appear in coverage.line traces.
    """
    import tokenize, io

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    # Collect all AST statement line numbers (executable or quasi-executable)
    stmt_lines = set()
    for node in ast.walk(tree):
        if hasattr(node, "lineno"):
            stmt_lines.add(node.lineno)

    exclude = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            exclude.add(node.lineno)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            exclude.add(node.lineno)
        for deco in getattr(node, "decorator_list", []):
            if hasattr(deco, "lineno"):
                exclude.add(deco.lineno)

    candidate = sorted(stmt_lines - exclude)

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
        # Only exclude pure comment lines (e.g. "# this is a comment"),
        # NOT lines with trailing comments (e.g. "x = 1  # init").
        non_code_types = {
            tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
            tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT,
            tokenize.ENCODING,
        }
        lines_with_code = {tok.start[0] for tok in tokens if tok.type not in non_code_types}
        pure_comment_lines = {
            tok.start[0] for tok in tokens
            if tok.type == tokenize.COMMENT and tok.start[0] not in lines_with_code
        }
        candidate = [ln for ln in candidate if ln not in pure_comment_lines]
    except Exception:
        pass

    return candidate


def compute_uncovered_lines(code: str, candidate_lines: List[int],
                            covered_lines: List[int]) -> List[int]:
    """candidate_lines - covered_lines, with line-level header augmentation.

    If all executable body lines under an else/elif/except/finally are uncovered,
    the header line is added to the uncovered set (line-level logical repair,
    not branch coverage).
    """
    uncovered = set(candidate_lines) - set(covered_lines)
    uncovered = _augment_uncovered_else_blocks(code, uncovered)
    return sorted(uncovered)


# ── Problem time limits (from raw parquet) ──────────────────────────────────

# Hardcoded fallback for problems missing from parquet (manually verified).
# Values are C++ / platform-native CPU time in seconds.
# Keys may be prefixes matching actual pid format (e.g. "p02257" matches "p02257 Prime Numbers").
_HARDCODED_TIME_LIMITS: dict = {
    "cf_630_A": 0.5,
    "cf_99_B": 2.0,
    "p02257": 1.0,
    "p00100": 1.0,
    "p02398": 1.0,
}


def get_cpu_time_limit(pid: str, time_limits: dict,
                       python_multiplier: float = 3.0) -> float:
    """Get CPU time limit for a problem, with Python multiplier.

    Codeforces time limits are for C++. Python is typically 2x, but with
    tracing overhead we use 3x by default. Callers (agents) that use tracing
    should pass this as cpu_time_limit to trace_coverage_dual().
    """
    tl = time_limits.get(pid)
    if tl is None:
        return 0.0  # signal: no limit available
    return tl * python_multiplier
