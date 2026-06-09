from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dual_launcher_defaults_to_16384_context_for_both_models() -> None:
    text = (ROOT / "scripts" / "run_gtor4_probe20_dual_progress.sh").read_text(encoding="utf-8")

    assert 'LLM_MAX_TOKENS_7B="${LLM_MAX_TOKENS_7B:-2048}"' in text
    assert 'LLM_MAX_TOKENS_9B="${LLM_MAX_TOKENS_9B:-2048}"' in text
    assert 'MAX_MODEL_LEN_7B="${MAX_MODEL_LEN_7B:-8192}"' in text
    assert 'MAX_MODEL_LEN_9B="${MAX_MODEL_LEN_9B:-8192}"' in text


def test_single_model_launcher_defaults_to_4096_output_and_16384_context() -> None:
    text = (ROOT / "scripts" / "run_gtor4_probe20_model.sh").read_text(encoding="utf-8")

    assert 'LLM_MAX_TOKENS="${LLM_MAX_TOKENS:-2048}"' in text
    assert 'DEFAULT_MAX_MODEL_LEN=8192' in text
    assert 'DEFAULT_MAX_MODEL_LEN=8192' in text
    assert '--llm-max-tokens "$LLM_MAX_TOKENS"' in text
