import json
from typing import Dict, Optional
from urllib import error, request

from app.config import CONFIG
from app.logging_config import get_logger
from app.utils import dedupe_keep_order

logger = get_logger(__name__)
LAST_QWEN_ERROR: Optional[str] = None


def get_last_qwen_error() -> Optional[str]:
    return LAST_QWEN_ERROR


def call_local_qwen(symbol: str, report_text: str, signals: Dict[str, str]) -> Optional[str]:
    """Call local OpenAI-compatible Qwen endpoint for signal explanation."""
    global LAST_QWEN_ERROR
    LAST_QWEN_ERROR = None

    candidate_bases = dedupe_keep_order([CONFIG.qwen_base_url.rstrip("/"), "http://127.0.0.1:11434/v1"])
    candidate_models = dedupe_keep_order([CONFIG.qwen_model, "qwen2.5:32b"])

    prompt = (
        f"你是A股量化研究助理。请基于以下技术信号给出简短解读与风险提示，"
        f"不要给出确定性收益承诺。\n\n股票: {symbol}\n"
        f"技术信号: {json.dumps(signals, ensure_ascii=False)}\n\n"
        f"数据摘要:\n{report_text}\n\n"
        "请输出3段：\n"
        "1) 当前结构判断\n"
        "2) 可执行观察点（2-3条）\n"
        "3) 风险控制建议\n"
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
                                {"role": "system", "content": "你是谨慎的A股技术分析助手。"},
                                {"role": "user", "content": prompt},
                            ],
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
                            return native_data["message"]["content"].strip()
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
                    {"role": "system", "content": "你是谨慎的A股技术分析助手。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
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
                    return data["choices"][0]["message"]["content"].strip()
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
                                    {"role": "system", "content": "你是谨慎的A股技术分析助手。"},
                                    {"role": "user", "content": prompt},
                                ],
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
                                return native_data["message"]["content"].strip()
                    except (error.URLError, error.HTTPError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as native_exc:
                        if LAST_QWEN_ERROR is None:
                            LAST_QWEN_ERROR = (
                                f"Qwen调用失败(含Ollama兜底): model={model}, "
                                f"error={type(native_exc).__name__}: {native_exc}"
                            )
                            logger.warning(LAST_QWEN_ERROR)
                continue
    return None
