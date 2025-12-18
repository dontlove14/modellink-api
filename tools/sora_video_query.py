from collections.abc import Generator
from typing import Any
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

class SoraVideoQueryTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Sora Video Query API 封装"""
        try:
            # 提取参数
            # 使用固定的 API host
            host = "https://api.modellink.online"
            apiKey = tool_parameters.get('apiKey')
            video_id = tool_parameters.get('id')
            
            logger.info(f'[Sora Video Query] 开始查询视频，ID: {video_id}')
            
            # 发送请求
            api_url = f"{host}/v1/videos/{video_id}"
            headers = {
                'Authorization': f'Bearer {apiKey}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(api_url, headers=headers, timeout=60)
            
            logger.info(f'[Sora Video Query] 响应状态: {response.status_code}')
            
            if not response.ok:
                error_text = response.text
                logger.error(f'[Sora Video Query] 错误响应: {error_text}')
                raise Exception(f'API 请求失败: {response.status_code} - {error_text}')
            
            result = response.json()
            logger.info(f'[Sora Video Query] 请求成功，视频状态: {result.get("status")}')
            
            # 构建返回结果
            response_result = {
                'success': True,
                'message': '视频查询成功',
                'data': {
                    'id': result.get('id'),
                    'model': result.get('model'),
                    'status': result.get('status'),
                    'progress': result.get('progress'),
                    'seconds': result.get('seconds'),
                    'size': result.get('size'),
                    'created_at': result.get('created_at'),
                    'completed_at': result.get('completed_at'),
                    'url': result.get('url'),
                    'video_url': result.get('video_url'),
                    'result_url': result.get('result_url')
                }
            }
            
            yield self.create_json_message(response_result)
            
        except Exception as e:
            logger.error(f'[Sora Video Query] 异常: {str(e)}')
            yield self.create_json_message({
                'success': False,
                'message': str(e) or '视频查询失败',
                'error': str(e)
            })