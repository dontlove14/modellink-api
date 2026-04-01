from __future__ import annotations

from typing import Any
import json

import requests


HOST = "https://api.modellink.online"


def normalize_param(value: Any) -> Any:
    """归一化单个参数值。"""
    if value == "variable":
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return stripped
    return value


def normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    """归一化工具参数字典。"""
    return {key: normalize_param(value) for key, value in params.items()}


def require_param(params: dict[str, Any], name: str) -> Any:
    """读取必填参数，不存在时抛出异常。"""
    value = params.get(name)
    if value is None:
        raise ValueError(f"{name} 为必填参数")
    return value


def build_headers(api_key: str, auth_type: str = "bearer") -> dict[str, str]:
    """构建认证请求头。"""
    if auth_type == "token":
        authorization = f"Token {api_key}"
    else:
        authorization = f"Bearer {api_key}"
    return {
        "Authorization": authorization,
        "Content-Type": "application/json",
    }


def filter_none_values(value: Any) -> Any:
    """递归移除值中的空字段。"""
    if isinstance(value, dict):
        filtered: dict[str, Any] = {}
        for key, item in value.items():
            normalized = filter_none_values(item)
            if normalized is not None:
                filtered[key] = normalized
        return filtered
    if isinstance(value, list):
        return [item for item in (filter_none_values(item) for item in value) if item is not None]
    return value


def parse_string_list(value: Any) -> list[str]:
    """解析字符串列表，支持 JSON 数组、换行或逗号分隔。"""
    normalized = normalize_param(value)
    if normalized is None:
        return []
    if isinstance(normalized, list):
        return [str(item).strip() for item in normalized if str(item).strip()]
    if not isinstance(normalized, str):
        text = str(normalized).strip()
        return [text] if text else []
    if normalized.startswith("[") and normalized.endswith("]"):
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    for separator in ("\n", ","):
        if separator in normalized:
            return [item.strip() for item in normalized.split(separator) if item.strip()]
    return [normalized]


def parse_int_value(value: Any) -> int | None:
    """将输入转换为整数。"""
    normalized = normalize_param(value)
    if normalized is None:
        return None
    return int(normalized)


def extract_error_message(value: Any) -> str | None:
    """递归提取接口错误消息。"""
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("message", "detail", "error_description"):
            nested = extract_error_message(value.get(key))
            if nested:
                return nested
        nested_error = extract_error_message(value.get("error"))
        if nested_error:
            return nested_error
        return None
    if isinstance(value, list):
        for item in value:
            nested = extract_error_message(item)
            if nested:
                return nested
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.startswith("not ok match:"):
            nested = extract_error_message(text.split("not ok match:", 1)[1].strip())
            if nested:
                return nested
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if parsed is not None:
            nested = extract_error_message(parsed)
            if nested:
                return nested
        return text
    return str(value)


def request_json(
    method: str,
    path: str,
    api_key: str,
    auth_type: str = "bearer",
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """发起 JSON 请求并返回响应体。"""
    session = requests.Session()
    session.trust_env = False
    response = session.request(
        method=method.upper(),
        url=f"{HOST}{path}",
        headers=build_headers(api_key, auth_type=auth_type),
        json=filter_none_values(json_body) if json_body is not None else None,
        timeout=(10, 120),
    )
    if not response.ok:
        try:
            error_json = response.json()
        except Exception:
            error_json = None
        message = extract_error_message(error_json)
        if not message:
            message = extract_error_message(response.text) or f"HTTP {response.status_code}"
        raise Exception(f"API 请求失败: {message}")
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("接口返回结果不是 JSON 对象")
    return result


def build_submit_message(message: str, data: dict[str, Any]) -> dict[str, Any]:
    """构建任务提交成功的标准返回结构。"""
    return {
        "success": True,
        "message": message,
        "data": data,
    }


def build_query_message(message: str, data: dict[str, Any]) -> dict[str, Any]:
    """构建任务查询成功的标准返回结构。"""
    return {
        "success": True,
        "message": message,
        "data": data,
    }
