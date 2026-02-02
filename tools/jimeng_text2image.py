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


class JimengText2ImageTool(Tool):
    def _normalize_param(self, value: Any) -> Any:
        """规范化工具参数值。

        规则:
            - 当参数值为字符串 'variable'（前端默认引用变量占位）时，视为未传入并置为 None
        """
        if isinstance(value, str) and value == "variable":
            return None
        return value

    def _build_prompt(self, prompt: str, aspect_ratio: str | None, resolution: str | None) -> str:
        """将宽高比与分辨率拼接进提示词。

        说明:
            - 即梦/Seedream 的宽高比与分辨率通过提示词传递（如：\"16:9 2K\"）
            - 若未选择，则不做拼接
        """
        parts: list[str] = [prompt.strip()]
        if aspect_ratio:
            parts.append(aspect_ratio)
        if resolution:
            parts.append(resolution)
        return " ".join([p for p in parts if p]).strip()

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """即梦 文生图（/v1/images/generations）。

        参数:
            tool_parameters:
                - api_key: 鉴权用 API Key
                - prompt: 文生图提示词
                - aspect_ratio: 宽高比（可选，拼接到提示词）
                - resolution: 分辨率（可选，拼接到提示词）
        """
        host = "https://api.modellink.online"
        api_url = f"{host}/v1/images/generations"
        model = "jimeng-4.5"

        api_key = self._normalize_param(tool_parameters.get("api_key"))
        prompt = self._normalize_param(tool_parameters.get("prompt"))
        aspect_ratio = self._normalize_param(tool_parameters.get("aspect_ratio"))
        resolution = self._normalize_param(tool_parameters.get("resolution"))

        if not api_key or not prompt:
            raise ValueError("api_key 和 prompt 为必填参数")

        final_prompt = self._build_prompt(str(prompt), aspect_ratio, resolution)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "prompt": final_prompt,
        }

        logger.info(
            f"[Jimeng Text2Image] 请求生成图片，model={model}, prompt_len={len(final_prompt)}"
        )

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=300)
            logger.info(f"[Jimeng Text2Image] 响应状态: {response.status_code}")

            if not response.ok:
                logger.error(f"[Jimeng Text2Image] 错误响应: {response.text}")
                response.raise_for_status()

            result = response.json()
            urls = [item.get("url") for item in (result.get("data") or []) if isinstance(item, dict)]

            response_result = {
                "success": True,
                "message": "即梦文生图生成成功",
                "data": {
                    "model": model,
                    "prompt": final_prompt,
                    "created": result.get("created"),
                    "images": urls,
                    "raw": result,
                },
            }
            yield self.create_json_message(response_result)

        except requests.exceptions.RequestException as e:
            logger.error(f"[Jimeng Text2Image] 网络异常: {str(e)}")
            raise Exception(str(e))
        except Exception as e:
            logger.error(f"[Jimeng Text2Image] 异常: {str(e)}")
            raise
