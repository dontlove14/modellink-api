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
            
            request_body_string = json.dumps(request_body)
            logger.info(f'[OpenAI Chat] 请求体: {request_body_string}')
            
            # 发送请求
            api_url = f"{host}/v1/chat/completions"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {apiKey}'
            }
            
            response = requests.post(api_url, headers=headers, json=request_body, timeout=60)
            
            logger.info(f'[OpenAI Chat] 响应状态: {response.status_code}')
            
            if not response.ok:
                error_text = response.text
                logger.error(f'[OpenAI Chat] 错误响应: {error_text}')
                raise Exception(f'API 请求失败: {response.status_code} - {error_text}')
            
            completion = response.json()
            logger.info(f'[OpenAI Chat] 请求成功')
            
            choice = completion.get('choices', [])[0]
            if not choice:
                raise Exception('API 响应中未找到回复内容')
            
            assistant_message = choice.get('message')
            if not assistant_message:
                raise Exception('API 响应中未找到回复消息')
            
            response_content = assistant_message.get('content', '')
            
            # 处理响应 content
            if isinstance(response_content, dict) and 'text' in response_content:
                response_content = response_content['text']
            elif not isinstance(response_content, str):
                response_content = json.dumps(response_content)
            
            # 构建返回结果
            result = {
                'success': True,
                'message': '对话成功',
                'data': {
                    'content': response_content,
                    'role': assistant_message.get('role', 'assistant'),
                    'finishReason': choice.get('finish_reason')
                },
                'metadata': {
                    'model': completion.get('model'),
                    'id': completion.get('id'),
                    'created': completion.get('created'),
                    'finishReason': choice.get('finish_reason'),
                    'serviceTier': completion.get('service_tier')
                }
            }
            
            # 添加 usage 信息
            if completion.get('usage'):
                usage = completion['usage']
                result['data']['usage'] = {
                    'promptTokens': usage.get('prompt_tokens'),
                    'completionTokens': usage.get('completion_tokens'),
                    'totalTokens': usage.get('total_tokens'),
                    'promptTokensDetails': usage.get('prompt_tokens_details'),
                    'completionTokensDetails': usage.get('completion_tokens_details')
                }
            
            yield self.create_json_message(result)
            
        except Exception as e:
            logger.error(f'[OpenAI Chat] 异常: {str(e)}')
            yield self.create_json_message({
                'success': False,
                'message': str(e) or '对话失败',
                'error': str(e)
            })
