from langchain_deepseek import ChatDeepSeek
from app.core.config import settings


def _build(model: str, temperature: float) -> ChatDeepSeek:
    return ChatDeepSeek(
        model=model,
        api_key=settings.DEEPSEEK_API_KEY,
        temperature=temperature,
        max_tokens=4096,
        timeout=60,
        max_retries=2,
    )


def get_llm(temperature: float = 0.7) -> ChatDeepSeek:
    """默认模型：可用 with_structured_output 强制结构化输出（行程生成、价格抽取）"""
    return _build(settings.DEEPSEEK_MODEL, temperature)


def get_thinking_llm(temperature: float = 0.7) -> ChatDeepSeek:
    """思考模型：用于多轮工具调用与自然语言对话。
    注意：思考模式不支持强制 tool_choice，所以不能用于 with_structured_output。"""
    return _build(settings.DEEPSEEK_MODEL_THINKING, temperature)
