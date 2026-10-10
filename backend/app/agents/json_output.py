"""Parse plain chat output without PydanticAI's structured-output message handling."""

import json
import logging
import re
from time import perf_counter

from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.settings import ModelSettings

from app.agents.json_stream import JSONStreamGuard, loads_json

logger = logging.getLogger("uvicorn.error.agents")


class AgentJSONError(RuntimeError):
    """An agent exhausted its attempts to produce valid schema-conforming JSON."""


def strip_json_fences(text: str) -> str:
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json|code)?\s*\n?(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text


def parse_json_output[ResultT: BaseModel](
    text: str, output_type: type[ResultT], *, validation_context: dict | None = None
) -> ResultT:
    payload = loads_json(strip_json_fences(text))
    return output_type.model_validate(payload, context=validation_context)


async def run_json_agent[ResultT: BaseModel](
    agent: Agent[None, str],
    prompt: str,
    output_type: type[ResultT],
    *,
    max_retries: int = 2,
    validation_context: dict | None = None,
    run_id: str | None = None,
    stage: str | None = None,
    retry_model_settings: ModelSettings | None = None,
) -> ResultT:
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    retry_prompt = prompt
    for attempt in range(max_retries + 1):
        finish_reason = None
        output_length = 0
        started = perf_counter()
        input_tokens = output_tokens = None
        outcome = "error"
        guard = JSONStreamGuard(output_type, validation_context)
        # Never replay history or use ModelRetry: each attempt must have exactly
        # one leading system message followed by a user message for Prism/Bonsai.
        try:
            retry_options = (
                {"model_settings": retry_model_settings}
                if attempt and retry_model_settings is not None
                else {}
            )
            result = await agent.run(retry_prompt, event_stream_handler=guard, **retry_options)
            finish_reason = getattr(getattr(result, "response", None), "finish_reason", None)
            output_length = len(result.output)
            usage = getattr(getattr(result, "response", None), "usage", None)
            input_tokens = getattr(usage, "input_tokens", None)
            output_tokens = getattr(usage, "output_tokens", None)
            parsed = parse_json_output(
                result.output, output_type, validation_context=validation_context
            )
            outcome = "valid"
            return parsed
        except (json.JSONDecodeError, ValidationError, UnexpectedModelBehavior) as exc:
            outcome = "invalid"
            if isinstance(exc, json.JSONDecodeError):
                feedback = f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}."
            elif isinstance(exc, ValidationError):
                feedback = "JSON does not match the schema: " + json.dumps(
                    exc.errors(include_input=False, include_url=False, include_context=False)
                )
            else:
                # PydanticAI rejects empty/thinking-only or otherwise unusable
                # responses before it can return text for json.loads.
                feedback = "No usable text output was returned. Return a complete JSON object."
            if finish_reason == "length":
                feedback += (
                    " The output was truncated at the token/context limit. Shorten scalar values "
                    "and lists substantially; avoid repetition and finish the entire JSON object."
                )
            logger.warning(
                "%s output failed validation (attempt %s/%s): %s; finish=%s; "
                "output_chars=%s; error_types=%s",
                output_type.__name__,
                attempt + 1,
                max_retries + 1,
                type(exc).__name__,
                finish_reason,
                max(output_length, len(guard.text)),
                sorted({error["type"] for error in exc.errors()})
                if isinstance(exc, ValidationError)
                else type(exc).__name__,
            )
            if attempt == max_retries:
                raise AgentJSONError(
                    f"{output_type.__name__} failed to return valid JSON matching its schema "
                    f"after {max_retries + 1} attempts. Please retry architecture generation."
                ) from exc
            retry_prompt = (
                f"{prompt}\n\nYour previous attempt failed validation. {feedback}\n"
                "Generate the complete answer again as valid JSON only, matching the "
                "JSON Schema in the system message. No Markdown or commentary."
            )
        finally:
            # Metadata only: do not log prompts, responses, clarifications or credentials.
            logger.info(
                "Agent timing run=%s stage=%s schema=%s attempt=%s outcome=%s "
                "seconds=%.3f input_tokens=%s output_tokens=%s output_chars=%s finish=%s",
                run_id,
                stage,
                output_type.__name__,
                attempt + 1,
                outcome,
                perf_counter() - started,
                input_tokens,
                output_tokens,
                max(output_length, len(guard.text)),
                finish_reason,
            )
    raise AssertionError("unreachable")
