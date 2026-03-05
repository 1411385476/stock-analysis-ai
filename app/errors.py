from enum import Enum


class ErrorCode(str, Enum):
    INPUT = "E_INPUT"
    DATA_FETCH = "E_DATA_FETCH"
    DATA_SCHEMA = "E_DATA_SCHEMA"
    SNAPSHOT = "E_SNAPSHOT"
    LLM_CALL = "E_LLM_CALL"
    NETWORK_RESTRICTED = "E_NETWORK_RESTRICTED"
    UNKNOWN = "E_UNKNOWN"


def format_error(code: ErrorCode, message: str) -> str:
    return f"[{code.value}] {message}"
