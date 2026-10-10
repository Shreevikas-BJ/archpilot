"""Reject broken JSON prefixes early; never accept or truncate a partial answer."""

import json
import re

from pydantic import BaseModel
from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, TextPart, TextPartDelta
from pydantic_core import from_json


def loads_json(text: str):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise json.JSONDecodeError("Duplicate JSON object key", text, 0)
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=unique_object)


class JSONStreamGuard:
    def __init__(self, output_type: type[BaseModel], validation_context: dict | None = None):
        self.output_type = output_type
        self.validation_context = validation_context
        self.text = ""
        self.checked_length = 0

    def check(self) -> None:
        text = self.text.lstrip()
        if text.startswith("`"):
            # Wait for a complete opening fence. The final parser remains the
            # authority for unsupported fence styles and single-line fences.
            opening, newline, rest = text.partition("\n")
            if not newline or opening.strip().lower() not in {"```", "```json", "```code"}:
                return
            text = re.sub(r"(?<=[}\]])\s*`{1,3}\s*$", "", rest).lstrip()
        if not text.strip():
            return
        try:
            # Partial mode accepts incomplete strings, numbers, literals and
            # containers. Its returned partial value is NEVER used as output.
            from_json(text, allow_partial=True)
        except ValueError as exc:
            message = str(exc)
            # Be conservative about parser differences (Unicode surrogates,
            # numeric ranges, recursion limits). Abort only definite syntax errors.
            if message.startswith(
                (
                    "expected ",
                    "key must be a string",
                    "invalid escape",
                    "invalid unicode code point",
                    "control character",
                    "trailing comma",
                )
            ):
                raise json.JSONDecodeError("Invalid JSON syntax: " + message, text, 0) from exc
            return
        if text.startswith(("{", "[")):
            try:
                json.JSONDecoder().raw_decode(text)
            except json.JSONDecodeError:
                return  # Valid but unfinished prefix: keep generating.
            # A complete object cannot repair itself with more trailing tokens.
            # Validate it now, but still wait for the natural end of valid output.
            payload = loads_json(text)
            self.output_type.model_validate(payload, context=self.validation_context)

    async def __call__(self, ctx, events) -> None:
        async for event in events:
            if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                self.text += event.part.content
            elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                self.text += event.delta.content_delta
            else:
                continue
            if len(self.text) - self.checked_length >= 128:
                self.check()
                self.checked_length = len(self.text)
