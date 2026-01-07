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
        """Sora 视频查询工具

        参数:
            tool_parameters: 包含 apiKey 与 id 的参数字典

        行为:
            - 向固定主机 https://api.modellink.online 查询视频信息
            - 成功时返回标准化 JSON 消息

        异常:
            - 当发生网络错误（超时、DNS 解析失败、连接错误等）时，直接抛出异常
            - 当响应非 2xx 时抛出 HTTPError
            - 当参数缺失或非法时抛出 ValueError
        """

        # 使用固定的 API host
        host = "https://api.modellink.online"

        # 提取并规范参数（将 "variable" 视为缺省）
        apiKey = tool_parameters.get('apiKey')
        video_id = tool_parameters.get('id')
        if isinstance(apiKey, str) and apiKey == 'variable':
            apiKey = None
        if isinstance(video_id, str) and video_id == 'variable':
            video_id = None

        if not apiKey or not video_id:
            raise ValueError('apiKey 和 id 为必填参数')

        logger.info(f'[Sora Video Query] 开始查询视频，ID: {video_id}')

        try:
            # 发送请求
            api_url = f"{host}/v1/videos/{video_id}"
            headers = {
                'Authorization': f'Bearer {apiKey}',
                'Content-Type': 'application/json'
            }

            response = requests.get(api_url, headers=headers, timeout=120)

            logger.info(f'[Sora Video Query] 响应状态: {response.status_code}')

            if not response.ok:
                error_text = response.text
                logger.error(f'[Sora Video Query] 错误响应: {error_text}')
                response.raise_for_status()

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

        except requests.exceptions.RequestException as e:
            logger.error(f'[Sora Video Query] 网络异常: {str(e)}')
            raise Exception(str(e))
        except Exception as e:
            logger.error(f'[Sora Video Query] 异常: {str(e)}')
            raise
