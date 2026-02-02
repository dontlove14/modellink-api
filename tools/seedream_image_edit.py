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


class SeedreamImageEditTool(Tool):
    def _normalize_param(self, value: Any) -> Any:
        """规范化工具参数值。

        规则:
            - 当参数值为字符串 'variable'（前端默认引用变量占位）时，视为未传入并置为 None
        """
        if isinstance(value, str) and value == "variable":
            return None
        return value

    def _build_prompt(self, prompt: str, aspect_ratio: str | None, resolution: str | None) -> str:
        """规范化提示词。

        说明:
            - 对于 Seedream，宽高比通过 size 字段传递，而不是拼接进提示词
        """
        return prompt.strip()

    def _normalize_bool(self, value: Any) -> bool | None:
        """规范化布尔参数。

        规则:
            - 参数值为字符串 'variable' 时视为未传入
            - 支持 bool、以及字符串 true/false/1/0
        """
        normalized = self._normalize_param(value)
        if normalized is None:
            return None
        if isinstance(normalized, bool):
            return normalized
        if isinstance(normalized, (int, float)):
            return bool(normalized)
        if isinstance(normalized, str):
            lowered = normalized.strip().lower()
            if lowered in {"true", "1", "yes", "y"}:
                return True
            if lowered in {"false", "0", "no", "n"}:
                return False
        return None

    def _round_to_multiple(self, value: float, multiple: int) -> int:
        """将数值四舍五入到指定倍数，并确保结果至少为 multiple。"""
        rounded = int(round(value / multiple)) * multiple
        return max(multiple, rounded)

    def _calc_size(self, aspect_ratio: str | None) -> str | None:
        """根据宽高比换算 size（\"WIDTHxHEIGHT\"）。

        规则:
            - Seedream 4.5 采用固定尺寸映射（避免上游对 size 的校验差异）
            - 映射:
                - 1:1  -> 2048x2048
                - 4:3  -> 2304x1728
                - 3:4  -> 1728x2304
                - 16:9 -> 2560x1440
                - 9:16 -> 1440x2560
                - 21:9 -> 3024x1296
        """
        ratio = (str(aspect_ratio).strip() if aspect_ratio else "1:1")

        fixed_2k = {
            "1:1": "2048x2048",
            "4:3": "2304x1728",
            "3:4": "1728x2304",
            "16:9": "2560x1440",
            "9:16": "1440x2560",
            "21:9": "3024x1296",
        }
        return fixed_2k.get(ratio) or fixed_2k["1:1"]

    def _resolve_size(self, aspect_ratio: Any) -> str:
        """根据宽高比解析最终 size。

        规则:
            - size 由宽高比自动换算得到
            - 默认值为 2048x2048（等价于 1:1）
        """
        calculated = self._calc_size(self._normalize_param(aspect_ratio))
        return calculated or "2048x2048"

    def _normalize_n(self, value: Any) -> int | None:
        """规范化 n（生成数量）参数。

        规则:
            - 参数值为字符串 'variable' 时视为未传入
            - 若能转换为 int 且 > 0，则返回该值；否则忽略并返回 None
        """
        normalized = self._normalize_param(value)
        if normalized is None:
            return None
        try:
            n_int = int(float(normalized))
        except (TypeError, ValueError):
            return None
        if n_int <= 0:
            return None
        return n_int

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Seedream 图生图/图片编辑（/v1/images/edits，multipart/form-data）。

        参数:
            tool_parameters:
                - api_key: 鉴权用 API Key
                - image: 参考图（URL 字符串）
                - prompt: 编辑指令
                - n: 生成数量（可选）
                - watermark: 是否带水印（可选）
                - aspect_ratio: 宽高比（可选，用于换算 size）
        """
        host = "https://api.modellink.online"
        api_url = f"{host}/v1/images/edits"
        model = "doubao-seedream-4-5-251128"

        api_key = self._normalize_param(tool_parameters.get("api_key"))
        image = self._normalize_param(tool_parameters.get("image"))
        prompt = self._normalize_param(tool_parameters.get("prompt"))
        n = self._normalize_n(tool_parameters.get("n"))
        size = self._resolve_size(tool_parameters.get("aspect_ratio"))
        watermark = self._normalize_bool(tool_parameters.get("watermark"))

        if not api_key or not image or not prompt:
            raise ValueError("api_key、image 和 prompt 为必填参数")

        final_prompt = self._build_prompt(str(prompt), None, None)
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        data = {
            "model": model,
            "prompt": final_prompt,
            "size": size,
        }
        if n is not None:
            data["n"] = n
        if watermark is not None:
            data["watermark"] = watermark
        image_urls = [u.strip() for u in str(image).split(",") if u.strip()]
        if len(image_urls) > 14:
            raise ValueError("参考图最多支持 14 张，请使用英文逗号分隔")
        if len(image_urls) == 0:
            raise ValueError("image 为必填参数")
        files = [("image", (None, url)) for url in image_urls]

        logger.info(
            f"[Seedream ImageEdit] 请求编辑图片，model={model}, prompt_len={len(final_prompt)}"
        )

        try:
            response = requests.post(
                api_url, headers=headers, data=data, files=files, timeout=300
            )
            logger.info(f"[Seedream ImageEdit] 响应状态: {response.status_code}")

            if not response.ok:
                logger.error(f"[Seedream ImageEdit] 错误响应: {response.text}")
                response.raise_for_status()

            result = response.json()
            urls = [item.get("url") for item in (result.get("data") or []) if isinstance(item, dict)]

            response_result = {
                "success": True,
                "message": "Seedream 图生图生成成功",
                "data": {
                    "model": model,
                    "prompt": final_prompt,
                    "size": size,
                    "watermark": watermark,
                    "created": result.get("created"),
                    "images": urls,
                    "raw": result,
                },
            }
            yield self.create_json_message(response_result)

        except requests.exceptions.RequestException as e:
            logger.error(f"[Seedream ImageEdit] 网络异常: {str(e)}")
            raise Exception(str(e))
        except Exception as e:
            logger.error(f"[Seedream ImageEdit] 异常: {str(e)}")
            raise
