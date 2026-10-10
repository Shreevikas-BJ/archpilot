import json

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app.config import Settings


def build_model(settings: Settings):
    if settings.llm_provider == "ollama":
        return OllamaModel(
            settings.llm_model,
            provider=OllamaProvider(base_url=settings.llm_base_url),
        )

    return OpenAIChatModel(
        settings.llm_model,
        provider=OpenAIProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        ),
    )


def agent_model_settings(
    settings: Settings, *, reasoning_budget_tokens: int | None = None
) -> ModelSettings:
    model_settings = ModelSettings(
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
    )
    budget = (
        settings.llm_reasoning_budget_tokens
        if reasoning_budget_tokens is None
        else reasoning_budget_tokens
    )
    if settings.llm_provider == "openai_compatible":
        extra = {}
        if budget is not None:
            extra["reasoning_budget_tokens"] = budget
        if settings.llm_reasoning_budget_message:
            extra["reasoning_budget_message"] = settings.llm_reasoning_budget_message
        if extra:
            model_settings["extra_body"] = extra
    return model_settings


def build_agent(
    *,
    settings: Settings,
    output_type: type[BaseModel],
    instructions: str,
    reasoning_budget_tokens: int | None = None,
) -> Agent[None, str]:
    model = build_model(settings)
    system_prompt = (
        f"{instructions}\n\n"
        "Return exactly one JSON object matching the JSON Schema below. "
        "Return JSON only: no Markdown fences, commentary, or tool calls. "
        "Include all required fields and use the exact field names and allowed values. "
        "Keep field values concise and avoid repeating the input context. "
        "Preserve concrete constraints, guarantees and implementation details; brevity must "
        "not remove required information. Use each object key exactly once.\n\n"
        f"JSON Schema:\n{json.dumps(output_type.model_json_schema(), separators=(',', ':'))}"
    )

    # Bonsai's chat template requires a single system message at the beginning.
    # Keep schemas in that prompt, never in tools or native response_format metadata.
    return Agent(
        model,
        output_type=str,
        system_prompt=system_prompt,
        retries=0,
        model_settings=agent_model_settings(
            settings, reasoning_budget_tokens=reasoning_budget_tokens
        ),
    )
