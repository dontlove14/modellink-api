from collections.abc import Generator
from typing import Any, Dict
import json
import logging
import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.config.logger_format import plugin_logger_handler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

class SunoSubmitMusicTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """提交 Suno 音乐生成任务，支持新歌与扩展模式。非流式返回结果，统一错误处理并规整空参数。"""
        try:
            host = "https://api.modellink.online"
            apiKey = tool_parameters.get('apiKey')
            prompt = tool_parameters.get('prompt')
            mv = tool_parameters.get('mv')
            title = tool_parameters.get('title')

            def _norm(v: Any) -> Any:
                return None if v in (None, '', 'variable') else v

            tags = _norm(tool_parameters.get('tags'))
            task = _norm(tool_parameters.get('task'))
            continue_at = _norm(tool_parameters.get('continue_at'))
            continue_clip_id = _norm(tool_parameters.get('continue_clip_id'))

            if not apiKey:
                raise Exception('缺少 apiKey')
            if not prompt or not mv or not title:
                raise Exception('prompt、mv、title 为必填参数')

            body: Dict[str, Any] = {
                'prompt': prompt,
                'mv': mv,
                'title': title
            }
            if tags is not None:
                body['tags'] = tags
            if task is not None:
                body['task'] = task
            if continue_at is not None:
                body['continue_at'] = continue_at
            if continue_clip_id is not None:
                body['continue_clip_id'] = continue_clip_id

            logger.info(f'[Suno Submit] 请求体: {json.dumps(body, ensure_ascii=False)}')

            url = f"{host}/suno/submit/music"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {apiKey}'
            }
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=120)
            except requests.exceptions.RequestException as e:
                logger.error(f'[Suno Submit] 网络异常: {str(e)}')
                yield self.create_json_message({'success': False, 'message': '网络异常，无法连接到 Model Link API', 'error': str(e)})
                return

            logger.info(f'[Suno Submit] 响应状态: {resp.status_code}')

            if not resp.ok:
                err = resp.text
                logger.error(f'[Suno Submit] 错误响应: {err}')
                yield self.create_json_message({'success': False, 'message': err, 'error': err})
                return

            try:
                data = resp.json()
            except Exception:
                data = {'raw': resp.text}

            yield self.create_json_message({'success': True, 'message': '任务提交成功', 'data': data})
        except Exception as e:
            logger.error(f'[Suno Submit] 异常: {str(e)}')
            yield self.create_json_message({'success': False, 'message': str(e) or '任务提交失败', 'error': str(e)})
