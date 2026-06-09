#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _managed_pipeline import health_check


def main() -> None:
    parser = argparse.ArgumentParser(description="Strict vLLM health check for ACA_model managed runs.")
    parser.add_argument("--api-base", default=None)
    parser.add_argument("--api-key", default="local-vllm")
    parser.add_argument("--expected-model-id", required=True)
    parser.add_argument("--models-json", type=Path, default=None)
    parser.add_argument("--chat-json", type=Path, default=None)
    args = parser.parse_args()

    result = health_check(
        api_base=args.api_base or "http://127.0.0.1:0/v1",
        api_key=args.api_key,
        expected_model_id=args.expected_model_id,
        models_json_path=args.models_json,
        chat_json_path=args.chat_json,
    )
    print(f"SERVICE_OK={1 if result.service_ok else 0}")
    print(f"MODELS_OK={1 if result.models_ok else 0}")
    print(f"MODEL_ID_MATCH={1 if result.model_id_match else 0}")
    print(f"CHAT_OK={1 if result.chat_ok else 0}")
    print(f"CONTENT_LEN={result.content_len}")
    print("MODEL_IDS=" + json.dumps(result.model_ids, ensure_ascii=False))
    if result.model_id:
        print(f"SELECTED_MODEL_ID={result.model_id}")
    if result.content_preview:
        print(f"CONTENT_PREVIEW={result.content_preview}")
    if result.error:
        print(f"ERROR={result.error}")
    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
