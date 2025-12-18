from collections.abc import Generator
from typing import Any, Dict, List
import base64
import json
import logging
import os
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
    def _download_image_as_base64(self, url: str) -> Dict[str, str]:
        """从 URL 下载图片并转换为 base64"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # 确定 MIME 类型
            content_type = response.headers.get('content-type', 'image/png')
            
            # 转换为 base64
            base64_data = base64.b64encode(response.content).decode('utf-8')
            
            return {
                'data': base64_data,
                'mimeType': content_type
            }
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
        """调用 Nano Banana 图生生成 API"""
        try:
            # 使用固定的 API host
            host = "https://api.modellink.online"
            api_key = tool_parameters.get('api_key')
            model = tool_parameters.get('model')
            prompt = tool_parameters.get('prompt')
            reference_image_url = tool_parameters.get('reference_image_url', [])
            ratio = tool_parameters.get('ratio')
            size = tool_parameters.get('size')
            
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
            if reference_image_url and isinstance(reference_image_url, list):
                max_images = min(len(reference_image_url), 14)
                logger.info(f'[BananaGen] 处理 {max_images} 张参考图片')
                
                for i in range(max_images):
                    image_url = reference_image_url[i]
                    try:
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
                'x-goog-api-key': api_key
            }
            
            response = requests.post(endpoint, headers=headers, json=request_body, timeout=60)
            
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
            
            result = response.json()
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
            
        except Exception as e:
            logger.error(f'[BananaGen] 生成图像失败: {str(e)}')
            yield self.create_json_message({
                'success': False,
                'error': str(e)
            })
