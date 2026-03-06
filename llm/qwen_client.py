import json
from typing import Any, Dict, Optional
from urllib import error, request

from app.config import CONFIG
from app.logging_config import get_logger
from app.utils import dedupe_keep_order
from llm.prompts import SYSTEM_PROMPT, build_structured_analysis_prompt
from llm.summarizer import format_structured_summary, parse_structured_summary

logger = get_logger(__name__)
LAST_QWEN_ERROR: Optional[str] = None
LAST_QWEN_STRUCTURED: Optional[dict[str, Any]] = None


def get_last_qwen_error() -> Optional[str]:
    return LAST_QWEN_ERROR


def get_last_qwen_structured() -> Optional[dict[str, Any]]:
    return LAST_QWEN_STRUCTURED


def _postprocess_llm_content(raw_content: str) -> str:
    global LAST_QWEN_STRUCTURED
    parsed = parse_structured_summary(raw_content)
    LAST_QWEN_STRUCTURED = parsed
    return format_structured_summary(parsed)


def call_local_qwen(
    symbol: str,
    report_text: str,
    signals: Dict[str, str],
    temperature: float = 0.1,
    stability_mode: bool = False,
) -> Optional[str]:
    """Call local OpenAI-compatible Qwen endpoint for signal explanation."""
    global LAST_QWEN_ERROR
    global LAST_QWEN_STRUCTURED
    LAST_QWEN_ERROR = None
    LAST_QWEN_STRUCTURED = None
    safe_temperature = max(float(temperature), 0.0)

    candidate_bases = dedupe_keep_order([CONFIG.qwen_base_url.rstrip("/"), "http://127.0.0.1:11434/v1"])
    candidate_models = dedupe_keep_order([CONFIG.qwen_model, "qwen2.5:32b"])
    prompt = build_structured_analysis_prompt(
        symbol=symbol,
        report_text=report_text,
        signals=signals,
        stability_mode=stability_mode,
    )

    for base_url in candidate_bases:
        for model in candidate_models:
            if "11434" in base_url:
                native_req = request.Request(
                    url="http://127.0.0.1:11434/api/chat",
                    data=json.dumps(
                        {
                            "model": model,
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            "options": {"temperature": safe_temperature},
                            "stream": False,
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with request.urlopen(native_req, timeout=CONFIG.qwen_timeout) as native_resp:
                        native_data = json.loads(native_resp.read().decode("utf-8"))
                        if "message" in native_data and "content" in native_data["message"]:
                            return _postprocess_llm_content(native_data["message"]["content"].strip())
                except (error.URLError, error.HTTPError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as native_exc:
                    if LAST_QWEN_ERROR is None:
                        LAST_QWEN_ERROR = (
                            f"Qwen调用失败(先尝试Ollama原生接口): model={model}, "
                            f"error={type(native_exc).__name__}: {native_exc}"
                        )
                        logger.warning(LAST_QWEN_ERROR)

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": safe_temperature,
            }

            req = request.Request(
                url=f"{base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {CONFIG.qwen_api_key}",
                },
                method="POST",
            )

            try:
                with request.urlopen(req, timeout=CONFIG.qwen_timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return _postprocess_llm_content(data["choices"][0]["message"]["content"].strip())
            except (error.URLError, error.HTTPError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
                if LAST_QWEN_ERROR is None:
                    LAST_QWEN_ERROR = f"Qwen调用失败: {base_url}, model={model}, error={type(exc).__name__}: {exc}"
                    logger.warning(LAST_QWEN_ERROR)
                if "11434" in base_url and isinstance(exc, error.HTTPError) and exc.code == 404:
                    native_req = request.Request(
                        url="http://127.0.0.1:11434/api/chat",
                        data=json.dumps(
                            {
                                "model": model,
                                "messages": [
                                    {"role": "system", "content": SYSTEM_PROMPT},
                                    {"role": "user", "content": prompt},
                                ],
                                "options": {"temperature": safe_temperature},
                                "stream": False,
                            }
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    try:
                        with request.urlopen(native_req, timeout=35) as native_resp:
                            native_data = json.loads(native_resp.read().decode("utf-8"))
                            if "message" in native_data and "content" in native_data["message"]:
                                return _postprocess_llm_content(native_data["message"]["content"].strip())
                    except (error.URLError, error.HTTPError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as native_exc:
                        if LAST_QWEN_ERROR is None:
                            LAST_QWEN_ERROR = (
                                f"Qwen调用失败(含Ollama兜底): model={model}, "
                                f"error={type(native_exc).__name__}: {native_exc}"
                            )
                            logger.warning(LAST_QWEN_ERROR)
                continue
    return None
