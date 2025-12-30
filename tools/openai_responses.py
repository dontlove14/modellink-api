from collections.abc import Generator
from typing import Any, Dict, Optional, List, Union
import json
import logging
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
import requests
from urllib.parse import urlparse

from dify_plugin.config.logger_format import plugin_logger_handler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)

class OpenAIResponsesTool(Tool):
    def _sanitize_url(self, url: str) -> str:
        """清理并校验 URL 字符串，去除多余空白和包裹字符"""
        if not isinstance(url, str):
            raise ValueError('URL 必须为字符串')
        cleaned = url.strip()
        if cleaned.startswith('`') and cleaned.endswith('`'):
            cleaned = cleaned[1:-1].strip()
        if cleaned.endswith('\\'):
            cleaned = cleaned[:-1]
        parsed = urlparse(cleaned)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError('无效的 URL')
        return cleaned

    def _normalize_content_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """规范化单个内容项"""
        itype = item.get('type')
        if itype == 'input_text':
            return {
                'type': 'input_text',
                'text': str(item.get('text', ''))
            }
        elif itype == 'input_image':
            image_url = item.get('image_url')
            sanitized = self._sanitize_url(str(image_url))
            return {
                'type': 'input_image',
                'image_url': sanitized
            }
        elif itype == 'input_file':
            file_url = item.get('file_url')
            file_id = item.get('file_id')
            result: Dict[str, Any] = {'type': 'input_file'}
            if file_url:
                result['file_url'] = self._sanitize_url(str(file_url))
            elif file_id:
                result['file_id'] = str(file_id)
            return result
        else:
            return item

    def _normalize_message_content(self, content: Any) -> Union[str, List[Dict[str, Any]]]:
        """规范化消息内容，确保 input_text/input_image/input_file 结构有效"""
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            text = content.get('text') or content.get('content')
            if text is not None:
                return [{'type': 'input_text', 'text': str(text)}]
            return [self._normalize_content_item(content)]
        if isinstance(content, list):
            normalized: List[Dict[str, Any]] = []
            for item in content:
                if isinstance(item, dict):
                    normalized.append(self._normalize_content_item(item))
                else:
                    normalized.append({'type': 'input_text', 'text': str(item)})
            return normalized
        return str(content)

    def _build_input(self, messages: List[Dict[str, Any]], prompt: Optional[str]) -> Union[str, List[Dict[str, Any]]]:
        """
        构建符合 Responses API 的 input 参数
        - 简单字符串: "input": "Tell me a story"
        - 消息数组: "input": [{"role": "user", "content": [...]}]
        """
        if prompt and (not messages or len(messages) == 0):
            return prompt

        input_messages: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content')
            if content:
                formatted_content = self._normalize_message_content(content)
                input_messages.append({
                    'role': role,
                    'content': formatted_content
                })

        return input_messages if input_messages else prompt or ""
    def _stream_responses(self, api_url: str, headers: Dict[str, Any], request_body: Dict[str, Any]) -> Dict[str, Any]:
        """
        以流式方式调用 Responses 接口，解析 SSE 事件并聚合 output_text 文本

        OpenAI Responses API 流式事件类型:
        - response.created: 响应创建
        - response.in_progress: 响应进行中
        - response.output_item.added: 输出项添加
        - response.content_part.added: 内容部分添加
        - response.output_text.delta: 文本增量 (主要文本内容)
        - response.output_text.done: 文本完成
        - response.content_part.done: 内容部分完成
        - response.output_item.done: 输出项完成
        - response.completed: 响应完成
        - response.failed: 响应失败
        """
        accumulated_text = ""
        finish_reason: Optional[str] = None
        model_id: Optional[str] = None
        response_id: Optional[str] = None
        created_ts: Optional[int] = None
        error_info: Optional[Dict[str, Any]] = None

        response = requests.post(api_url, headers=headers, json=request_body, timeout=600, stream=True)

        logger.info(f'[OpenAI Responses] 响应状态: {response.status_code}')
        if not response.ok:
            error_text = response.text
            logger.error(f'[OpenAI Responses] 错误响应: {error_text}')
            raise Exception(f'API 请求失败: {response.status_code} - {error_text}')

        content_type = response.headers.get('Content-Type', '') or response.headers.get('content-type', '')
        charset = 'utf-8'
        if 'charset=' in content_type:
            try:
                charset = content_type.split('charset=')[-1].split(';')[0].strip()
            except Exception:
                charset = 'utf-8'
        if not response.encoding:
            response.encoding = charset

        for raw_line in response.iter_lines(decode_unicode=False):
            if raw_line is None:
                continue
            try:
                line = raw_line.decode(charset, errors='replace').lstrip('\ufeff').strip()
            except Exception:
                line = raw_line.decode('utf-8', errors='replace').lstrip('\ufeff').strip()
            if not line:
                continue

            # 处理 SSE 事件格式: "event: xxx" 和 "data: xxx"
            if line.startswith('event:'):
                continue  # 事件类型行，跳过，数据在 data 行

            if line.startswith('data:'):
                payload = line[len('data:'):].strip()
                if payload == '[DONE]':
                    break
                try:
                    event = json.loads(payload)
                except Exception as e:
                    logger.warning(f'[OpenAI Responses] JSON 解析失败: {e}, payload: {payload[:200]}')
                    continue

                etype = event.get('type', '')
                logger.info(f'[OpenAI Responses] 事件类型: {etype}')

                # 提取响应元数据 (从 response.created, response.in_progress 等事件)
                if isinstance(event.get('response'), dict):
                    resp = event['response']
                    model_id = resp.get('model') or model_id
                    response_id = resp.get('id') or response_id
                    created_ts = resp.get('created_at') or created_ts
                    # 检查错误信息
                    if resp.get('error'):
                        error_info = resp['error']

                # 处理文本增量事件: response.output_text.delta
                if etype == 'response.output_text.delta':
                    delta = event.get('delta', '')
                    if delta:
                        accumulated_text += str(delta)
                        logger.info(f'[OpenAI Responses] 收到 delta，当前累计长度: {len(accumulated_text)}')

                # 处理响应完成事件: response.completed
                elif etype == 'response.completed':
                    finish_reason = 'stop'
                    resp = event.get('response', {})
                    # 从完成事件中提取完整文本（备用，当没有收到 delta 事件时）
                    if not accumulated_text:
                        logger.info(f'[OpenAI Responses] 从 response.completed 提取文本')
                        output_list = resp.get('output', [])
                        for output_item in output_list:
                            if output_item.get('type') == 'message':
                                content_list = output_item.get('content', [])
                                for content_item in content_list:
                                    if content_item.get('type') == 'output_text':
                                        accumulated_text += content_item.get('text', '')

                # 处理响应失败事件: response.failed
                elif etype == 'response.failed':
                    resp = event.get('response', {})
                    error_info = resp.get('error', {})
                    error_code = error_info.get('code', 'unknown_error')
                    error_message = error_info.get('message', 'The model failed to generate a response.')
                    logger.error(f'[OpenAI Responses] 响应失败: {error_code} - {error_message}')
                    raise Exception(f'响应失败: {error_code} - {error_message}')

                # 兼容其他 delta 事件
                elif etype and 'delta' in etype:
                    delta = event.get('delta', '')
                    if delta:
                        accumulated_text += str(delta)
                        logger.info(f'[OpenAI Responses] 收到其他 delta 事件: {etype}')

        logger.info(f'[OpenAI Responses] 解析完成，文本长度: {len(accumulated_text)}')
        logger.info(f'[OpenAI Responses] 文本内容: {accumulated_text[:200]}...' if len(accumulated_text) > 200 else f'[OpenAI Responses] 文本内容: {accumulated_text}')

        result: Dict[str, Any] = {
            'success': True,
            'message': '对话成功',
            'data': {
                'content': accumulated_text,
                'role': 'assistant',
                'finishReason': finish_reason
            },
            'metadata': {
                'model': model_id,
                'id': response_id,
                'created': created_ts,
                'finishReason': finish_reason,
                'serviceTier': None
            }
        }
        logger.info(f'[OpenAI Responses] 返回结果: {json.dumps(result, ensure_ascii=False)[:500]}')
        return result

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        调用 OpenAI Responses Create 接口
        官方文档: https://platform.openai.com/docs/api-reference/responses/create

        必需参数:
        - model: 模型 ID
        - input: 输入内容 (字符串或消息数组)

        可选参数:
        - instructions: 系统指令
        - max_output_tokens: 最大输出 token 数
        - temperature: 采样温度
        - top_p: 核采样
        - stop: 停止序列
        - tools: 工具列表 (web_search_preview, file_search 等)
        - tool_choice: 工具选择策略
        - truncation: 截断策略
        - reasoning: 推理配置 (用于 o1/o3 系列模型)
        - metadata: 元数据
        - store: 是否存储响应
        - include: 额外返回内容
        """
        try:
            host = "https://api.modellink.online"
            apiKey = tool_parameters.get('apiKey')
            if not apiKey or not isinstance(apiKey, str) or not apiKey.strip():
                raise ValueError('缺少有效的 API Key')

            messages = tool_parameters.get('messages', [])
            prompt = tool_parameters.get('prompt')
            model = tool_parameters.get('model', 'gpt-4o')

            # 辅助函数：过滤无效参数值
            def get_param(key: str) -> Any:
                val = tool_parameters.get(key)
                if val is None or val == 'variable' or val == '':
                    return None
                return val

            # Responses API 支持的参数
            instructions = get_param('instructions')
            temperature = get_param('temperature')
            max_output_tokens = get_param('maxOutputTokens') or get_param('maxCompletionTokens')
            top_p = get_param('topP')
            stop = get_param('stop')
            tools = get_param('tools')
            tool_choice = get_param('toolChoice')
            truncation = get_param('truncation')
            reasoning = get_param('reasoning')
            metadata = get_param('metadata')
            store = get_param('store')
            include = get_param('include')
            previous_response_id = get_param('previousResponseId')
            stream = tool_parameters.get('stream', True)

            logger.info(f'[OpenAI Responses] 开始对话，模型: {model}')

            # 构建 input 参数
            if isinstance(messages, str):
                try:
                    messages = json.loads(messages)
                except json.JSONDecodeError:
                    messages = []

            input_value = self._build_input(messages if isinstance(messages, list) else [], prompt)

            # 构建请求体
            request_body: Dict[str, Any] = {
                'model': model,
                'input': input_value,
                'stream': stream
            }

            # 添加可选参数
            if instructions is not None:
                request_body['instructions'] = instructions
            if temperature is not None:
                request_body['temperature'] = temperature
            if max_output_tokens is not None:
                request_body['max_output_tokens'] = max_output_tokens
            if top_p is not None:
                request_body['top_p'] = top_p
            if stop is not None:
                request_body['stop'] = stop
            if tools is not None:
                if isinstance(tools, str):
                    try:
                        request_body['tools'] = json.loads(tools)
                    except json.JSONDecodeError:
                        pass
                else:
                    request_body['tools'] = tools
            if tool_choice is not None:
                request_body['tool_choice'] = tool_choice
            if truncation is not None:
                request_body['truncation'] = truncation
            if reasoning is not None:
                if isinstance(reasoning, str):
                    try:
                        request_body['reasoning'] = json.loads(reasoning)
                    except json.JSONDecodeError:
                        request_body['reasoning'] = {'effort': reasoning}
                else:
                    request_body['reasoning'] = reasoning
            if metadata is not None:
                if isinstance(metadata, str):
                    try:
                        request_body['metadata'] = json.loads(metadata)
                    except json.JSONDecodeError:
                        pass
                else:
                    request_body['metadata'] = metadata
            if store is not None:
                request_body['store'] = store
            if include is not None:
                if isinstance(include, str):
                    request_body['include'] = [s.strip() for s in include.split(',')]
                else:
                    request_body['include'] = include
            if previous_response_id is not None:
                request_body['previous_response_id'] = previous_response_id

            request_body_string = json.dumps(request_body, ensure_ascii=False)
            logger.info(f'[OpenAI Responses] 请求体: {request_body_string}')

            api_url = f"{host}/v1/responses"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {apiKey}'
            }

            result = self._stream_responses(api_url, headers, request_body)
            yield self.create_json_message(result)
        except Exception as e:
            logger.error(f'[OpenAI Responses] 异常: {str(e)}')
            yield self.create_json_message({
                'success': False,
                'message': str(e) or '对话失败',
                'error': str(e)
            })
