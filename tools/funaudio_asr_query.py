from __future__ import annotations

from collections.abc import Generator
from typing import Any, Dict
import logging

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.config.logger_format import plugin_logger_handler


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class FunAudioAsrQueryTool(Tool):
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

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """查询百炼（FunAudio-ASR）录音文件识别任务状态与结果。

        参数:
            tool_parameters:
                - apiKey: 鉴权用 API Key
                - task_id: 提交任务接口返回的 task_id

        行为:
            - 向文档主机 https://dashscope.aliyuncs.com 的 /api/v1/tasks/{task_id} 查询任务
            - 成功时返回任务状态、子任务结果等原始响应

        异常:
            - 参数缺失、网络错误、HTTP 非 2xx、JSON 解析失败直接抛出异常
        """
        host = "https://dashscope.aliyuncs.com"

        api_key = self._normalize_param(tool_parameters.get("apiKey"))
        task_id = self._normalize_param(tool_parameters.get("task_id"))

        if not api_key or not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("缺少有效的 apiKey")
        if not task_id or not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id 为必填参数")

        api_url = f"{host}/api/v1/tasks/{task_id}"
        headers = {"Authorization": f"Bearer {api_key}"}

        logger.info(f"[FunAudio ASR Query] 开始查询任务，task_id: {task_id}")

        try:
            response = requests.post(api_url, headers=headers, timeout=120)
            logger.info(f"[FunAudio ASR Query] 响应状态: {response.status_code}")

            if not response.ok:
                error_text = response.text
                logger.error(f"[FunAudio ASR Query] 错误响应: {error_text}")
                response.raise_for_status()

            result = response.json()
            output = result.get("output", {}) if isinstance(result, dict) else {}
            task_status = output.get("task_status") if isinstance(output, dict) else None

            response_result = {
                "success": True,
                "message": "任务查询成功",
                "data": {
                    "task_id": output.get("task_id") if isinstance(output, dict) else task_id,
                    "task_status": task_status,
                    "results": output.get("results") if isinstance(output, dict) else None,
                    "task_metrics": output.get("task_metrics") if isinstance(output, dict) else None,
                    "usage": result.get("usage") if isinstance(result, dict) else None,
                    "request_id": result.get("request_id") if isinstance(result, dict) else None,
                    "raw": result,
                },
            }
            yield self.create_json_message(response_result)
        except requests.exceptions.RequestException as e:
            logger.error(f"[FunAudio ASR Query] 网络异常: {str(e)}")
            raise Exception(str(e))
        except Exception as e:
            logger.error(f"[FunAudio ASR Query] 异常: {str(e)}")
            raise
