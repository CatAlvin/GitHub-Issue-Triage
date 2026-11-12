"""Project-local model configuration with an explicit offline default."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "deepseek": "deepseek-chat",
}


class ConfigurationError(ValueError):
    pass


def llm_provider() -> str:
    mode = os.getenv("APP_MODE", "offline").strip().lower()
    if mode == "offline":
        return "mock"
    if mode != "live":
        raise ConfigurationError("APP_MODE must be offline or live")
    for provider, key in (("openai", "OPENAI_API_KEY"),
                          ("anthropic", "ANTHROPIC_API_KEY"),
                          ("deepseek", "DEEPSEEK_API_KEY")):
        if os.getenv(key):
            return provider
    raise ConfigurationError("APP_MODE=live requires a model API key")


def llm_model() -> str:
    provider = llm_provider()
    return "mock" if provider == "mock" else os.getenv("LLM_MODEL") or DEFAULT_MODELS[provider]


def llm_available() -> bool:
    return llm_provider() != "mock"


def call_llm(system: str, user: str, mock=None, temperature: float = 0.3,
             max_output_tokens: int | None = None) -> str:
    provider = llm_provider()
    if provider == "mock":
        if mock is None:
            raise ConfigurationError("Offline mode requires an extractive implementation")
        return mock(system, user) if callable(mock) else mock
    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    retries = int(os.getenv("LLM_MAX_RETRIES", "1"))
    if not 0 < timeout <= 300 or not 0 <= retries <= 3:
        raise ConfigurationError("LLM_TIMEOUT must be in (0,300]; LLM_MAX_RETRIES in [0,3]")
    if provider in ("openai", "deepseek"):
        from openai import OpenAI
        kwargs = {"timeout": timeout, "max_retries": retries}
        if provider == "deepseek":
            kwargs.update(api_key=os.environ["DEEPSEEK_API_KEY"],
                          base_url="https://api.deepseek.com")
        with OpenAI(**kwargs) as client:
            result = client.chat.completions.create(
                model=llm_model(),
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=temperature, max_tokens=max_output_tokens or 1500)
            answer = result.choices[0].message.content
    else:
        import anthropic
        with anthropic.Anthropic(timeout=timeout, max_retries=retries) as client:
            result = client.messages.create(
                model=llm_model(), max_tokens=max_output_tokens or 1500,
                system=system, messages=[{"role": "user", "content": user}])
            answer = "".join(block.text for block in result.content if block.type == "text")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Model returned an empty response")
    return answer
