from collections.abc import Generator
from typing import Any, Dict
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

class KlingusImage2VideoTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Klingus Image to Video Generation API 封装"""
        try:
            # 提取参数
            # 使用固定的 API host
            host = "https://api.modellink.online"
            api_key = tool_parameters.get('api_key')
            model_name = tool_parameters.get('model_name', 'kling-v1')
            prompt = tool_parameters.get('prompt')
            negative_prompt = tool_parameters.get('negative_prompt')
            image = tool_parameters.get('image')
            image_tail = tool_parameters.get('image_tail')
            cfg_scale = tool_parameters.get('cfg_scale')
            mode = tool_parameters.get('mode', 'std')
            aspect_ratio = tool_parameters.get('aspect_ratio')
            duration = tool_parameters.get('duration', '5')
            callback_url = tool_parameters.get('callback_url')
            external_task_id = tool_parameters.get('external_task_id')
            enable_audio = tool_parameters.get('enable_audio', True)
            
            # 处理参数值为'variable'的情况
            def process_param(value):
                if value == 'variable':
                    return None
                return value
            
            api_key = process_param(api_key)
            model_name = process_param(model_name)
            prompt = process_param(prompt)
            negative_prompt = process_param(negative_prompt)
            image = process_param(image)
            image_tail = process_param(image_tail)
            cfg_scale = process_param(cfg_scale)
            mode = process_param(mode)
            aspect_ratio = process_param(aspect_ratio)
            duration = process_param(duration)
            callback_url = process_param(callback_url)
            external_task_id = process_param(external_task_id)
            enable_audio = process_param(enable_audio)
            
            logger.info(f'[Klingus Image2Video] 开始生成视频，模型: {model_name}')
            
            # 构建请求数据
            request_data = {
                'model_name': model_name,
                'prompt': prompt,
                'image': image,
                'image_tail': image_tail,
                'mode': mode,
                'duration': duration,
                'enable_audio': enable_audio
            }
            
            # 添加可选参数
            if negative_prompt:
                request_data['negative_prompt'] = negative_prompt
            if cfg_scale is not None:
                request_data['cfg_scale'] = cfg_scale
            if aspect_ratio:
                request_data['aspect_ratio'] = aspect_ratio
            if callback_url:
                request_data['callback_url'] = callback_url
            if external_task_id:
                request_data['external_task_id'] = external_task_id
            
            logger.info(f'[Klingus Image2Video] 请求数据: {request_data}')
            
            # 发送请求
            api_url = f"{host}/klingus/v1/videos/image2video"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            
            response = requests.post(api_url, headers=headers, json=request_data, timeout=60)
            
            logger.info(f'[Klingus Image2Video] 响应状态: {response.status_code}')
            
            if not response.ok:
                error_text = response.text
                logger.error(f'[Klingus Image2Video] 错误响应: {error_text}')
                raise Exception(f'API 请求失败: {response.status_code} - {error_text}')
            
            result = response.json()
            logger.info(f'[Klingus Image2Video] 请求成功，任务 ID: {result.get("data", {}).get("task_id")}')
            
            # 构建返回结果
            response_result = {
                'success': True,
                'message': '视频生成任务已提交',
                'data': result.get('data', {})
            }
            
            yield self.create_json_message(response_result)
            
        except Exception as e:
            logger.error(f'[Klingus Image2Video] 异常: {str(e)}')
            yield self.create_json_message({
                'success': False,
                'message': str(e) or '视频生成任务提交失败',
                'error': str(e)
            })
