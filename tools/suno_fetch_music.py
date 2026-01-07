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
        """查询 Suno 音乐生成结果

        参数:
            tool_parameters: 包含 apiKey 与 task_id 的参数字典

        行为:
            - 使用 https://api.modellink.online 查询任务状态

        异常:
            - 网络错误、HTTP 非 2xx、参数缺失直接抛出异常
        """
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
                resp.raise_for_status()

            try:
                data = resp.json()
            except Exception:
                data = {'raw': resp.text}

            yield self.create_json_message({'success': True, 'message': '查询成功', 'data': data})
        except requests.exceptions.RequestException as e:
            logger.error(f'[Suno Fetch] 网络异常: {str(e)}')
            raise Exception(str(e))
        except Exception as e:
            logger.error(f'[Suno Fetch] 异常: {str(e)}')
            raise
