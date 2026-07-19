"""
LLM 服务 — 支持 OpenAI 兼容 API，可自定义模型和端点路径
启动时自动加载活跃供应商配置
支持 Function Calling 的智能体循环
"""
import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from config import LLM_CONFIG

# 可运行时覆盖的全局配置
_runtime_llm_config: dict = {}
# 当前激活的供应商 ID（用于章节生成时指定）
_active_provider: Optional[dict] = None


def _try_repair_json(s: str):
    """尝试修复不完整的 JSON 字符串（AI 输出被截断的情况）
    
    常见截断模式：
    - {"name": "林宇"  （缺右括号）
    - {"name": "林宇",  （末尾逗号 + 缺右括号）
    - {"items": ["a", "b  （字符串未闭合 + 缺括号）
    
    返回修复后的 dict，或 None（无法修复）
    """
    s = s.strip()
    if not s:
        return None
    
    # 快速路径：已经是合法 JSON
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    
    # 尝试 1：补全缺失的右括号和右方括号
    repaired = s
    # 去掉末尾的逗号（trailing comma）
    repaired = repaired.rstrip().rstrip(',')
    
    # 统计未闭合的括号
    open_braces = 0
    open_brackets = 0
    in_string = False
    escape = False
    for ch in repaired:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            open_braces += 1
        elif ch == '}':
            open_braces -= 1
        elif ch == '[':
            open_brackets += 1
        elif ch == ']':
            open_brackets -= 1
    
    # 如果字符串未闭合，尝试闭合它
    if in_string:
        repaired += '"'
    
    # 补全方括号和花括号
    repaired += ']' * max(open_brackets, 0)
    repaired += '}' * max(open_braces, 0)
    
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass
    
    # 尝试 2：用更宽松的方式——提取 key:value 对
    # 这种情况适用于 {"name": "林宇", "age": 25 被截断
    try:
        # 如果以 { 开头但不完整，尝试补成完整对象
        if repaired.startswith('{') and not repaired.endswith('}'):
            # 去掉可能的末尾不完整部分
            # 找最后一个完整的 key:value 对
            test = repaired
            if not test.endswith('"') and not test.endswith('}') and not test.endswith(']'):
                # 末尾可能是不完整的值，尝试截断到最后一个完整的值
                # 找最后一个引号或数字结尾
                last_quote = test.rfind('"')
                last_bracket = max(test.rfind('}'), test.rfind(']'))
                last_complete = max(last_quote, last_bracket)
                if last_complete > 0:
                    test = test[:last_complete + 1]
                    # 去掉末尾逗号
                    test = test.rstrip().rstrip(',')
                    test += '}'
                    return json.loads(test)
    except (json.JSONDecodeError, ValueError):
        pass
    
    return None

def update_llm_config(api_base: str = "", api_key: str = "", model: str = "",
                      temperature: float = 0.8, max_tokens: int = 4096,
                      chat_path: str = ""):
    """更新 LLM 运行时配置"""
    global _runtime_llm_config
    if api_base:
        _runtime_llm_config["api_base"] = api_base
    if api_key:
        _runtime_llm_config["api_key"] = api_key
    if model:
        _runtime_llm_config["model"] = model
    if chat_path:
        _runtime_llm_config["chat_path"] = chat_path
    _runtime_llm_config["temperature"] = temperature
    _runtime_llm_config["max_tokens"] = max_tokens


def set_active_provider(provider: Optional[dict]):
    """设置当前活跃供应商（用于章节生成时临时切换）"""
    global _active_provider
    _active_provider = provider


def apply_active_provider():
    """从 provider_service 重新加载活跃供应商到运行时"""
    global _active_provider
    from services.provider_service import list_providers
    providers = list_providers(mask_keys=False)
    active = next((p for p in providers if p.get("is_active")), None)
    if active:
        _active_provider = active
    else:
        _active_provider = None


def get_llm_config() -> dict:
    """获取当前有效的 LLM 配置"""
    global _active_provider
    if _active_provider:
        return {
            "api_base": _active_provider.get("api_base", LLM_CONFIG["api_base"]),
            "api_key": _active_provider.get("api_key", LLM_CONFIG["api_key"]),
            "model": _active_provider.get("model", LLM_CONFIG["model"]),
            "temperature": _active_provider.get("temperature", LLM_CONFIG["temperature"]),
            "max_tokens": _active_provider.get("max_tokens", LLM_CONFIG["max_tokens"]),
            "chat_path": _active_provider.get("chat_path", LLM_CONFIG["chat_path"]),
        }
    cfg = {**LLM_CONFIG, **_runtime_llm_config}
    return cfg


def _build_url(cfg: dict) -> str:
    """构建 chat completions 请求 URL"""
    base = cfg["api_base"].rstrip("/")
    path = cfg.get("chat_path") or "/chat/completions"
    if not path.startswith("/"):
        path = "/" + path
    # base 已包含完整路径时不重复拼接
    if base.endswith(path):
        return base
    if "/chat/completions" in base or base.endswith("/chat"):
        return base
    return f"{base}{path}"


async def chat_completion(
    messages: list[dict],
    stream: bool = False,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> dict:
    """调用 LLM 聊天补全（非流式）"""
    cfg = get_llm_config()
    url = _build_url(cfg)

    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature if temperature is not None else cfg["temperature"],
        "max_tokens": max_tokens if max_tokens is not None else cfg["max_tokens"],
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
        )
        # 保留 LLM API 返回的错误详情，便于调试
        if resp.status_code >= 400:
            body = resp.text[:500]
            raise ValueError(f"LLM API 错误 ({resp.status_code}): {body}")
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("LLM 返回了空的 choices 列表")
        msg = choices[0].get("message", {})
        if not msg:
            raise ValueError("LLM 返回的 message 为空")
        return data


async def chat_completion_stream(
    messages: list[dict],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """调用 LLM 聊天补全（流式），逐块返回文本"""
    cfg = get_llm_config()
    url = _build_url(cfg)

    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature if temperature is not None else cfg["temperature"],
        "max_tokens": max_tokens if max_tokens is not None else cfg["max_tokens"],
        "stream": True,
    }

    # 流式场景使用更长的读取超时（模型推理可能需要较长时间）
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0)) as client:
        async with client.stream(
            "POST",
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise ValueError(f"LLM API 错误 ({resp.status_code}): {body.decode('utf-8', errors='replace')[:500]}")
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue


# ==================== Function Calling 支持 ====================

async def chat_completion_stream_with_tools(
    messages: list[dict],
    tools: list[dict],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncGenerator[tuple, None]:
    """带工具调用的流式聊天补全。
    
    一次请求内 yield:
      ("content", "文本片段")     — LLM 生成的正文内容
      ("reasoning", "推理片段")   — LLM 的推理/思考内容（DeepSeek R1, Qwen QwQ 等）
      ("tool_calls", [{...}])    — LLM 请求的工具调用（请求结束，需执行后重新调用）
      ("finish", reason)         — 本次请求结束的原因
    
    调用方需要：
    1. 收到 ("content", ...) 时转发给前端
    2. 收到 ("reasoning", ...) 时转发给前端思考区
    3. 收到 ("tool_calls", [...]) 时执行工具，将结果追加到 messages，再次调用本函数
    4. 收到 ("finish", "stop") 且无 tool_calls 时，生成完成
    """
    cfg = get_llm_config()
    url = _build_url(cfg)

    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature if temperature is not None else cfg["temperature"],
        "max_tokens": max_tokens if max_tokens is not None else cfg["max_tokens"],
        "stream": True,
        "tools": tools,
        "tool_choice": "auto",
    }

    accumulated_tool_calls = []
    current_tool_call = None
    has_tool_calls = False
    finish_reason = None

    # 流式场景使用更长的读取超时（模型推理可能需要较长时间，特别是带 reasoning 的模型）
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0)) as client:
        async with client.stream(
            "POST",
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise ValueError(f"LLM API 错误 ({resp.status_code}): {body.decode('utf-8', errors='replace')[:500]}")
            
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    finish_reason = choices[0].get("finish_reason") or finish_reason

                    # 转发推理/思考内容（DeepSeek R1, Qwen QwQ 等模型的 reasoning_content）
                    reasoning = delta.get("reasoning_content", "") or delta.get("reasoning", "")
                    if reasoning:
                        yield ("reasoning", reasoning)

                    # 转发正文内容
                    content = delta.get("content", "")
                    if content:
                        yield ("content", content)

                    # 累积工具调用
                    tool_calls_delta = delta.get("tool_calls", [])
                    if tool_calls_delta:
                        has_tool_calls = True
                        for tc in tool_calls_delta:
                            idx = tc.get("index", 0)
                            # 扩展列表到所需索引
                            while len(accumulated_tool_calls) <= idx:
                                accumulated_tool_calls.append({
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                })
                            if tc.get("id"):
                                accumulated_tool_calls[idx]["id"] = tc["id"]
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                accumulated_tool_calls[idx]["function"]["name"] += fn["name"]
                            if fn.get("arguments"):
                                accumulated_tool_calls[idx]["function"]["arguments"] += fn["arguments"]
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue

    # 请求结束后，如果有工具调用则 yield
    if has_tool_calls and accumulated_tool_calls:
        # 清理空调用
        valid_calls = [tc for tc in accumulated_tool_calls if tc["function"]["name"]]
        if valid_calls:
            yield ("tool_calls", valid_calls)
    
    yield ("finish", finish_reason or "stop")


async def agentic_generate(
    messages: list[dict],
    tools: list[dict],
    tool_executor: callable,
    stream_callback: Optional[callable] = None,
    max_rounds: int = 10,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """智能体生成循环。
    
    分离式架构：
    - 工具调用轮次中 LLM 输出的文本 → "thinking"（思考过程）
    - 最后一轮（无工具调用）的文本 → "chunk"（正文内容）
    - reasoning_content（DeepSeek R1 等）→ "thinking"（推理过程，增量发送）
    
    stream_callback 收到的事件类型：
      {"type": "chunk", "data": str}         — 正文片段
      {"type": "thinking", "data": str}      — 思考过程片段（增量发送）
      {"type": "tool_call", ...}             — 工具调用
      {"type": "tool_result", ...}           — 工具结果
      {"type": "content_replace", "data": str} — 用最终清洗后的内容替换流式内容
    """
    full_content = ""
    had_reasoning = False  # 是否收到过推理内容
    skip_tools = False  # 重试时跳过工具，强制模型直接输出正文
    total_tool_calls = 0  # 累计工具调用次数
    tool_result_chars = 0  # 累计工具返回结果字符数（防止上下文膨胀）
    
    # 创建副本，避免修改调用方的 messages 列表（防止会话历史污染）
    messages = list(messages)
    
    for round_num in range(max_rounds):
        round_content = ""
        round_had_tool_calls = False
        round_had_reasoning = False
        round_finish_reason = None
        
        # 重试模式下不传工具，强制模型直接输出正文
        current_tools = [] if skip_tools else tools
        
        logging.info("agentic_generate round %d/%d, skip_tools=%s, tools=%d, msgs=%d, total_tool_calls=%d",
                     round_num + 1, max_rounds, skip_tools, len(current_tools), len(messages), total_tool_calls)
        
        async for event_type, data in chat_completion_stream_with_tools(
            messages, current_tools, temperature=temperature, max_tokens=max_tokens,
        ):
            if event_type == "reasoning":
                # 推理内容直接增量发送到思考区，不累积到 round_content
                round_had_reasoning = True
                had_reasoning = True
                if stream_callback:
                    await stream_callback({"type": "thinking", "data": data, "incremental": True})
            
            elif event_type == "content":
                round_content += data
                # 先作为正文发送（保持流式体验）
                if stream_callback:
                    await stream_callback({"type": "chunk", "data": data})
            
            elif event_type == "tool_calls":
                round_had_tool_calls = True
                total_tool_calls += 1
                # 本轮的文本是"思考"而非正文
                if round_content and stream_callback:
                    # 用 content_replace 清空正文区（比前端 slice 更可靠）
                    await stream_callback({"type": "content_replace", "data": ""})
                    # 将本轮内容作为思考增量发送
                    await stream_callback({"type": "thinking", "data": round_content, "incremental": True})
                round_content = ""  # 不计入 full_content

                # 先追加一条 assistant 消息（含全部 tool_calls），只追加一次
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": data,
                })

                # 逐个执行工具并追加 tool 结果
                for tc in data:
                    fn_name = tc["function"]["name"]
                    raw_args = tc["function"].get("arguments") or "{}"
                    fn_args = None
                    try:
                        fn_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        # 尝试修复常见的不完整 JSON（AI 输出被截断的情况）
                        fn_args = _try_repair_json(raw_args)
                        if fn_args is not None:
                            logging.info("工具参数 JSON 已自动修复: %s -> %s", raw_args[:80], fn_args)
                        else:
                            logging.warning("工具参数 JSON 解析失败，跳过工具 %s: %s", fn_name, raw_args[:200])
                            # 不执行工具，告知 AI 参数格式错误，让它重新调用
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "name": fn_name,
                                "content": f"错误：工具参数 JSON 格式无效（可能被截断）。请重新调用工具 {fn_name}，确保参数完整。收到的参数：{raw_args[:200]}",
                            })
                            continue
                    
                    if stream_callback:
                        await stream_callback({
                            "type": "tool_call",
                            "name": fn_name,
                            "args": fn_args,
                        })
                    
                    # 执行工具
                    try:
                        result = await tool_executor(fn_name, fn_args)
                    except Exception as e:
                        logging.exception("工具执行失败 %s: %s", fn_name, e)
                        result = f"工具执行出错: {e}"
                    
                    # 追加 tool 结果消息
                    result_str = str(result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str,
                    })
                    tool_result_chars += len(result_str)
                    
                    if stream_callback:
                        await stream_callback({
                            "type": "tool_result",
                            "name": fn_name,
                            "preview": result_str[:200],
                        })
            
            elif event_type == "finish":
                round_finish_reason = data
        
        # finish 事件处理（移到循环外，确保所有事件都已处理）
        if not round_had_tool_calls:
            # 情况1: 推理模型把 max_tokens 全用在 reasoning 上，content 为空
            # 情况2: finish_reason=length 说明 token 耗尽，content 被截断
            # 情况3: 完全空响应（无 reasoning 无 content）
            # 情况4: 工具调用后模型未输出正文（最常见）
            need_retry = (not round_content) or (
                len(round_content) < 100 and round_finish_reason == "length"
            )
            
            # 防止无限重试：skip_tools 模式下最多重试 2 次
            if skip_tools and need_retry and round_num >= max_rounds - 3:
                logging.warning("skip_tools 模式下仍无正文，放弃重试（round %d）", round_num)
                # 累积已获取的内容（可能为空），直接返回
                full_content += round_content
                return full_content
            
            if need_retry and round_num < max_rounds - 1:
                if round_had_reasoning:
                    retry_reason = "推理后无正文"
                elif round_finish_reason == "length":
                    retry_reason = "token耗尽"
                elif total_tool_calls > 0:
                    retry_reason = "工具调用后无正文"
                else:
                    retry_reason = "空响应"
                logging.info("自动重试 (%s, round %d, 内容%d字符, 工具调用%d次)", retry_reason, round_num, len(round_content), total_tool_calls)
                if stream_callback:
                    await stream_callback({
                        "type": "thinking",
                        "data": f"（{retry_reason}，正在重新生成正文...）",
                        "incremental": True,
                    })
                    if round_content:
                        # 有部分内容但被截断，清空重来
                        await stream_callback({"type": "content_replace", "data": ""})
                
                # 重试策略：跳过工具 + 追加直接输出指令
                skip_tools = True
                messages.append({"role": "assistant", "content": round_content or None})
                messages.append({
                    "role": "user",
                    "content": "请直接输出完整的小说正文，不要思考过程，不要调用工具，不要输出任何说明或注释。",
                })
                continue  # 进入下一轮
            
            full_content += round_content
            return full_content
        # 否则继续下一轮（工具调用后的下一轮）
        # 上下文膨胀保护：累积工具结果超过 6000 字时强制进入正文生成
        if not skip_tools and tool_result_chars >= 6000:
            logging.info("工具结果累积 %d 字，强制跳过工具进入正文生成", tool_result_chars)
            skip_tools = True
            messages.append({
                "role": "user",
                "content": "你已查阅了足够的设定信息（累积%d字），现在请直接输出完整的小说正文，不要再调用工具。" % tool_result_chars,
            })
        # 工具调用次数保护：超过 6 次也强制进入正文
        elif not skip_tools and total_tool_calls >= 6:
            logging.info("工具调用已达 %d 次，强制跳过工具进入正文生成", total_tool_calls)
            skip_tools = True
            messages.append({
                "role": "user",
                "content": "你已调用足够多次工具查阅设定，现在请直接输出完整的小说正文，不要再调用工具。",
            })
    
    # 达到最大轮次后，full_content 仍为空，做最后一次无工具尝试
    if not full_content:
        logging.warning("agentic_generate 达到最大轮次且无正文，最后尝试无工具生成")
        if stream_callback:
            await stream_callback({
                "type": "thinking",
                "data": "（多次尝试未输出正文，使用简化模式最后尝试...）",
                "incremental": True,
            })
            await stream_callback({"type": "content_replace", "data": ""})
        messages.append({
            "role": "user",
            "content": "请立即输出小说正文，不要调用任何工具，不要思考，直接开始写作。",
        })
        async for event_type, data in chat_completion_stream_with_tools(
            messages, [], temperature=temperature, max_tokens=max_tokens,
        ):
            if event_type == "content" and stream_callback:
                full_content += data
                await stream_callback({"type": "chunk", "data": data})
    
    return full_content
