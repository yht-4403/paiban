import json
import os
import time

import httpx

from accord_api.platform.ai.config import (
    REASONING_EFFORTS,
    configured,
    default_reasoning_effort,
    model_name,
    supports_reasoning,
)
from accord_api.platform.ai.errors import ModelError


def stream_answer(
    messages,
    sources,
    on_delta,
    cancelled,
    model=None,
    tool_context=None,
    on_usage=None,
    reasoning_effort=None,
    on_phase=None,
):
    if not configured():
        raise ModelError('not_configured', '模型尚未连接，请联系工作空间管理员配置。')
    started = time.monotonic()
    body, usage, finish_reason, reasoning_trace = '', {}, '', ''
    model = model or model_name()
    deepseek = supports_reasoning()
    effort = reasoning_effort or default_reasoning_effort()
    if effort not in REASONING_EFFORTS:
        raise ModelError('configuration', '思考强度设置无效，请重新选择。')
    timeout_seconds = int(
        os.environ.get('ACCORD_LLM_TIMEOUT_SECONDS', '900' if deepseek else '120')
    )
    seen_calls = set()

    def check():
        if cancelled():
            raise ModelError('cancelled', '已停止生成。')
        if time.monotonic() - started > timeout_seconds:
            raise ModelError('timeout', '生成超时，已保留现有内容。你可以重试。')
        if tool_context:
            tool_context.check()

    try:
        with httpx.Client(timeout=httpx.Timeout(60 if deepseek else 30, connect=10)) as client:
            for turn in range(7):
                check()
                payload = {
                    'model': model,
                    'messages': messages,
                    'stream': True,
                    'stream_options': {'include_usage': True},
                    'max_tokens': int(
                        os.environ.get('ACCORD_LLM_MAX_TOKENS', '65536' if deepseek else '4096')
                    ),
                }
                if tool_context:
                    payload.update(
                        tools=tool_context.schemas,
                        tool_choice='auto' if turn < 6 else 'none',
                        parallel_tool_calls=False,
                    )
                thinking = os.environ.get('ACCORD_LLM_ENABLE_THINKING', '')
                if deepseek:
                    payload.update(thinking={'type': 'enabled'}, reasoning_effort=effort)
                elif thinking in ('true', 'false'):
                    payload['enable_thinking'] = thinking == 'true'
                content, calls, round_usage, finish_reason, reasoning = '', {}, {}, '', ''
                prefix = body + ('\n\n' if body else '')
                with client.stream(
                    'POST',
                    os.environ['ACCORD_LLM_BASE_URL'].rstrip('/') + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + os.environ['ACCORD_LLM_API_KEY']},
                    json=payload,
                ) as response:
                    if response.status_code in (401, 403):
                        raise ModelError(
                            'authorization', '模型服务拒绝了访问，请联系管理员检查模型权限。'
                        )
                    if response.status_code == 429:
                        raise ModelError('rate_limit', '模型服务当前繁忙或额度受限，请稍后重试。')
                    if response.status_code == 402:
                        raise ModelError('balance', '模型账户余额不足，请联系管理员充值后重试。')
                    if not response.is_success:
                        raise ModelError('upstream', '模型服务暂时无法完成请求，请稍后重试。')
                    for line in response.iter_lines():
                        if not line.startswith('data:'):
                            check()
                            continue
                        data = line[5:].strip()
                        if data == '[DONE]':
                            break
                        event = json.loads(data)
                        # Save provider-reported usage even if the user stopped this run.
                        if event.get('usage'):
                            round_usage = {
                                key: event['usage'][key]
                                for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                                if type(event['usage'].get(key)) is int and event['usage'][key] >= 0
                            }
                            reasoning_tokens = (
                                event['usage'].get('completion_tokens_details') or {}
                            ).get('reasoning_tokens')
                            if type(reasoning_tokens) is int and reasoning_tokens >= 0:
                                round_usage['reasoning_tokens'] = reasoning_tokens
                            if on_usage:
                                on_usage(
                                    {
                                        key: usage.get(key, 0) + round_usage.get(key, 0)
                                        for key in usage.keys() | round_usage.keys()
                                    }
                                )
                        check()
                        if event.get('error'):
                            raise ModelError('upstream', '模型服务中断了回答，请重试。')
                        choices = event.get('choices', [])
                        if not choices:
                            continue
                        delta = choices[0].get('delta', {})
                        thought = delta.get('reasoning_content') or ''
                        if not isinstance(thought, str):
                            raise ModelError(
                                'invalid_response', '模型返回的思考内容无法读取，请重试。'
                            )
                        reasoning += thought
                        if len(reasoning_trace) + len(reasoning) > 2000000:
                            raise ModelError(
                                'output_limit', '思考达到本次长度上限，请缩小问题范围后重试。'
                            )
                        if thought and on_phase:
                            on_phase('thinking')
                        part = delta.get('content') or ''
                        if not isinstance(part, str):
                            raise ModelError('invalid_response', '模型返回的内容无法读取，请重试。')
                        content += part
                        if len(prefix + content) > (120000 if deepseek else 32000):
                            raise ModelError(
                                'output_limit', '回答达到长度上限，请缩小问题范围后重试。'
                            )
                        if part:
                            if on_phase:
                                on_phase('answering')
                            on_delta(
                                prefix + content,
                                list(tool_context.used) if tool_context else sources,
                            )
                        for fragment in delta.get('tool_calls') or []:
                            index = fragment.get('index')
                            if type(index) is not int or not 0 <= index < 12:
                                raise ModelError('invalid_response', '工具调用格式不完整，请重试。')
                            call = calls.setdefault(
                                index,
                                {
                                    'id': '',
                                    'type': 'function',
                                    'function': {'name': '', 'arguments': ''},
                                },
                            )
                            if fragment.get('id'):
                                if call['id'] and call['id'] != fragment['id']:
                                    raise ModelError(
                                        'invalid_response', '工具调用标识发生变化，请重试。'
                                    )
                                call['id'] = fragment['id']
                            function = fragment.get('function') or {}
                            for key in ('name', 'arguments'):
                                call['function'][key] += function.get(key) or ''
                            if (
                                len(call['function']['arguments']) > 8000
                                or len(call['function']['name']) > 80
                            ):
                                raise ModelError(
                                    'tool_limit', '工具参数超出范围，请缩小问题后重试。'
                                )
                        finish_reason = choices[0].get('finish_reason') or finish_reason
                usage = {
                    key: usage.get(key, 0) + round_usage.get(key, 0)
                    for key in usage.keys() | round_usage.keys()
                }
                reasoning_trace += reasoning
                if content:
                    body = prefix + content
                if not calls:
                    if finish_reason == 'length' and not content.strip():
                        raise ModelError(
                            'reasoning_limit',
                            '思考已达到本次生成上限，尚未形成回答。请缩小问题范围或降低思考强度后重试。',
                        )
                    if not content.strip() or not finish_reason or finish_reason == 'tool_calls':
                        raise ModelError('incomplete', '模型没有完整返回回答，请重试。')
                    if finish_reason not in ('stop', 'length'):
                        raise ModelError('incomplete', '模型未能完成回答，已有内容已保留，请重试。')
                    break
                if not tool_context or turn >= 6 or finish_reason != 'tool_calls':
                    raise ModelError('tool_limit', '资料查阅没有完成，请缩小问题范围后重试。')
                ordered = [calls[index] for index in sorted(calls)]
                for call in ordered:
                    if (
                        not isinstance(call['id'], str)
                        or not 1 <= len(call['id']) <= 160
                        or call['id'] in seen_calls
                    ):
                        raise ModelError('invalid_response', '工具调用标识无效，请重试。')
                    seen_calls.add(call['id'])
                assistant_turn = {
                    'role': 'assistant',
                    'content': content or None,
                    'tool_calls': ordered,
                }
                if deepseek:
                    assistant_turn['reasoning_content'] = reasoning
                messages.append(assistant_turn)
                if on_phase:
                    on_phase('reading')
                for call in ordered:
                    check()
                    args = json.loads(call['function']['arguments'])
                    result = tool_context.execute(call['id'], call['function']['name'], args)
                    messages.append(
                        {
                            'role': 'tool',
                            'tool_call_id': call['id'],
                            'content': json.dumps(result, ensure_ascii=False),
                        }
                    )
            check()
        return {
            'body': body,
            'sources': list(tool_context.used) if tool_context else sources,
            'model': model,
            'usage': usage,
            'citations': list(tool_context.used.values()) if tool_context else [],
            'reasoning_content': reasoning_trace if deepseek else '',
            'finish_reason': finish_reason,
            'duration_ms': round((time.monotonic() - started) * 1000),
        }
    except httpx.TimeoutException:
        raise ModelError('timeout', '模型响应超时，请稍后重试。') from None
    except httpx.HTTPError:
        raise ModelError('network', '暂时无法连接模型服务，请稍后重试。') from None
    except (ValueError, KeyError, TypeError, IndexError):
        raise ModelError('invalid_response', '模型返回的内容无法读取，请重试。') from None
