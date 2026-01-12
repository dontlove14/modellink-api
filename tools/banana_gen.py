from collections.abc import Generator
from typing import Any, Dict, List
import base64
import json
import logging
import os
import time
from datetime import datetime
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
import requests
import random
import string

# 导入 logging 和自定义处理器
from dify_plugin.config.logger_format import plugin_logger_handler

# 使用自定义处理器设置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

class BananaGenTool(Tool):
    def _normalize_param(self, value: Any) -> Any:
        """将字符串'variable'规范化为None"""
        if isinstance(value, str) and value.strip().lower() == 'variable':
            return None
        return value
    def _download_image_as_base64(self, url: str) -> Dict[str, str]:
        """从 URL 断点续传下载图片并转换为 base64

        说明:
            - 优先使用 HTTP Range 请求进行断点续传
            - 若源站不支持 Range，则自动回退为普通下载
            - 在网络中断/超时场景下，会基于已下载字节数继续请求剩余部分
        """
        try:
            session = requests.Session()
            session.trust_env = False

            downloaded = bytearray()
            downloaded_size = 0
            total_size = None
            content_type = 'image/png'

            max_attempts = 5
            attempt = 0
            chunk_size = 256 * 1024

            while True:
                headers: Dict[str, str] = {}
                if downloaded_size > 0:
                    headers['Range'] = f'bytes={downloaded_size}-'

                try:
                    response = session.get(url, headers=headers, timeout=(10, 30), stream=True)
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise Exception(f'下载中断且重试次数已达上限: {str(e)}')
                    time.sleep(min(8, 2 ** attempt))
                    continue

                try:
                    if response.status_code not in (200, 206):
                        response.raise_for_status()

                    response_content_type = response.headers.get('content-type')
                    if response_content_type:
                        content_type = response_content_type.split(';', 1)[0].strip() or content_type

                    if response.status_code == 200 and downloaded_size > 0:
                        downloaded = bytearray()
                        downloaded_size = 0
                        total_size = None

                    if total_size is None:
                        if response.status_code == 206:
                            content_range = response.headers.get('Content-Range') or response.headers.get('content-range')
                            if content_range and '/' in content_range:
                                total_part = content_range.split('/', 1)[1].strip()
                                if total_part.isdigit():
                                    total_size = int(total_part)
                        else:
                            content_length = response.headers.get('Content-Length') or response.headers.get('content-length')
                            if content_length and str(content_length).isdigit():
                                total_size = int(content_length)

                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        downloaded.extend(chunk)
                        downloaded_size += len(chunk)

                    if total_size is not None:
                        if downloaded_size >= total_size:
                            break
                        attempt += 1
                        if attempt >= max_attempts:
                            raise Exception('下载未完成且重试次数已达上限')
                        time.sleep(min(8, 2 ** attempt))
                        continue

                    break
                finally:
                    response.close()

            base64_data = base64.b64encode(bytes(downloaded)).decode('utf-8')
            return {'data': base64_data, 'mimeType': content_type}
        except Exception as e:
            raise Exception(f'下载参考图片失败: {str(e)}')
    
    def _get_file_extension_from_mime_type(self, mime_type: str) -> str:
        """从 MIME 类型获取文件扩展名"""
        mime_map = {
            'image/png': 'png',
            'image/jpeg': 'jpg',
            'image/jpg': 'jpg',
            'image/gif': 'gif',
            'image/webp': 'webp'
        }
        return mime_map.get(mime_type, 'png')
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """调用 Nano Banana 图生生成 API

        参数:
            tool_parameters: 包含 api_key、model、prompt、reference_image_urls 等参数

        行为:
            - 使用 https://api.modellink.online 的 Gemini 图像生成接口

        异常:
            - 网络错误、HTTP 非 2xx、解析失败等直接抛出异常
        """
        try:
            # 使用固定的 API host
            host = "https://api.modellink.online"
            api_key = self._normalize_param(tool_parameters.get('api_key'))
            model = self._normalize_param(tool_parameters.get('model'))
            prompt = self._normalize_param(tool_parameters.get('prompt'))
            reference_image_urls = self._normalize_param(tool_parameters.get('reference_image_urls', ''))
            ratio = self._normalize_param(tool_parameters.get('ratio'))
            size = self._normalize_param(tool_parameters.get('size'))

            if not api_key:
                raise Exception('缺少 API Key')
            if not model:
                raise Exception('缺少模型名称')
            
            # 使用插件内置的日志记录
            logger.info(f'[BananaGen] 开始生成图像，模型: {model}, 提示词: {prompt}')
            
            # 构建 API 端点
            endpoint = f"{host}/v1beta/models/{model}:generateContent"
            
            # 构建请求的 parts
            parts = []
            
            # 添加文本提示词
            if prompt:
                parts.append({'text': prompt})
            
            # 处理参考图片（最多14张）
            urls_to_process = []
            
            # 处理不同类型的 reference_image_urls 参数
            if reference_image_urls:
                if isinstance(reference_image_urls, str):
                    # 旧格式：CSV 字符串
                    urls_to_process = [url.strip() for url in reference_image_urls.split(',') if url.strip()]
                elif isinstance(reference_image_urls, list):
                    # 新格式：文件对象列表
                    for item in reference_image_urls:
                        if isinstance(item, dict):
                            # 从文件对象中提取 URL
                            image_url = item.get('url') or item.get('remote_url')
                            if image_url:
                                urls_to_process.append(image_url)
                elif isinstance(reference_image_urls, dict):
                    # 单文件对象
                    image_url = reference_image_urls.get('url') or reference_image_urls.get('remote_url')
                    if image_url:
                        urls_to_process = [image_url]
            
            max_images = min(len(urls_to_process), 14)
            if max_images > 0:
                logger.info(f'[BananaGen] 处理 {max_images} 张参考图片')
                
                for i in range(max_images):
                    image_url = urls_to_process[i]
                    try:
                        # 确保 URL 是完整的，添加 API host 前缀
                        if not image_url.startswith('http'):
                            # 处理相对路径，添加完整的 API host
                            if image_url.startswith('/'):
                                image_url = f"https://api.modellink.online{image_url}"
                            else:
                                image_url = f"https://api.modellink.online/{image_url}"
                        
                        # 下载图片并转换为 base64
                        image_data = self._download_image_as_base64(image_url)
                        
                        parts.append({
                            'inlineData': {
                                'mimeType': image_data['mimeType'],
                                'data': image_data['data']
                            }
                        })
                        
                        logger.info(f'[BananaGen] 参考图片 {i + 1} 处理完成')
                    except Exception as e:
                        logger.warning(f'[BananaGen] 参考图片 {i + 1} 处理失败: {str(e)}')
                        # 继续处理其他图片，不中断流程
            
            # 构建 generationConfig
            generation_config = {
                'responseModalities': ['IMAGE']  # 只返回图片，不返回文本
            }
            
            # 添加 imageConfig
            image_config = {}
            
            if ratio:
                image_config['aspectRatio'] = ratio
            
            # 只有 gemini-3-pro-image-preview 支持 imageSize 参数
            if size and model == 'gemini-3-pro-image-preview':
                image_config['imageSize'] = size  # 1K, 2K, 4K
            
            if image_config:
                generation_config['imageConfig'] = image_config
            
            # 构建请求体
            request_body = {
                'contents': [{
                    'parts': parts
                }],
                'generationConfig': generation_config
            }
            
            logger.info(f'[BananaGen] 发送请求到: {endpoint}')
            logger.debug(f'[BananaGen] 请求体: {json.dumps(request_body, indent=2)}')
            
            # 发送 API 请求
            headers = {
                'Content-Type': 'application/json',
                'x-goog-api-key': api_key,
                'Connection': 'close'
            }
            
            # 使用 Session 和重试机制来处理网络不稳定的情况
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            session = requests.Session()
            session.trust_env = False
            retry_strategy = Retry(
                total=5,
                connect=5,
                read=5,
                status=5,
                backoff_factor=1,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=frozenset(["POST"]),
                respect_retry_after_header=True
            )
            adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
            session.mount("https://", adapter)
            session.mount("http://", adapter)

            # 使用流式读取来处理大响应（图片 base64 数据很大）
            try:
                response = session.post(
                    endpoint,
                    headers=headers,
                    json=request_body,
                    timeout=(30, 1200),
                    stream=True
                )
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                logger.warning(f'[BananaGen] 请求连接超时或中断，进行一次重试: {str(e)}')
                response = session.post(
                    endpoint,
                    headers=headers,
                    json=request_body,
                    timeout=(30, 1500),
                    stream=True
                )

            if not response.ok:
                error_message = f'HTTP {response.status_code}: {response.reason}'
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        if isinstance(error_data['error'], str):
                            error_message = error_data['error']
                        elif isinstance(error_data['error'], dict) and 'message' in error_data['error']:
                            error_message = error_data['error']['message']
                        else:
                            error_message = json.dumps(error_data['error'])
                    elif 'message' in error_data:
                        error_message = error_data['message']
                except Exception:
                    # 无法解析 JSON，使用默认错误信息
                    pass
                raise Exception(f'API 请求失败: {error_message}')

            # 流式分块读取响应内容，避免 IncompleteRead 错误
            chunks = []
            try:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        chunks.append(chunk)
                response_content = b''.join(chunks)
                result = json.loads(response_content.decode('utf-8'))
            except Exception as e:
                logger.error(f'[BananaGen] 读取响应失败: {str(e)}')
                raise Exception(f'读取 API 响应失败: {str(e)}')
            logger.debug(f'[BananaGen] API 响应: {json.dumps(result, indent=2)}')
            
            # 提取所有生成的图片数据（支持多张图片）
            images = []
            
            if 'candidates' in result and result['candidates']:
                candidate = result['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    for part in candidate['content']['parts']:
                        if 'inlineData' in part and 'data' in part['inlineData']:
                            images.append({
                                'data': part['inlineData']['data'],
                                'mimeType': part['inlineData'].get('mimeType', 'image/png')
                            })
            
            if not images:
                raise Exception('未能从响应中提取图片数据')
            
            logger.info(f'[BananaGen] 成功提取 {len(images)} 张图片，开始处理返回')
            
            # 直接使用 Dify 的 create_blob_message 返回图片，避免页面卡顿和外部依赖
            for i, image in enumerate(images):
                try:
                    # 解码 base64 数据为二进制
                    image_bytes = base64.b64decode(image['data'])
                    
                    # 生成随机文件名
                    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
                    file_extension = self._get_file_extension_from_mime_type(image['mimeType'])
                    file_name = f"banana_gen_{int(datetime.now().timestamp())}_{i+1}_{random_suffix}.{file_extension}"
                    
                    logger.info(f'[BananaGen] 返回第 {i+1}/{len(images)} 张图片: {file_name}, 大小: {len(image_bytes)} bytes')
                    
                    # 使用 Dify 的 create_blob_message 直接返回图片二进制数据
                    yield self.create_blob_message(
                        blob=image_bytes,
                        meta={
                            'file_name': file_name,
                            'mime_type': image['mimeType']
                        }
                    )
                    
                except Exception as e:
                    logger.error(f'[BananaGen] 处理第 {i+1} 张图片失败: {str(e)}')
                    continue
            
            # 如果需要，也可以返回一个总结 JSON 消息
            logger.info(f'[BananaGen] 图片处理完成，共返回 {len(images)} 张图片')
            
        except requests.exceptions.RequestException as e:
            logger.error(f'[BananaGen] 网络异常: {str(e)}')
            raise Exception(str(e))
        except Exception as e:
            logger.error(f'[BananaGen] 生成图像失败: {str(e)}')
            raise
