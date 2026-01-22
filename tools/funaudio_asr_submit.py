from __future__ import annotations

from collections.abc import Generator
from typing import Any, Dict, List, Optional
import json
import logging

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.config.logger_format import plugin_logger_handler


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class FunAudioAsrSubmitTool(Tool):
    def _normalize_param(self, value: Any) -> Any:
        """规范化工具参数值。

        规则:
            - 当参数值为字符串 'variable'（前端默认引用变量占位）时，视为未传入并置为 None。
            - 当参数为字符串且仅包含空白时，视为未传入并置为 None。
        """
        if isinstance(value, str):
            if value == "variable":
                return None
            if value.strip() == "":
                return None
        return value

    def _parse_csv_list(self, value: Any) -> List[str]:
        """将逗号分隔字符串解析为字符串列表。"""
        normalized = self._normalize_param(value)
        if normalized is None:
            return []
        if isinstance(normalized, list):
            return [str(item).strip() for item in normalized if str(item).strip()]
        if not isinstance(normalized, str):
            return [str(normalized).strip()] if str(normalized).strip() else []

        text = normalized.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass

        return [part.strip() for part in text.split(",") if part.strip()]

    def _parse_csv_int_list(self, value: Any) -> Optional[List[int]]:
        """将逗号分隔字符串解析为整数列表；缺省返回 None。"""
        items = self._parse_csv_list(value)
        if not items:
            return None
        result: List[int] = []
        for item in items:
            try:
                result.append(int(item))
            except Exception as e:
                raise ValueError(f"channel_id 必须为整数列表，无法解析: {item}") from e
        return result

    def _parse_bool(self, value: Any) -> Optional[bool]:
        """解析布尔参数；缺省返回 None。"""
        normalized = self._normalize_param(value)
        if normalized is None:
            return None
        if isinstance(normalized, bool):
            return normalized
        if isinstance(normalized, (int, float)):
            return bool(normalized)
        if isinstance(normalized, str):
            text = normalized.strip().lower()
            if text in {"true", "1", "yes", "y", "on"}:
                return True
            if text in {"false", "0", "no", "n", "off"}:
                return False
        raise ValueError("diarization_enabled 需为布尔值")

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """提交百炼（FunAudio-ASR）录音文件识别任务。

        参数:
            tool_parameters:
                - apiKey: 鉴权用 API Key
                - model: 模型名，例如 fun-asr
                - file_urls: 录音文件 URL 列表（CSV 字符串或 JSON 数组字符串），最多 100
                - vocabulary_id: 热词 ID（可选）
                - channel_id: 音轨索引（CSV 字符串，可选）
                - special_word_filter: 敏感词过滤 JSON 字符串（可选）
                - diarization_enabled: 是否开启说话人分离（可选）
                - speaker_count: 说话人数量参考（可选）
                - language_hints: 语言提示（CSV 字符串，可选）

        行为:
            - 向文档主机 https://dashscope.aliyuncs.com 的 /api/v1/services/audio/asr/transcription 提交异步任务
            - 成功时返回 task_id 与 task_status

        异常:
            - 参数缺失、网络错误、HTTP 非 2xx、JSON 解析失败直接抛出异常
        """
        host = "https://dashscope.aliyuncs.com"

        api_key = self._normalize_param(tool_parameters.get("apiKey"))
        model = self._normalize_param(tool_parameters.get("model"))
        file_urls_raw = tool_parameters.get("file_urls")

        if not api_key or not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("缺少有效的 apiKey")
        if not model or not isinstance(model, str) or not model.strip():
            raise ValueError("model 为必填参数")

        file_urls = self._parse_csv_list(file_urls_raw)
        if not file_urls:
            raise ValueError("file_urls 为必填参数，且至少包含 1 个 URL")
        if len(file_urls) > 100:
            raise ValueError("file_urls 单次最多支持 100 个 URL")

        vocabulary_id = self._normalize_param(tool_parameters.get("vocabulary_id"))
        channel_id = self._parse_csv_int_list(tool_parameters.get("channel_id"))
        special_word_filter = self._normalize_param(tool_parameters.get("special_word_filter"))
        diarization_enabled = self._parse_bool(tool_parameters.get("diarization_enabled"))
        speaker_count = self._normalize_param(tool_parameters.get("speaker_count"))
        language_hints = self._parse_csv_list(tool_parameters.get("language_hints"))

        parameters: Dict[str, Any] = {}
        if vocabulary_id is not None:
            parameters["vocabulary_id"] = vocabulary_id
        if channel_id is not None:
            parameters["channel_id"] = channel_id
        if special_word_filter is not None:
            parameters["special_word_filter"] = special_word_filter
        if diarization_enabled is not None:
            parameters["diarization_enabled"] = diarization_enabled
        if speaker_count is not None:
            try:
                parameters["speaker_count"] = int(speaker_count)
            except Exception as e:
                raise ValueError("speaker_count 必须为整数") from e
        if language_hints:
            parameters["language_hints"] = language_hints

        request_body: Dict[str, Any] = {
            "model": model,
            "input": {"file_urls": file_urls},
        }
        if parameters:
            request_body["parameters"] = parameters

        api_url = f"{host}/api/v1/services/audio/asr/transcription"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

        logger.info(f"[FunAudio ASR Submit] 开始提交任务，files: {len(file_urls)}，model: {model}")

        try:
            response = requests.post(api_url, headers=headers, json=request_body, timeout=600)
            logger.info(f"[FunAudio ASR Submit] 响应状态: {response.status_code}")

            if not response.ok:
                error_text = response.text
                logger.error(f"[FunAudio ASR Submit] 错误响应: {error_text}")
                response.raise_for_status()

            result = response.json()
            output = result.get("output", {}) if isinstance(result, dict) else {}

            task_id = output.get("task_id")
            task_status = output.get("task_status")
            response_result = {
                "success": True,
                "message": "任务提交成功",
                "data": {
                    "task_id": task_id,
                    "task_status": task_status,
                    "request_id": result.get("request_id") if isinstance(result, dict) else None,
                    "raw": result,
                },
            }
            yield self.create_json_message(response_result)
        except requests.exceptions.RequestException as e:
            logger.error(f"[FunAudio ASR Submit] 网络异常: {str(e)}")
            raise Exception(str(e))
        except Exception as e:
            logger.error(f"[FunAudio ASR Submit] 异常: {str(e)}")
            raise
