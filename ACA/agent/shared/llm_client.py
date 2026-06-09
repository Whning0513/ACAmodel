"""LLM client with connection pooling, retry, and optional logging.

Usage:
    from ACA.agent.shared.llm_client import LLMClient

    client = LLMClient(model="deepseek-v4-pro", api_key="...", api_base="...")
    response = client.call(messages, tools)
"""

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import httpx
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)


@dataclass
class LLMConfig:
    """Minimal LLM configuration — no dependency on old ACAExperimentConfig."""
    model: str = "gpt-4o-mini-ca"
    api_base: str = ""
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 16383
    seed: Optional[int] = None
    llm_timeout: int = 320            # max total time for the full retry loop
    verbose: bool = False
    env_source: Optional[Dict[str, str]] = None


class LLMClient:
    """OpenAI-compatible LLM client with connection pooling and retry."""

    _startup_log_keys = set()

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client: Optional[OpenAI] = None
        self._log = None                # optional logger callback
        self._emit_startup_diagnostics()

    def _emit_startup_diagnostics(self) -> None:
        if not self.config.verbose:
            return
        base = self.config.api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        actual_api_base = base or "https://api.deepseek.com/v1"
        key_prefix = (self.config.api_key or "")[:6]
        env_source = self.config.env_source or {}
        log_key = (
            self.config.model,
            actual_api_base,
            key_prefix,
            json.dumps(env_source, sort_keys=True, ensure_ascii=False),
        )
        if log_key in self._startup_log_keys:
            return
        self._startup_log_keys.add(log_key)
        payload = {
            "model": self.config.model,
            "api_base": actual_api_base,
            "key_prefix": key_prefix,
            "env_source": env_source,
        }
        print(f"[LLM ENV] {json.dumps(payload, ensure_ascii=False)}", file=sys.stderr, flush=True)

    def set_logger(self, log_fn: Callable[[str, dict], None]):
        """Attach an optional structured logger: log_fn(tag, data_dict)."""
        self._log = log_fn

    def _get_client(self) -> OpenAI:
        if self._client is None:
            base = self.config.api_base.rstrip("/")
            # Some API bases include the full endpoint path — strip to the base URL
            if base.endswith("/chat/completions"):
                base = base[: -len("/chat/completions")]
            actual_api_base = base or "https://api.deepseek.com/v1"

            htimeout = httpx.Timeout(
                connect=10, read=100, write=10, pool=5,
            )
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=actual_api_base,
                max_retries=0,
                timeout=htimeout,
            )
        return self._client

    @staticmethod
    def _is_retryable_api_error(exc: Exception) -> bool:
        if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)):
            return True
        if isinstance(exc, APIError):
            status_code = getattr(exc, "status_code", None)
            return status_code is None or int(status_code) >= 500
        return False

    def _api_error_ai_message(self, exc: Exception) -> AIMessage:
        payload = {
            "error_type": type(exc).__name__,
            "status_code": getattr(exc, "status_code", None),
            "message": str(exc),
            "retryable": self._is_retryable_api_error(exc),
        }
        return AIMessage(
            content=f"[LLM API Error] {json.dumps(payload, ensure_ascii=False)}",
            tool_calls=[],
            additional_kwargs={"llm_error": payload},
        )

    # ── Message conversion ──────────────────────────────────────────

    @staticmethod
    def _to_openai_message(msg: Any) -> Dict[str, Any]:
        if isinstance(msg, dict):
            return {"role": msg.get("role", "user"), "content": str(msg.get("content", ""))}
        if isinstance(msg, SystemMessage):
            return {"role": "system", "content": msg.content}
        if isinstance(msg, HumanMessage):
            return {"role": "user", "content": msg.content}
        if isinstance(msg, AIMessage):
            d: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"]),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.additional_kwargs and "reasoning_content" in msg.additional_kwargs:
                d["reasoning_content"] = msg.additional_kwargs["reasoning_content"]
            return d
        if isinstance(msg, ToolMessage):
            return {
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": msg.content,
            }
        return {"role": "user", "content": str(msg.content)}

    # ── Retry ───────────────────────────────────────────────────────

    def _with_retry(self, fn: Callable[[], Any], max_retries: int = 5) -> Any:
        last_exc = None
        max_delay = 60.0
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except (APITimeoutError, RateLimitError, InternalServerError) as e:
                last_exc = e
                if attempt < max_retries:
                    delay = min(4.0 * (2 ** attempt), max_delay)
                    time.sleep(delay)
            except APIError as e:
                last_exc = e
                if attempt < max_retries:
                    delay = min(4.0 * (2 ** attempt), max_delay)
                    time.sleep(delay)
                else:
                    raise
            except Exception as e:
                last_exc = e
                if attempt < max_retries:
                    delay = min(4.0 * (2 ** attempt), max_delay)
                    time.sleep(delay)
        raise last_exc  # type: ignore

    @staticmethod
    def _extract_json_object(text: str) -> Optional[dict]:
        text = (text or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            parts = text.split("```")
            candidates = [part.strip() for part in parts if part.strip() and not part.strip().startswith(("json", "python"))]
        else:
            candidates = [text]

        for candidate in candidates:
            start = candidate.find("{")
            if start < 0:
                continue
            depth = 0
            in_string = False
            escape = False
            for idx, ch in enumerate(candidate[start:], start=start):
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        payload = candidate[start : idx + 1]
                        try:
                            parsed = json.loads(payload)
                        except json.JSONDecodeError:
                            break
                        if isinstance(parsed, dict):
                            return parsed
                        break
        return None

    @classmethod
    def _tool_call_from_content(cls, content: str) -> tuple[list[dict], dict]:
        parsed = cls._extract_json_object(content)
        if not parsed:
            return [], {}
        if "name" not in parsed or "arguments" not in parsed:
            return [], {}

        args = parsed["arguments"]
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return [], {}
        if not isinstance(args, dict):
            return [], {}

        tool_call = {
            "id": "content-tool-call-0",
            "name": str(parsed["name"]),
            "args": args,
        }
        meta = {
            "content_tool_call_fallback": True,
            "content_tool_call_name": tool_call["name"],
        }
        return [tool_call], meta

    @staticmethod
    def _normalize_tool_choice(
        tool_choice: Optional[str],
        tools: List[Dict[str, Any]],
    ) -> Optional[str | Dict[str, Any]]:
        if tool_choice != "required":
            return tool_choice
        if len(tools) == 1:
            function_name = tools[0].get("function", {}).get("name")
            if function_name:
                return {
                    "type": "function",
                    "function": {"name": function_name},
                }
        return "auto"

    # ── Main call ───────────────────────────────────────────────────

    def call(
        self,
        messages: Sequence[BaseMessage],
        tools: List[Dict[str, Any]],
        tool_choice: Optional[str] = None,
    ) -> AIMessage:
        """Call the LLM and return an AIMessage (may contain tool_calls).

        Args:
            tool_choice: Passed through to OpenAI API. "required" forces the model
                         to call at least one tool. Default (None) = "auto".
        Returns AIMessage with error details on failure — never raises.
        """
        cfg = self.config
        _model_lower = cfg.model.lower()
        # Fast models finish quickly; slower reasoning models need longer read timeout
        read_timeout = 120 if any(kw in _model_lower for kw in ("flash", "haiku", "mini")) else 400

        openai_msgs = [self._to_openai_message(m) for m in messages]

        kwargs: Dict[str, Any] = {
            "model": cfg.model,
            "messages": openai_msgs,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
        }
        if cfg.seed is not None:
            kwargs["seed"] = cfg.seed
        if tools:
            kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = self._normalize_tool_choice(tool_choice, tools)

        client = self._get_client()
        req_timeout = httpx.Timeout(connect=10, read=read_timeout, write=10, pool=5)

        try:
            response = self._with_retry(
                lambda: client.chat.completions.create(**kwargs, timeout=req_timeout),
                max_retries=2,
            )
        except RateLimitError as e:
            return self._api_error_ai_message(e)
        except APITimeoutError as e:
            return self._api_error_ai_message(e)
        except InternalServerError as e:
            return self._api_error_ai_message(e)
        except APIError as e:
            return self._api_error_ai_message(e)
        except Exception as e:
            return self._api_error_ai_message(e)

        if not response.choices:
            return AIMessage(content="[LLM API Error] No choices returned.", tool_calls=[])

        choice = response.choices[0]
        message = choice.message
        content = message.content or ""
        raw_tool_calls = message.tool_calls or []

        # ── JSON parse retry on tool_calls arguments ──────────────────
        parse_meta: dict = {}
        lc_tool_calls: list = []
        for _parse_attempt in range(2):
            try:
                lc_tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": json.loads(tc.function.arguments) if tc.function.arguments else {},
                    }
                    for tc in raw_tool_calls
                ]
                break
            except json.JSONDecodeError as e:
                if _parse_attempt == 0:
                    # Preserve first-attempt raw response info
                    parse_meta["parse_repair_used"] = True
                    parse_meta["first_raw_arguments"] = (
                        raw_tool_calls[0].function.arguments if raw_tool_calls else ""
                    )
                    parse_meta["first_finish_reason"] = getattr(choice, "finish_reason", None)
                    parse_meta["first_usage"] = (
                        {
                            "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                            "completion_tokens": response.usage.completion_tokens if response.usage else None,
                            "total_tokens": response.usage.total_tokens if response.usage else None,
                        }
                        if hasattr(response, "usage") and response.usage
                        else None
                    )
                    parse_meta["first_error"] = str(e)

                    # Retry: re-call API with same messages + tools
                    try:
                        response = self._with_retry(
                            lambda: client.chat.completions.create(**kwargs, timeout=req_timeout),
                            max_retries=2,
                        )
                        if not response.choices:
                            parse_meta["llm_parse_failed"] = True
                            parse_meta["final_error"] = "Retry: no choices returned"
                            break
                        choice = response.choices[0]
                        message = choice.message
                        content = message.content or ""
                        raw_tool_calls = message.tool_calls or []
                    except Exception as api_e:
                        parse_meta["llm_parse_failed"] = True
                        parse_meta["final_error"] = f"Retry API error: {api_e}"
                        break
                else:
                    parse_meta["llm_parse_failed"] = True
                    parse_meta["final_error"] = str(e)
                    break

        additional_kwargs = {}
        if tools and not lc_tool_calls and content:
            content_tool_calls, content_meta = self._tool_call_from_content(content)
            if content_tool_calls:
                lc_tool_calls = content_tool_calls
                additional_kwargs.update(content_meta)
        if parse_meta.get("parse_repair_used") or parse_meta.get("llm_parse_failed"):
            additional_kwargs["_parse_meta"] = parse_meta
        # Some providers expose reasoning in model_extra, not as a direct attribute
        reasoning = getattr(message, "reasoning_content", None)
        if not reasoning:
            extra = getattr(message, "model_extra", None) or {}
            reasoning = extra.get("reasoning_content")
        if reasoning:
            additional_kwargs["reasoning_content"] = reasoning

        return AIMessage(content=content, tool_calls=lc_tool_calls, additional_kwargs=additional_kwargs)
