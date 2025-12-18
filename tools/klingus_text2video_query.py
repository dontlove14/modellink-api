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

class KlingusText2VideoQueryTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Klingus Text to Video Query API 封装"""
        try:
            # 提取参数
            # 使用固定的 API host
            host = "https://api.modellink.online"
            api_key = tool_parameters.get('api_key')
            task_id = tool_parameters.get('task_id')
            
            # 处理参数值为'variable'的情况
            def process_param(value):
                if value == 'variable':
                    return None
                return value
            
            api_key = process_param(api_key)
            task_id = process_param(task_id)
            
            logger.info(f'[Klingus Text2Video Query] 查询任务，任务 ID: {task_id}')
            
            # 构建请求
            api_url = f"{host}/klingus/v1/videos/text2video/{task_id}"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            
            # 发送请求
            response = requests.get(api_url, headers=headers, timeout=60)
            
            logger.info(f'[Klingus Text2Video Query] 响应状态: {response.status_code}')
            
            # 获取响应内容
            response_content = response.text
            logger.debug(f'[Klingus Text2Video Query] 响应内容: {response_content[:500]}')  # 只记录前500个字符，避免日志过大
            
            if not response.ok:
                logger.error(f'[Klingus Text2Video Query] 错误响应: {response_content}')
                raise Exception(f'API 请求失败: {response.status_code} - {response_content}')
            
            try:
                result = response.json()
                logger.info(f'[Klingus Text2Video Query] 查询成功，任务状态: {result.get("data", {}).get("task_status")}')
            except ValueError as e:
                logger.error(f'[Klingus Text2Video Query] JSON 解析失败: {e}，响应内容: {response_content}')
                raise Exception(f'JSON 解析失败: {e}，响应内容: {response_content}')
            
            # 构建返回结果
            response_result = {
                'success': True,
                'message': '任务查询成功',
                'data': result.get('data', {})
            }
            
            yield self.create_json_message(response_result)
            
        except Exception as e:
            logger.error(f'[Klingus Text2Video Query] 异常: {str(e)}')
            yield self.create_json_message({
                'success': False,
                'message': str(e) or '任务查询失败',
                'error': str(e)
            })
