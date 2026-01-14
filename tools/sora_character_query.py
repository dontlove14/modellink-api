from collections.abc import Generator
from typing import Any
import logging

import requests
from dify_plugin import Tool
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class SoraCharacterQueryTool(Tool):
    def _normalize_param(self, value: Any) -> Any:
        """规范化工具参数值

        规则:
            - 当参数值为字符串 'variable'（前端默认引用变量占位）时，视为未传入并置为 None
        """
        if isinstance(value, str) and value == "variable":
            return None
        return value

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """查询角色创建结果

        参数:
            tool_parameters:
                - apiKey: 鉴权用 API Key
                - id: 角色任务 ID（路径参数 video_id）

        行为:
            - 向固定主机 https://api.modellink.online 的 /v1/videos/{video_id} 获取任务详情
            - 成功时返回标准化 JSON 消息（包含状态、进度、头像、视频链接等）
        """
        host = "https://api.modellink.online"

        api_key = self._normalize_param(tool_parameters.get("apiKey"))
        video_id = self._normalize_param(tool_parameters.get("id"))

        if not api_key or not video_id:
            raise ValueError("apiKey 和 id 为必填参数")

        logger.info(f"[Sora Character Query] 查询角色任务，ID: {video_id}")

        api_url = f"{host}/v1/videos/{video_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(api_url, headers=headers, timeout=120)
            logger.info(f"[Sora Character Query] 响应状态: {response.status_code}")

            if not response.ok:
                logger.error(f"[Sora Character Query] 错误响应: {response.text}")
                response.raise_for_status()

            result = response.json()
            logger.info(f"[Sora Character Query] 状态: {result.get('status')}, 进度: {result.get('progress')}")

            response_result = {
                "success": True,
                "message": "角色创建结果查询成功",
                "data": {
                    "id": result.get("id"),
                    "object": result.get("object"),
                    "model": result.get("model"),
                    "status": result.get("status"),
                    "progress": result.get("progress"),
                    "username": result.get("username"),
                    "avatar_url": result.get("avatar_url"),
                    "video_url": result.get("video_url"),
                    "url": result.get("url"),
                    "result_url": result.get("result_url"),
                    "seconds": result.get("seconds"),
                    "size": result.get("size"),
                    "created_at": result.get("created_at"),
                    "completed_at": result.get("completed_at"),
                    "expires_at": result.get("expires_at"),
                    "remixed_from_video_id": result.get("remixed_from_video_id"),
                    "error": result.get("error"),
                },
            }

            yield self.create_json_message(response_result)

        except requests.exceptions.RequestException as e:
            logger.error(f"[Sora Character Query] 网络异常: {str(e)}")
            raise Exception(str(e))
        except Exception as e:
            logger.error(f"[Sora Character Query] 异常: {str(e)}")
            raise
