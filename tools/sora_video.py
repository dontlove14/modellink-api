from collections.abc import Generator
from typing import Any, Dict, List, Optional
import logging
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
import requests

# 导入 logging 和自定义处理器
from dify_plugin.config.logger_format import plugin_logger_handler

# 使用自定义处理器设置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

class SoraVideoTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Sora Video Generation API 封装"""
        try:
            # 提取参数
            # 使用固定的 API host
            host = "https://api.modellink.online"
            apiKey = tool_parameters.get('apiKey')
            model = tool_parameters.get('model', 'sora-2')
            prompt = tool_parameters.get('prompt')
            seconds = tool_parameters.get('seconds', '10')
            input_reference = tool_parameters.get('input_reference')
            size = tool_parameters.get('size')
            watermark = tool_parameters.get('watermark')
            private = tool_parameters.get('private')
            character_url = tool_parameters.get('character_url')
            character_timestamps = tool_parameters.get('character_timestamps')
            
            logger.info(f'[Sora Video] 开始生成视频，模型: {model}')
            
            # 构建请求数据
            request_data = {
                'model': model,
                'prompt': prompt,
                'seconds': seconds
            }
            
            # 添加可选参数
            if input_reference:
                request_data['input_reference'] = input_reference
            if size:
                request_data['size'] = size
            if watermark is not None:
                request_data['watermark'] = watermark
            if private is not None:
                request_data['private'] = private
            if character_url:
                request_data['character_url'] = character_url
            if character_timestamps:
                request_data['character_timestamps'] = character_timestamps
            
            logger.info(f'[Sora Video] 请求数据: {request_data}')
            
            # 发送请求
            api_url = f"{host}/v1/videos"
            headers = {
                'Authorization': f'Bearer {apiKey}',
                'Content-Type': 'multipart/form-data'
            }
            
            # 使用 requests.post 发送 multipart/form-data 请求
            response = requests.post(api_url, headers=headers, data=request_data, timeout=60)
            
            logger.info(f'[Sora Video] 响应状态: {response.status_code}')
            
            if not response.ok:
                error_text = response.text
                logger.error(f'[Sora Video] 错误响应: {error_text}')
                raise Exception(f'API 请求失败: {response.status_code} - {error_text}')
            
            result = response.json()
            logger.info(f'[Sora Video] 请求成功，任务 ID: {result.get("id")}')
            
            # 构建返回结果
            response_result = {
                'success': True,
                'message': '视频生成任务已提交',
                'data': {
                    'task_id': result.get('id'),
                    'model': result.get('model'),
                    'status': result.get('status'),
                    'created': result.get('created'),
                    'expires_at': result.get('expires_at'),
                    'task_type': result.get('task_type')
                }
            }
            
            yield self.create_json_message(response_result)
            
        except Exception as e:
            logger.error(f'[Sora Video] 异常: {str(e)}')
            yield self.create_json_message({
                'success': False,
                'message': str(e) or '视频生成失败',
                'error': str(e)
            })