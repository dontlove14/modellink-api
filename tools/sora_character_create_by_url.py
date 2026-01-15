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


class SoraCharacterCreateByUrlTool(Tool):
    def _create_retry_session(self) -> requests.Session:
        """创建带重试策略的 HTTP Session

        说明:
            - 用于应对网络抖动、连接重置、服务端临时 5xx 等问题
            - 对于 5xx 错误会进行指数退避重试
        """
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        session.trust_env = False
        retry_strategy = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(["POST"]),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _normalize_param(self, value: Any) -> Any:
        """规范化工具参数值

        规则:
            - 当参数值为字符串 'variable'（前端默认引用变量占位）时，视为未传入并置为 None
        """
        if isinstance(value, str) and value == "variable":
            return None
        return value

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """通过视频 URL 创建 Sora 角色（真人角色可用）

        参数:
            tool_parameters:
                - apiKey: 鉴权用 API Key
                - url: 用于创建角色的视频链接（接口字段 url）
                - timestamps: 角色片段时间范围（接口字段 timestamps，格式如 1,3，跨度不大于 3 秒）

        行为:
            - 向固定主机 https://api.modellink.online 的 /v1/videos 提交角色创建任务
            - 请求体为 application/json，固定 model=sora-2-character，prompt 为必填占位字符串
            - 成功时返回标准化 JSON 消息（包含任务 id、状态、角色信息等）
        """
        host = "https://api.modellink.online"

        api_key = self._normalize_param(tool_parameters.get("apiKey"))
        url = self._normalize_param(tool_parameters.get("url"))
        timestamps = self._normalize_param(tool_parameters.get("timestamps"))

        if not api_key or not url or not timestamps:
            raise ValueError("apiKey、url、timestamps 为必填参数")

        logger.info(f"[Sora Character Create By URL] 开始创建角色，url: {url}, timestamps: {timestamps}")

        request_json = {
            "model": "sora-2-character",
            "prompt": "123",
            "url": url,
            "timestamps": timestamps,
        }

        api_url = f"{host}/v1/videos"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            session = self._create_retry_session()
            response = session.post(api_url, headers=headers, json=request_json, timeout=(10, 120))

            logger.info(f"[Sora Character Create By URL] 响应状态: {response.status_code}")

            if not response.ok:
                logger.error(f"[Sora Character Create By URL] 错误响应: {response.text}")
                response.raise_for_status()

            try:
                result = response.json()
            except ValueError:
                logger.error(f"[Sora Character Create By URL] 非 JSON 响应: {response.text}")
                raise Exception("服务返回非 JSON 响应")

            if isinstance(result, dict) and result.get("code") and result.get("description") and not result.get("id"):
                raise Exception(str(result.get("description")))

            logger.info(f"[Sora Character Create By URL] 请求成功，任务 ID: {result.get('id')}")

            response_result = {
                "success": True,
                "message": "角色创建任务已提交",
                "data": {
                    "id": result.get("id"),
                    "object": result.get("object"),
                    "model": result.get("model"),
                    "status": result.get("status"),
                    "progress": result.get("progress"),
                    "created_at": result.get("created_at"),
                },
            }

            yield self.create_json_message(response_result)

        except requests.exceptions.RequestException as e:
            logger.error(f"[Sora Character Create By URL] 网络异常: {str(e)}")
            raise Exception(str(e))
        except Exception as e:
            logger.error(f"[Sora Character Create By URL] 异常: {str(e)}")
            raise
