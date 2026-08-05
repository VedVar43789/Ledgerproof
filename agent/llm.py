"""
The provider abstraction layer.

Everything that knows about Gemini specifically lives in this file and nowhere
else. The loop, the tools, and the eval runner all talk to `chat()` and receive
the same shape back regardless of which provider is behind it.

This is not architecture for its own sake. In v2 you run the same evaluation
suite against Gemini and against a Sonnet-class model to show that your
verification layer works independent of model quality. If provider code has
leaked into the loop, that comparison becomes a refactor instead of an
afternoon.
"""

import os
import random
import time

from google import genai
from google.genai import types

# NOTE: verify this model string against the current model list in AI Studio.
# Model names change more often than SDK shapes do.
MODEL = os.environ.get("LEDGERPROOF_MODEL", "gemini-3-flash")

_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])


# ---------------------------------------------------------------------------
# Rate limiting
#
# The free tier is roughly 10 requests per minute and 250,000 tokens per minute.
# Requests per day is not your problem. Tokens per minute is, because the
# fetched EDGAR payload is resent on EVERY iteration of a trajectory. An eight
# step run can move 100k tokens in under a minute, so two runs back to back
# will hit the ceiling.
#
# A fixed minimum gap between calls is crude but sufficient at v0.
# ---------------------------------------------------------------------------
MIN_SECONDS_BETWEEN_CALLS = 6.0
_last_call_time = 0.0


def _throttle() -> None:
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call_time = time.time()


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    return "429" in text or "resource_exhausted" in text or "quota" in text


def chat(system_prompt: str, history: list, tool_declarations: list) -> dict:
    """
    One model call.

    `history` is the running conversation, in the provider's native format.
    Returns a normalized dict, one of:
        {"kind": "tool_call", "name": str, "args": dict, "raw": <content>}
        {"kind": "text",      "text": str,                "raw": <content>}

    Retries with exponential backoff and jitter on rate limit errors. Jitter
    matters when several requests are throttled at once, because without it
    they all retry at the same instant and get rejected together.
    """
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=tool_declarations)],
        # Passing explicit FunctionDeclaration objects rather than Python
        # callables means the SDK will NOT execute tools for us. That is the
        # entire point of v0: we want to write the loop by hand.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0,
    )

    for attempt in range(6):
        _throttle()
        try:
            response = _client.models.generate_content(
                model=MODEL,
                contents=history,
                config=config,
            )
            break
        except Exception as error:
            if not _is_rate_limit_error(error) or attempt == 5:
                raise
            delay = (2**attempt) + random.uniform(0, 1)
            print(f"    [rate limited, waiting {delay:.1f}s]")
            time.sleep(delay)

    content = response.candidates[0].content

    for part in content.parts or []:
        if getattr(part, "function_call", None):
            call = part.function_call
            return {
                "kind": "tool_call",
                "name": call.name,
                "args": dict(call.args or {}),
                "raw": content,
            }

    text = "".join(p.text for p in (content.parts or []) if getattr(p, "text", None))
    return {"kind": "text", "text": text, "raw": content}


def append_model_turn(history: list, raw_content) -> None:
    """Put the model's own message back into the conversation."""
    history.append(raw_content)


def append_tool_result(history: list, tool_name: str, result: dict) -> None:
    """Put a tool's output into the conversation so the model can see it."""
    history.append(
        types.Content(
            role="user",
            parts=[types.Part.from_function_response(name=tool_name, response=result)],
        )
    )


def user_message(text: str):
    return types.Content(role="user", parts=[types.Part(text=text)])