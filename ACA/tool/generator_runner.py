"""Run LLM-generated Python generator programs on a list of seeds.

TODO:
- This is not a strong sandbox. It uses a temp working directory, `shell=False`,
  timeout, and optional RLIMIT_AS memory limiting, but it does not fully prevent
  malicious filesystem or syscall behavior.
- Future hardening should block network access and restrict absolute-path writes.
"""

from __future__ import annotations

import resource
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class GeneratorCompileResult:
    status: str
    ok: bool
    error: Optional[str]
    code_bytes: int


@dataclass
class GeneratorRunResult:
    seed: int
    status: str
    input_text: Optional[str]
    stdout_preview: str
    stderr_preview: str
    runtime_sec: float
    error: Optional[str] = None


def _safe_preview(text: str, limit: int = 300) -> str:
    flat = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(flat) <= limit:
        return flat
    return flat[: max(0, limit - 3)] + "..."


def compile_generator_code(code: str, max_code_bytes: int) -> GeneratorCompileResult:
    normalized = textwrap.dedent(code).strip() + "\n"
    code_bytes = len(normalized.encode("utf-8"))
    if code_bytes > max_code_bytes:
        return GeneratorCompileResult(
            status="GENERATOR_CODE_TOO_LARGE",
            ok=False,
            error=f"generator code exceeded {max_code_bytes} bytes",
            code_bytes=code_bytes,
        )
    try:
        compile(normalized, "generator.py", "exec")
    except SyntaxError as exc:
        return GeneratorCompileResult(
            status="GENERATOR_SYNTAX_ERROR",
            ok=False,
            error=f"{exc.__class__.__name__}: {exc}",
            code_bytes=code_bytes,
        )
    except Exception as exc:
        return GeneratorCompileResult(
            status="GENERATOR_COMPILE_ERROR",
            ok=False,
            error=f"{exc.__class__.__name__}: {exc}",
            code_bytes=code_bytes,
        )
    return GeneratorCompileResult(
        status="GENERATOR_COMPILE_OK",
        ok=True,
        error=None,
        code_bytes=code_bytes,
    )


def _limit_memory(memory_mb: int):
    if memory_mb > 0:
        limit_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))


def _run_one_seed(
    code: str,
    seed: int,
    timeout: float,
    memory_mb: int,
    max_output_bytes: int,
) -> GeneratorRunResult:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="aca_generator_") as tmpdir:
        script_path = Path(tmpdir) / "generator.py"
        script_path.write_text(code, encoding="utf-8")
        stdout_path = Path(tmpdir) / "stdout.bin"
        stderr_path = Path(tmpdir) / "stderr.bin"

        try:
            with stdout_path.open("wb") as stdout_fh, stderr_path.open("wb") as stderr_fh:
                proc = subprocess.Popen(
                    [sys.executable, str(script_path), str(seed)],
                    cwd=tmpdir,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_fh,
                    stderr=stderr_fh,
                    text=False,
                    shell=False,
                    preexec_fn=(lambda: _limit_memory(memory_mb)),
                )

                oversized = False
                while True:
                    return_code = proc.poll()
                    runtime_sec = time.perf_counter() - started
                    if stdout_path.exists() and stdout_path.stat().st_size > max_output_bytes:
                        oversized = True
                        proc.kill()
                        proc.wait()
                        break
                    if return_code is not None:
                        break
                    if runtime_sec > timeout:
                        proc.kill()
                        proc.wait()
                        raise subprocess.TimeoutExpired(proc.args, timeout)
                    time.sleep(0.02)
        except subprocess.TimeoutExpired:
            stdout_b = stdout_path.read_bytes() if stdout_path.exists() else b""
            stderr_b = stderr_path.read_bytes() if stderr_path.exists() else b""
            runtime_sec = time.perf_counter() - started
            return GeneratorRunResult(
                seed=seed,
                status="GEN_TIMEOUT",
                input_text=None,
                stdout_preview=_safe_preview((stdout_b or b"").decode("utf-8", errors="replace")),
                stderr_preview=_safe_preview((stderr_b or b"").decode("utf-8", errors="replace")),
                runtime_sec=runtime_sec,
                error=f"generator timed out after {timeout:.2f}s",
            )
        except Exception as exc:
            runtime_sec = time.perf_counter() - started
            return GeneratorRunResult(
                seed=seed,
                status="GEN_RUNTIME_ERROR",
                input_text=None,
                stdout_preview="",
                stderr_preview=_safe_preview(str(exc)),
                runtime_sec=runtime_sec,
                error=str(exc),
            )

        stdout_b = stdout_path.read_bytes() if stdout_path.exists() else b""
        stderr_b = stderr_path.read_bytes() if stderr_path.exists() else b""
        stdout_text = (stdout_b or b"").decode("utf-8", errors="replace")
        stderr_text = (stderr_b or b"").decode("utf-8", errors="replace")

        if oversized or len(stdout_b or b"") > max_output_bytes:
            return GeneratorRunResult(
                seed=seed,
                status="GEN_TOO_LARGE",
                input_text=None,
                stdout_preview=_safe_preview(stdout_text),
                stderr_preview=_safe_preview(stderr_text),
                runtime_sec=runtime_sec,
                error=f"stdout exceeded {max_output_bytes} bytes",
            )

        if proc.returncode != 0:
            return GeneratorRunResult(
                seed=seed,
                status="GEN_RUNTIME_ERROR",
                input_text=None,
                stdout_preview=_safe_preview(stdout_text),
                stderr_preview=_safe_preview(stderr_text),
                runtime_sec=runtime_sec,
                error=f"generator exited with code {proc.returncode}",
            )

        if not stdout_text:
            return GeneratorRunResult(
                seed=seed,
                status="GEN_EMPTY_OUTPUT",
                input_text=None,
                stdout_preview="",
                stderr_preview=_safe_preview(stderr_text),
                runtime_sec=runtime_sec,
                error="generator produced empty stdout",
            )

        return GeneratorRunResult(
            seed=seed,
            status="GEN_OK",
            input_text=stdout_text,
            stdout_preview=_safe_preview(stdout_text),
            stderr_preview=_safe_preview(stderr_text),
            runtime_sec=runtime_sec,
            error=None,
        )


def run_generator_code(
    code: str,
    seeds: List[int],
    timeout: float,
    memory_mb: int,
    max_output_bytes: int,
) -> List[GeneratorRunResult]:
    """Run generator code once per seed and collect per-seed results."""
    normalized = textwrap.dedent(code).strip() + "\n"
    return [
        _run_one_seed(
            normalized,
            seed=seed,
            timeout=timeout,
            memory_mb=memory_mb,
            max_output_bytes=max_output_bytes,
        )
        for seed in seeds
    ]
