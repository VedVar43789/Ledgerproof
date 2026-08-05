"""
The agent loop.

This file is the whole project in miniature. Everything else is supporting
infrastructure. If you understand this loop you understand what an agent is.

  1. Send the model the goal and the list of tools it is allowed to use.
  2. It replies with either a tool it wants, or a final answer.
  3. If it asked for a tool, run it and send the result back.
  4. Go to 2.
  5. Stop on done(), run verification, then print the result.

Nothing in here decides anything. It runs whatever the model asked for and
hands back the result. All the intelligence is on the other side of the API
call. That is worth sitting with, because it is the thing people get wrong when
they say an agent "has its own brain".
"""

import json

from . import llm
from . import prompts
from . import tools
from . import verify

MAX_ITERATIONS = 15


def _preview(value, limit: int = 220) -> str:
    """Tool results can be large. Print a readable summary, not the whole blob."""
    text = json.dumps(value, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + f" ... [{len(text)} chars total]"


def _structured_from_done_args(args: dict) -> dict:
    """Accept v1 structured done() or fall back when the model sends legacy prose."""
    if "summary" in args or "figures" in args:
        return {
            "summary": args.get("summary", ""),
            "figures": args.get("figures") or [],
            "could_not_determine": args.get("could_not_determine") or [],
        }

    legacy_answer = args.get("answer")
    if legacy_answer:
        return {
            "summary": legacy_answer,
            "figures": [],
            "could_not_determine": [
                "Structured figures were not provided. Nothing was verified."
            ],
        }

    return {
        "summary": "(model called done with no output)",
        "figures": [],
        "could_not_determine": ["No answer provided."],
    }


def run(question: str, verbose: bool = True) -> str:
    history = [llm.user_message(question)]
    fetched_snapshots: list[dict] = []
    calculate_history: list[dict] = []

    if verbose:
        print(f"\nQuestion: {question}\n" + "-" * 70)

    for step in range(1, MAX_ITERATIONS + 1):
        response = llm.chat(prompts.SYSTEM_PROMPT, history, tools.DECLARATIONS)

        # Case A: the model produced text instead of a tool call. Usually it is
        # reasoning aloud or trying to answer without calling done(). Nudge it.
        if response["kind"] == "text":
            if verbose:
                print(f"[{step}] model text: {response['text'][:200]}")
            llm.append_model_turn(history, response["raw"])
            history.append(
                llm.user_message(
                    "Continue using tools, and call done() with structured figures "
                    "when you have the answer."
                )
            )
            continue

        # Case B: a tool call.
        name, args = response["name"], response["args"]

        if verbose:
            print(f"[{step}] wants: {name}({json.dumps(args, default=str)[:120]})")

        if name == "done":
            structured = _structured_from_done_args(args)
            verified, unverified = verify.verify(
                structured,
                fetched_snapshots,
                calculate_history,
            )
            if verbose:
                print(
                    f"    verify() -> {len(verified)} passed, "
                    f"{len(unverified)} failed, "
                    f"{len(structured.get('could_not_determine') or [])} could not determine"
                )
            return verify.format_output(structured, verified, unverified)

        result = tools.execute(name, args)

        if name == "get_company_facts" and isinstance(result, dict) and "concepts" in result:
            fetched_snapshots.append(result)
        if name == "calculate" and isinstance(result, dict):
            calculate_history.append(result)

        if verbose:
            print(f"    -> {_preview(result)}")

        # The two-line heart of the loop: the model's request goes into the
        # transcript, then the real result goes in right after it. Next call,
        # the model sees both and decides what to do next.
        llm.append_model_turn(history, response["raw"])
        llm.append_tool_result(history, name, result)

    # The iteration cap exists because agents get stuck in loops. Without it,
    # a confused model will fetch the same data forever and quietly burn quota.
    return f"Stopped after {MAX_ITERATIONS} steps without a final answer."
