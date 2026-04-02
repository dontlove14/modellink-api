from collections.abc import Generator
from typing import Any
import json
import logging
import os
import time
from urllib.parse import urlparse
import mimetypes

import requests
from dify_plugin import Tool
from dify_plugin.config.logger_format import plugin_logger_handler
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class SeedreamImageGenerationsTool(Tool):
    def _normalize_param(self, value: Any) -> Any:
        """规范化工具参数值。"""
        if isinstance(value, str) and value == "variable":
            return None
        return value

    def _normalize_bool(self, value: Any) -> bool | None:
        """规范化布尔参数。"""
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

    def _normalize_int(self, value: Any) -> int | None:
        """规范化整数参数。"""
        normalized = self._normalize_param(value)
        if normalized is None:
            return None
        try:
            return int(float(normalized))
        except (TypeError, ValueError):
            return None

    def _normalize_float(self, value: Any) -> float | None:
        """规范化浮点参数。"""
        normalized = self._normalize_param(value)
        if normalized is None:
            return None
        try:
            return float(normalized)
        except (TypeError, ValueError):
            return None

    def _build_prompt(self, prompt: str) -> str:
        """规范化提示词。"""
        return prompt.strip()

    def _calc_size(self, aspect_ratio: str | None) -> str:
        """根据宽高比换算 size（\"WIDTHxHEIGHT\"）。"""
        ratio = (str(aspect_ratio).strip() if aspect_ratio else "1:1")
        fixed_2k = {
            "1:1": "2048x2048",
            "4:3": "2304x1728",
            "3:4": "1728x2304",
            "16:9": "2560x1440",
            "9:16": "1440x2560",
            "3:2": "2496x1664",
            "2:3": "1664x2496",
            "21:9": "3024x1296",
        }
        return fixed_2k.get(ratio) or fixed_2k["1:1"]

    def _parse_image_input(self, value: Any) -> str | list[str] | None:
        """解析 image 入参，支持单图或多图（URL/Base64），返回 string 或 list[string]。"""
        normalized = self._normalize_param(value)
        if normalized is None:
            return None
        if isinstance(normalized, list):
            items = [str(x).strip() for x in normalized if str(x).strip()]
            if not items:
                return None
            return items if len(items) > 1 else items[0]
        if isinstance(normalized, str):
            text = normalized.strip()
            if not text:
                return None
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    items = [str(x).strip() for x in parsed if str(x).strip()]
                    if not items:
                        return None
                    return items if len(items) > 1 else items[0]
            if "," in text:
                items = [x.strip() for x in text.split(",") if x.strip()]
                if not items:
                    return None
                return items if len(items) > 1 else items[0]
            return text
        return str(normalized)

    def _guess_file_name(self, url: str, mime_type: str, index: int) -> str:
        """根据 URL 与 MIME 生成文件名。"""
        parsed = urlparse(url)
        base = os.path.basename(parsed.path)
        base = base.split("?")[0].split("#")[0] if base else ""
        if base and "." in base:
            return base
        ext = mimetypes.guess_extension(mime_type) or ".jpg"
        timestamp = int(time.time())
        return f"seedream_{timestamp}_{index}{ext}"

    def _yield_file_from_url(self, url: str, index: int) -> ToolInvokeMessage:
        """下载图片 URL 并以文件消息返回。"""
        if hasattr(self, "create_file_message"):
            try:
                return self.create_file_message(url=url)
            except TypeError:
                try:
                    return self.create_file_message(url)
                except TypeError:
                    pass

        response = requests.get(url, timeout=300)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "image/jpeg")
        mime_type = content_type.split(";")[0].strip() if content_type else "image/jpeg"
        file_name = self._guess_file_name(url, mime_type, index)
        return self.create_blob_message(
            blob=response.content,
            meta={"file_name": file_name, "mime_type": mime_type},
        )

    def _get_response_text(self, response: requests.Response) -> str:
        """获取响应文本，尽量避免编码问题导致的异常。"""
        try:
            if response.encoding:
                return response.text or ""
        except Exception:
            pass
        try:
            return (response.content or b"").decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _parse_sse_json(self, response_text: str) -> dict[str, Any]:
        """解析 text/event-stream (SSE) 形式的 data 行为 JSON。"""
        last_obj: dict[str, Any] | None = None
        data_items: list[Any] = []
        for line in response_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("event:"):
                continue
            if not stripped.startswith("data:"):
                continue
            payload_text = stripped[len("data:") :].strip()
            if payload_text == "[DONE]":
                break
            try:
                obj = json.loads(payload_text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                last_obj = obj
                chunk_data = obj.get("data")
                if isinstance(chunk_data, list):
                    data_items.extend(chunk_data)
        if last_obj is None:
            raise json.JSONDecodeError("Invalid SSE JSON", response_text, 0)
        if data_items:
            last_obj["data"] = data_items
        return last_obj

    def _parse_generation_response(self, response: requests.Response) -> dict[str, Any]:
        """解析图片生成接口响应，兼容 JSON 与 SSE 两种输出。"""
        content_type = (response.headers.get("Content-Type") or "").lower()
        text = self._get_response_text(response)
        body_preview = text[:500].replace("\n", "\\n").replace("\r", "\\r")

        if not text.strip():
            raise Exception(
                f"接口返回空响应体，status={response.status_code}, content-type={content_type}"
            )

        if "text/event-stream" in content_type or text.lstrip().startswith("data:"):
            try:
                return self._parse_sse_json(text)
            except Exception:
                raise Exception(
                    f"接口返回非 JSON（疑似 SSE），无法解析。status={response.status_code}, content-type={content_type}, body={body_preview}"
                )

        try:
            return response.json()
        except Exception:
            try:
                return json.loads(text)
            except Exception:
                raise Exception(
                    f"接口返回非 JSON，无法解析。status={response.status_code}, content-type={content_type}, body={body_preview}"
                )

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Seedream 图片生成（官方 ImageGenerations 入参）。"""
        host = "https://api.modellink.online"
        api_url = f"{host}/v1/images/generations"
        default_model = "doubao-seedream-5-0-260128"

        api_key = self._normalize_param(tool_parameters.get("api_key"))
        model = self._normalize_param(tool_parameters.get("model")) or default_model
        prompt = self._normalize_param(tool_parameters.get("prompt"))
        image = self._parse_image_input(tool_parameters.get("image"))
        aspect_ratio = self._normalize_param(tool_parameters.get("aspect_ratio"))
        watermark = False
        seed = self._normalize_int(tool_parameters.get("seed"))
        guidance_scale = self._normalize_float(tool_parameters.get("guidance_scale"))
        optimize_prompt_mode = self._normalize_param(tool_parameters.get("optimize_prompt_mode"))
        sequential_image_generation = self._normalize_param(
            tool_parameters.get("sequential_image_generation")
        )
        sequential_image_generation_max_images = self._normalize_int(
            tool_parameters.get("sequential_image_generation_max_images")
        )

        if not api_key or not prompt:
            raise ValueError("api_key 和 prompt 为必填参数")
        if isinstance(image, list) and len(image) > 14:
            raise ValueError("参考图最多支持 14 张，请减少 image 数量")

        final_prompt = self._build_prompt(str(prompt))
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload: dict[str, Any] = {
            "model": model,
            "prompt": final_prompt,
            "response_format": "url",
            "stream": False,
        }
        if image is not None:
            payload["image"] = image
        if aspect_ratio is not None:
            payload["size"] = self._calc_size(str(aspect_ratio))
        if watermark is not None:
            payload["watermark"] = watermark
        if seed is not None:
            payload["seed"] = seed
        if guidance_scale is not None:
            payload["guidance_scale"] = guidance_scale
        if optimize_prompt_mode is not None:
            payload["optimize_prompt_options"] = {"mode": str(optimize_prompt_mode).strip()}
        if sequential_image_generation is not None:
            payload["sequential_image_generation"] = str(sequential_image_generation).strip()
        if (
            sequential_image_generation_max_images is not None
            and str(sequential_image_generation).strip() == "auto"
        ):
            payload["sequential_image_generation_options"] = {
                "max_images": sequential_image_generation_max_images
            }

        logger.info(
            f"[Seedream ImageGenerations] 请求生成图片，model={model}, prompt_len={len(final_prompt)}"
        )

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=300)
            logger.info(f"[Seedream ImageGenerations] 响应状态: {response.status_code}")

            if not response.ok:
                logger.error(f"[Seedream ImageGenerations] 错误响应: {response.text}")
                response.raise_for_status()

            result = self._parse_generation_response(response)
            data = result.get("data") or []
            urls: list[str] = []
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("url"), str) and item.get("url"):
                    urls.append(item["url"])

            if not urls:
                raise Exception("接口未返回可用的图片 url")

            for i, url in enumerate(urls, start=1):
                yield self._yield_file_from_url(url, i)

        except requests.exceptions.RequestException as e:
            logger.error(f"[Seedream ImageGenerations] 网络异常: {str(e)}")
            raise Exception(str(e))
        except Exception as e:
            logger.error(f"[Seedream ImageGenerations] 异常: {str(e)}")
            raise
