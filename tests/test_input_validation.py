from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

# Import the helper without loading ACA.tool's Linux-only sandbox dependencies.
MODULE_PATH = Path(__file__).resolve().parents[1] / "ACA" / "tool" / "input_validation.py"
SPEC = spec_from_file_location("aca_input_validation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
input_validation = module_from_spec(SPEC)
SPEC.loader.exec_module(input_validation)


def test_validator_lookup_uses_unique_basename_fallback(tmp_path: Path, monkeypatch) -> None:
    registry_path = tmp_path / "metadata" / "registry.json"
    validator_path = tmp_path / "dataset" / "validators" / "same.py"
    validator_path.parent.mkdir(parents=True)
    validator_path.write_text("def validate(value): return True\n", encoding="utf-8")
    monkeypatch.setattr(
        input_validation,
        "_validator_file_index",
        lambda: {"same.py": [validator_path]},
    )

    resolved = input_validation._resolve_validator_path("same.py", registry_path)

    assert resolved == validator_path


def test_validator_lookup_does_not_guess_between_duplicate_basenames(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "metadata" / "registry.json"
    validators = [
        tmp_path / "dataset-a" / "validators" / "same.py",
        tmp_path / "dataset-b" / "validators" / "same.py",
    ]
    for validator in validators:
        validator.parent.mkdir(parents=True)
        validator.write_text("def validate(value): return True\n", encoding="utf-8")
    monkeypatch.setattr(
        input_validation,
        "_validator_file_index",
        lambda: {"same.py": validators},
    )

    resolved = input_validation._resolve_validator_path("same.py", registry_path)

    assert resolved is None
