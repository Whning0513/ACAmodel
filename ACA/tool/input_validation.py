"""Problem-specific input validator loader for ACA sandbox.

Supports multiple validator asset layouts observed in this workspace:

- ``ACA_data/validators/registry.json`` with a direct ``pid -> entry`` mapping
- ``validator_registry.json`` bundles with a top-level ``validators`` list
- entries that use either ``path`` or ``val_path``

Environment overrides:

- ``ACA_VALIDATOR_REGISTRY``: exact registry file to use
- ``ACA_VALIDATOR_ROOT``: root directory to search first for registry/files
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Optional


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_validator_root() -> Path:
    return _workspace_root() / "ACA_data" / "validators"


def get_validator_root() -> Optional[Path]:
    root = os.environ.get("ACA_VALIDATOR_ROOT")
    if root:
        return Path(root).expanduser().resolve()
    default_root = _default_validator_root()
    if default_root.exists():
        return default_root
    return None


def _iter_registry_candidates() -> Iterable[Path]:
    registry_env = os.environ.get("ACA_VALIDATOR_REGISTRY")
    if registry_env:
        yield Path(registry_env).expanduser().resolve()
        return

    root = get_validator_root()
    seen: set[Path] = set()

    def emit(path: Path) -> Iterable[Path]:
        resolved = path.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            yield resolved

    if root is not None:
        for name in ("registry.json", "validator_registry.json"):
            yield from emit(root / name)

    workspace = _workspace_root()
    direct = [
        workspace / "ACA_data" / "validators" / "registry.json",
        workspace / "ACA_data" / "validators" / "validator_registry.json",
    ]
    for path in direct:
        yield from emit(path)

    for base in (workspace / "ACA_data" / "outputs", workspace / "outputs"):
        if not base.exists():
            continue
        for name in ("validator_registry.json", "registry.json"):
            for path in sorted(base.rglob(name)):
                yield from emit(path)


def _iter_validator_dataset_candidates() -> Iterable[Path]:
    workspace = _workspace_root()
    for base in (workspace / "ACA_data" / "outputs", workspace / "outputs"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*_with_validators.ndjson")):
            yield path.resolve()


def get_registry_path() -> Optional[Path]:
    for path in _iter_registry_candidates():
        if path.exists():
            return path
    return None


def _normalize_status(raw_status: Any) -> str:
    text = str(raw_status or "").strip().lower()
    if text in {"reviewed", "validator_ready"}:
        return "reviewed"
    if text in {"draft", "llm_draft", "llm_draft_tested", "validator_pending"}:
        return "draft"
    if text in {"disabled", "missing"}:
        return text
    return "draft" if text else "missing"


def _entry_available(status: str) -> bool:
    return status in {"draft", "reviewed"}


def _build_validator_index() -> dict[str, list[Path]]:
    workspace = _workspace_root()
    index: dict[str, list[Path]] = {}
    for base in (workspace / "ACA_data", workspace / "outputs"):
        if not base.exists():
            continue
        for path in base.rglob("validators/*.py"):
            index.setdefault(path.name, []).append(path.resolve())
    return index


@lru_cache(maxsize=1)
def _validator_file_index() -> dict[str, list[Path]]:
    return _build_validator_index()


def _resolve_validator_path(path_value: Any, registry_path: Path) -> Optional[Path]:
    if not path_value:
        return None

    raw = str(path_value).strip()
    candidate = Path(raw).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()

    relative_candidates = [
        registry_path.parent / raw,
        registry_path.parent / "validators" / raw,
        registry_path.parent.parent / "validators" / raw,
    ]
    for rel in relative_candidates:
        if rel.exists():
            return rel.resolve()

    basename = Path(raw).name
    hits = _validator_file_index().get(basename, [])
    return hits[0] if len(hits) == 1 else None


def _normalize_registry_entry(pid: str, entry: dict[str, Any], registry_path: Path) -> dict[str, Any]:
    status = _normalize_status(entry.get("status"))
    resolved_path = _resolve_validator_path(entry.get("path") or entry.get("val_path"), registry_path)
    source = (
        entry.get("source")
        or entry.get("model")
        or (entry.get("generation_meta") or {}).get("model")
    )
    version = entry.get("version")

    return {
        "pid": pid,
        "available": _entry_available(status) and resolved_path is not None,
        "status": status if resolved_path is not None else "missing",
        "version": version,
        "path": str(resolved_path) if resolved_path is not None else None,
        "source": source,
        "registry_path": str(registry_path),
        "raw_status": entry.get("status"),
    }


def _normalize_dataset_validator_entry(
    pid: str,
    validator_info: dict[str, Any],
    dataset_path: Path,
) -> dict[str, Any]:
    status = _normalize_status(validator_info.get("status"))
    resolved_path = _resolve_validator_path(validator_info.get("path"), dataset_path)
    return {
        "pid": pid,
        "available": _entry_available(status) and resolved_path is not None,
        "status": status if resolved_path is not None else "missing",
        "version": validator_info.get("version"),
        "path": str(resolved_path) if resolved_path is not None else None,
        "source": validator_info.get("source"),
        "registry_path": str(dataset_path),
        "raw_status": validator_info.get("status"),
    }


def _iter_registry_entries(payload: dict[str, Any], registry_path: Path) -> Iterable[tuple[str, dict[str, Any]]]:
    validators = payload.get("validators")
    if isinstance(validators, list):
        for item in validators:
            if not isinstance(item, dict):
                continue
            pid = item.get("pid_key") or item.get("pid")
            if pid:
                yield str(pid), _normalize_registry_entry(str(pid), item, registry_path)
        return

    for pid, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        yield str(pid), _normalize_registry_entry(str(pid), entry, registry_path)


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}

    def score(entry: dict[str, Any]) -> tuple[int, int, int]:
        return (
            1 if entry.get("path") else 0,
            1 if entry.get("available") else 0,
            1 if entry.get("status") == "reviewed" else 0,
        )

    for registry_path in _iter_registry_candidates():
        if not registry_path.exists():
            continue
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        for pid, entry in _iter_registry_entries(payload, registry_path):
            current = registry.get(pid)
            if current is None or score(entry) > score(current):
                registry[pid] = entry

    for dataset_path in _iter_validator_dataset_candidates():
        try:
            with dataset_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        continue
                    pid = row.get("pid")
                    validator_info = row.get("validator_info")
                    if not pid or not isinstance(validator_info, dict):
                        continue
                    entry = _normalize_dataset_validator_entry(str(pid), validator_info, dataset_path)
                    current = registry.get(str(pid))
                    if current is None or score(entry) > score(current):
                        registry[str(pid)] = entry
        except Exception:
            continue

    return registry


@lru_cache(maxsize=None)
def _load_validator_module(module_path: str) -> ModuleType:
    path = Path(module_path)
    spec = importlib.util.spec_from_file_location(f"aca_validator_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load validator spec from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


def get_validator_info_for_pid(pid: Optional[str]) -> dict[str, Any]:
    """Return dataset-facing validator metadata for one pid."""
    if not pid:
        return {
            "available": False,
            "status": "missing",
            "version": None,
            "path": None,
            "source": None,
        }

    entry = _load_registry().get(pid)
    if not entry:
        return {
            "available": False,
            "status": "missing",
            "version": None,
            "path": None,
            "source": None,
            "registry_path": None,
        }
    return {
        "available": bool(entry.get("available")),
        "status": entry.get("status", "missing"),
        "version": entry.get("version"),
        "path": entry.get("path"),
        "source": entry.get("source"),
        "registry_path": entry.get("registry_path"),
    }


def validate_input_by_pid(pid: Optional[str], input_str: str) -> dict[str, Any]:
    """Validate one input against a pid-specific validator if available."""
    validator_info = get_validator_info_for_pid(pid)
    if not pid or validator_info["status"] == "missing":
        return {
            "ok": True,
            "reason": "no_validator",
            "category": "unknown",
            "has_validator": False,
            "validator_path": None,
        }

    registry = _load_registry()
    entry = registry.get(pid)
    if not entry:
        return {
            "ok": True,
            "reason": "no_validator",
            "category": "unknown",
            "has_validator": False,
            "validator_path": None,
        }

    status = entry.get("status", "missing")
    if status == "disabled":
        return {
            "ok": True,
            "reason": "validator_disabled",
            "category": "unknown",
            "has_validator": False,
            "validator_path": None,
        }

    validator_path_str = entry.get("path")
    if not validator_path_str:
        return {
            "ok": True,
            "reason": "no_validator",
            "category": "unknown",
            "has_validator": False,
            "validator_path": None,
        }

    validator_path = Path(validator_path_str).expanduser().resolve()
    if not validator_path.exists():
        return {
            "ok": True,
            "reason": "no_validator",
            "category": "unknown",
            "has_validator": False,
            "validator_path": None,
        }

    try:
        module = _load_validator_module(str(validator_path))
        validate_fn = getattr(module, "validate_input")
        ok, reason = validate_fn(input_str)
        return {
            "ok": bool(ok),
            "reason": str(reason),
            "category": "ok" if ok else "spec_invalid",
            "has_validator": True,
            "validator_path": str(validator_path),
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"validator_error: {exc}",
            "category": "validator_error",
            "has_validator": True,
            "validator_path": str(validator_path),
        }
