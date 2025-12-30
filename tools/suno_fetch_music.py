from collections.abc import Generator
from typing import Any, Dict
import logging
import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.config.logger_format import plugin_logger_handler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

class SunoFetchMusicTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """查询 Suno 音乐生成结果，返回任务状态与生成内容"""
        try:
            host = "https://api.modellink.online"
            apiKey = tool_parameters.get('apiKey')
            task_id = tool_parameters.get('task_id')

            if not task_id:
                raise Exception('task_id 为必填参数')

            url = f"{host}/suno/fetch/{task_id}"
            headers = {
                'Authorization': f'Bearer {apiKey}'
            }
            resp = requests.get(url, headers=headers, timeout=120)
            logger.info(f'[Suno Fetch] 响应状态: {resp.status_code}')

            if not resp.ok:
                err = resp.text
                logger.error(f'[Suno Fetch] 错误响应: {err}')
                yield self.create_json_message({'success': False, 'message': err, 'error': err})
                return

            try:
                data = resp.json()
            except Exception:
                data = {'raw': resp.text}

            yield self.create_json_message({'success': True, 'message': '查询成功', 'data': data})
        except Exception as e:
            logger.error(f'[Suno Fetch] 异常: {str(e)}')
            yield self.create_json_message({'success': False, 'message': str(e) or '查询失败', 'error': str(e)})

