from __future__ import annotations


SYSTEM_PROMPT_TEMPLATE = """你是一个企业知识库问答助手。请只基于给定上下文回答用户问题。
如果上下文中没有答案，请明确回答“根据现有资料无法确定”。
不要编造事实。

上下文：
{context}
"""


def build_system_prompt(context: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(context=context or "暂无可用上下文。")
