from collections.abc import Generator
from typing import Any
import logging
import os
import re
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
    def _create_retry_session(self) -> requests.Session:
        """创建带重试策略的 HTTP Session

        说明:
            - 用于应对网络抖动、连接重置、服务端临时 5xx 等问题
            - multipart/form-data 的“断点续传上传”需要服务端协议支持，客户端侧仅做安全重试
        """
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        session.trust_env = False
        retry_strategy = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(["POST"]),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """Sora 视频生成工具

        参数:
            tool_parameters: 包含 apiKey、model、prompt 等参数

        行为:
            - 使用固定主机 https://api.modellink.online 提交生成任务
            - 成功返回标准化 JSON 消息

        异常:
            - 网络错误、HTTP 非 2xx、参数缺失等直接抛出异常
        """
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
            
            # 处理参数值为'variable'的情况
            def process_param(value):
                """处理 Dify 工作流变量引用的默认占位值。

                说明:
                    - 当表单默认设置为引用变量但未真正绑定时，系统会传入字符串 'variable'
                    - 为避免后续校验与请求序列化异常，这里将其转换为 None
                """
                if value == 'variable':
                    return None
                return value

            def to_form_field_value(value: Any) -> str:
                """将字段值转换为 multipart/form-data 可接受的字符串值。"""
                if isinstance(value, bool):
                    return 'true' if value else 'false'
                return str(value)

            def normalize_size(value: Any) -> Any:
                """归一化 size 参数，兼容比例与宽高两种写法。

                说明:
                    - 支持直接传入比例：16x9 / 9x16
                    - 若传入宽高（如 1024x1792），则按宽高关系归一为横屏 16x9 或竖屏 9x16
                """
                if value is None:
                    return None
                if not isinstance(value, str):
                    return value
                s = value.strip()
                if not s:
                    return None
                if s in {'16x9', '9x16'}:
                    return s
                match = re.match(r'^(\d+)\s*x\s*(\d+)$', s)
                if not match:
                    return s
                width = int(match.group(1))
                height = int(match.group(2))
                if width >= height:
                    return '16x9'
                return '9x16'

            def map_size_for_model(model_name: str | None, value: str | None) -> str | None:
                """根据模型将 size（比例）映射为接口所需的分辨率参数。"""
                if not value:
                    return None

                size_value = value.strip()
                if not size_value:
                    return None

                if model_name == 'sora-2':
                    if size_value not in {'9x16', '16x9'}:
                        logger.warning(f'[Sora Video] sora-2 模型仅支持 size=9x16/16x9，已自动调整为 16x9（原值: {size_value}）')
                        size_value = '16x9'
                    if size_value == '9x16':
                        return '720x1280'
                    return '1280x720'

                if model_name == 'sora-2-pro':
                    if size_value not in {'9x16', '16x9'}:
                        logger.warning(f'[Sora Video] sora-2-pro 模型仅支持 size=9x16/16x9，已自动调整为 16x9（原值: {size_value}）')
                        size_value = '16x9'
                    if size_value == '9x16':
                        return '1024x1792'
                    return '1792x1024'

                return size_value

            def normalize_input_reference(value: Any) -> str | None:
                """归一化 input_reference，仅支持单个文件或单个链接。

                说明:
                    - 支持传入 http/https 链接，作为 form-data 字段提交
                    - 支持传入本地文件路径或 file:// 路径，作为 form-data 文件上传
                    - 若传入列表/CSV/JSON 数组字符串，仅取第一个非空值（兼容历史用法）
                """
                if value is None:
                    return None
                if isinstance(value, list):
                    for x in value:
                        s = str(x).strip()
                        if s:
                            logger.warning('[Sora Video] input_reference 仅支持单个值，已自动取第一个非空值')
                            return s
                    return None
                if isinstance(value, str):
                    s = value.strip()
                    if not s:
                        return None
                    if s.startswith('[') and s.endswith(']'):
                        import json
                        try:
                            arr = json.loads(s)
                            if isinstance(arr, list):
                                for x in arr:
                                    t = str(x).strip()
                                    if t:
                                        logger.warning('[Sora Video] input_reference 仅支持单个值，已自动取数组第一个非空值')
                                        return t
                        except Exception:
                            pass
                    if ',' in s:
                        first = s.split(',', 1)[0].strip()
                        if first:
                            logger.warning('[Sora Video] input_reference 仅支持单个值，已自动取逗号分隔第一个值')
                            return first
                    return s
                return str(value).strip() or None
            
            apiKey = process_param(apiKey)
            model = process_param(model)
            prompt = process_param(prompt)
            seconds = process_param(seconds)
            input_reference = normalize_input_reference(process_param(input_reference))
            size = normalize_size(process_param(size))
            watermark = process_param(watermark)
            private = process_param(private)
            character_url = process_param(character_url)
            character_timestamps = process_param(character_timestamps)

            if not apiKey:
                raise ValueError('apiKey 为必填参数')
            if not prompt:
                raise ValueError('prompt 为必填参数')
            
            logger.info(f'[Sora Video] 开始生成视频，模型: {model}')
            
            # 模型参数兼容性检查
            # sora-2 支持的尺寸比例：9x16, 16x9
            # sora-2 支持的时长：10, 15
            # sora-2-pro 支持所有尺寸和时长
            if model == 'sora-2':
                # 验证seconds参数
                if seconds and seconds not in ['10', '15']:
                    # 如果时长不支持，使用默认值10
                    logger.warning(f'[Sora Video] sora-2 模型不支持时长 {seconds} 秒，已自动调整为 10 秒')
                    seconds = '10'

            mapped_size = map_size_for_model(model, size)
            
            # 构建请求数据
            request_data = {
                'model': model,
                'prompt': prompt,
                'seconds': seconds
            }
            
            # 添加可选参数
            if mapped_size:
                request_data['size'] = mapped_size
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
                'Authorization': f'Bearer {apiKey}'
                # 不手动设置Content-Type，requests会自动处理multipart/form-data
            }
            
            # 使用 requests.post 发送 multipart/form-data 请求
            # 对于multipart/form-data，使用files参数发送
            # 将request_data转换为files格式，每个字段作为一个元组
            files: list[tuple[str, tuple[Any, Any, Any] | tuple[Any, Any]]] = [
                (k, (None, to_form_field_value(v))) for k, v in request_data.items() if v is not None
            ]

            opened_files: list[Any] = []
            if input_reference:
                ref = input_reference
                if ref.startswith('http://') or ref.startswith('https://'):
                    files.append(('input_reference', (None, ref)))
                else:
                    path = ref
                    if ref.startswith('file://'):
                        path = ref[len('file://'):]
                    if os.path.isfile(path):
                        f = open(path, 'rb')
                        opened_files.append(f)
                        filename = os.path.basename(path) or 'input_reference'
                        files.append(('input_reference', (filename, f, 'application/octet-stream')))
                    else:
                        files.append(('input_reference', (None, ref)))

            session = self._create_retry_session()
            try:
                response = session.post(api_url, headers=headers, files=files, timeout=(10, 120))
            finally:
                for f in opened_files:
                    try:
                        f.close()
                    except Exception:
                        pass
            
            logger.info(f'[Sora Video] 响应状态: {response.status_code}')
            
            if not response.ok:
                error_text = response.text
                logger.error(f'[Sora Video] 错误响应: {error_text}')
                response.raise_for_status()
            
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
            
        except requests.exceptions.RequestException as e:
            logger.error(f'[Sora Video] 网络异常: {str(e)}')
            raise Exception(str(e))
        except Exception as e:
            logger.error(f'[Sora Video] 异常: {str(e)}')
            raise
