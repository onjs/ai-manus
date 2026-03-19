from app.core.config import Settings
from app.infrastructure.providers.base_provider import BaseLLMProvider
from app.infrastructure.providers.openai_provider import OpenAICompatibleProvider


class ProviderFactory:
    _OPENAI_COMPATIBLE_PROVIDERS = {
        "openai",
        "deepseek",
        "qwen",
        "doubao",
        "moonshot",
        "zhipu",
        "glm",
    }

    @staticmethod
    def create(settings: Settings) -> BaseLLMProvider:
        provider = (settings.model_provider or "openai").strip().lower()
        if not settings.api_base:
            raise RuntimeError("API_BASE is required for gateway runtime streaming")

        if provider in ProviderFactory._OPENAI_COMPATIBLE_PROVIDERS:
            return OpenAICompatibleProvider(
                api_base=settings.api_base,
                api_key=settings.api_key,
                model_name=settings.model_name,
                timeout_seconds=settings.gateway_timeout_seconds,
                extra_headers=settings.extra_headers,
            )

        raise RuntimeError(f"Unsupported model_provider: {provider}")
