from collections.abc import Generator
from typing import Any, Dict, List, Optional
import json
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

class OpenAIChatTool(Tool):
    def _stream_chat_completion(self, api_url: str, headers: Dict[str, Any], request_body: Dict[str, Any]) -> Dict[str, Any]:
        """使用流式读取完成 Chat Completions，并在方法内部聚合为完整结果后返回"""
        accumulated_text = ""
        finish_reason: Optional[str] = None
        model_id: Optional[str] = None
        completion_id: Optional[str] = None
        created_ts: Optional[int] = None

        response = requests.post(api_url, headers=headers, json=request_body, timeout=600, stream=True)

        logger.info(f'[OpenAI Chat] 响应状态: {response.status_code}')
        if not response.ok:
            error_text = response.text
            logger.error(f'[OpenAI Chat] 错误响应: {error_text}')
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
            if line.startswith('data:'):
                payload = line[len('data:'):].strip()
                if payload == '[DONE]':
                    break
                try:
                    chunk = json.loads(payload)
                except Exception:
                    continue

                model_id = chunk.get('model') or model_id
                completion_id = chunk.get('id') or completion_id
                created_ts = chunk.get('created') or created_ts

                choices = chunk.get('choices') or []
                if choices:
                    c0 = choices[0]
                    finish_reason = c0.get('finish_reason') or finish_reason
                    delta = c0.get('delta') or {}
                    if isinstance(delta, dict):
                        piece = delta.get('content')
                        if piece:
                            accumulated_text += piece
                    else:
                        msg = c0.get('message') or {}
                        if isinstance(msg, dict):
                            piece2 = msg.get('content')
                            if piece2:
                                accumulated_text += piece2

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
                'id': completion_id,
                'created': created_ts,
                'finishReason': finish_reason,
                'serviceTier': None
            }
        }
        return result
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """OpenAI Chat Completions API 封装，支持标准 OpenAI API 格式"""
        try:
            # 提取参数
            # 使用固定的 API host
            host = "https://api.modellink.online"
            apiKey = tool_parameters.get('apiKey')
            messages = tool_parameters.get('messages', [])
            prompt = tool_parameters.get('prompt')
            model = tool_parameters.get('model', 'gpt-4o')
            
            # 处理参数，跳过值为'variable'的参数
            temperature = tool_parameters.get('temperature') if tool_parameters.get('temperature') != 'variable' else None
            maxCompletionTokens = tool_parameters.get('maxCompletionTokens') if tool_parameters.get('maxCompletionTokens') != 'variable' else None
            topP = tool_parameters.get('topP') if tool_parameters.get('topP') != 'variable' else None
            frequencyPenalty = tool_parameters.get('frequencyPenalty') if tool_parameters.get('frequencyPenalty') != 'variable' else None
            presencePenalty = tool_parameters.get('presencePenalty') if tool_parameters.get('presencePenalty') != 'variable' else None
            n = tool_parameters.get('n') if tool_parameters.get('n') != 'variable' else None
            stop = tool_parameters.get('stop') if tool_parameters.get('stop') != 'variable' else None
            responseFormat = tool_parameters.get('responseFormat') if tool_parameters.get('responseFormat') != 'variable' else None
            reasoningEffort = tool_parameters.get('reasoningEffort') if tool_parameters.get('reasoningEffort') != 'variable' else None
            seed = tool_parameters.get('seed') if tool_parameters.get('seed') != 'variable' else None
            logitBias = tool_parameters.get('logitBias') if tool_parameters.get('logitBias') != 'variable' else None
            logprobs = tool_parameters.get('logprobs') if tool_parameters.get('logprobs') != 'variable' else None
            topLogprobs = tool_parameters.get('topLogprobs') if tool_parameters.get('topLogprobs') != 'variable' else None
            
            logger.info(f'[OpenAI Chat] 开始对话，模型: {model}')
            
            # 构建 messages 数组
            conversation_messages = []
            
            if messages and isinstance(messages, list) and len(messages) > 0:
                for msg in messages:
                    content = msg.get('content')
                    
                    if content:
                        formatted_content = content
                        
                        # 处理不同格式的 content
                        if isinstance(content, str):
                            # 字符串格式，直接使用
                            formatted_content = content
                        elif isinstance(content, list):
                            # 数组格式，直接使用（多模态）
                            formatted_content = content
                        elif isinstance(content, dict):
                            # 单个对象格式，转换为数组
                            # 处理 { type: 'text', text: '...' } 或 { type: 'text', content: '...' }
                            text = content.get('text') or content.get('content')
                            if text:
                                formatted_content = [{
                                    'type': 'text',
                                    'text': text
                                }]
                            else:
                                # 如果对象没有 text/content 字段，转换为 JSON 字符串
                                formatted_content = json.dumps(content)
                        else:
                            # 其他类型，转换为字符串
                            formatted_content = str(content)
                        
                        conversation_messages.append({
                            'role': msg.get('role', 'user'),
                            'content': formatted_content
                        })
            elif prompt:
                conversation_messages.append({
                    'role': 'user',
                    'content': prompt
                })
            else:
                raise Exception('必须提供 messages 或 prompt 参数')
            
            # 构建请求体
            request_body = {
                'model': model,
                'messages': conversation_messages
            }
            
            # 添加可选参数
            if temperature is not None:
                request_body['temperature'] = temperature
            if maxCompletionTokens is not None:
                request_body['max_completion_tokens'] = maxCompletionTokens
            if topP is not None:
                request_body['top_p'] = topP
            if frequencyPenalty is not None:
                request_body['frequency_penalty'] = frequencyPenalty
            if presencePenalty is not None:
                request_body['presence_penalty'] = presencePenalty
            if n is not None:
                request_body['n'] = n
            if stop is not None:
                request_body['stop'] = stop
            if responseFormat is not None:
                request_body['response_format'] = responseFormat
            if reasoningEffort is not None:
                request_body['reasoning_effort'] = reasoningEffort
            if seed is not None:
                request_body['seed'] = seed
            if logitBias is not None:
                request_body['logit_bias'] = logitBias
            if logprobs is not None:
                request_body['logprobs'] = logprobs
            if topLogprobs is not None:
                request_body['top_logprobs'] = topLogprobs
            
            request_body['stream'] = True
            request_body_string = json.dumps(request_body)
            logger.info(f'[OpenAI Chat] 请求体: {request_body_string}')
            
            # 发送请求
            api_url = f"{host}/v1/chat/completions"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {apiKey}'
            }
            
            result = self._stream_chat_completion(api_url, headers, request_body)
            yield self.create_json_message(result)
            
        except Exception as e:
            logger.error(f'[OpenAI Chat] 异常: {str(e)}')
            yield self.create_json_message({
                'success': False,
                'message': str(e) or '对话失败',
                'error': str(e)
            })
