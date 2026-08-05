"""
Tool definitions and dispatch.

Two halves:
  - DECLARATIONS: what the model is told exists. This is a schema, not code.
  - execute():    what actually runs when the model asks for a tool.

The model never touches your functions. It emits a name and a dictionary of
arguments, and your code decides what to do with that. Keeping those two things
clearly separate is most of what "tool use" means.
"""

import ast
import operator
import sys
import pathlib

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from data import edgar  # noqa: E402
from . import prompts  # noqa: E402


DECLARATIONS = [
    {
        "name": "get_company_facts",
        "description": (
            "Fetch reported financial data for a public company from SEC EDGAR XBRL. "
            "Returns revenue, cost of revenue, operating expense lines and income "
            "figures across recent periods, each tagged with its XBRL concept, "
            "start and end dates, form type and accession number. "
            "Call this before reporting any figure. Never state a financial number "
            "that did not come from this tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol, for example DDOG or SNOW.",
                }
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "calculate",
        "description": (
            "Evaluate an arithmetic expression and return the result. "
            "Use this for every calculation without exception, including simple ones. "
            "Do not compute values yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic only, for example (721400000 - 155200000) / 721400000 * 100",
                }
            },
            "required": ["expression"],
        },
    },
    {
        "name": "done",
        "description": (
            "Call this when the question is fully answered. "
            "Return structured output only, not a prose essay."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One or two sentence answer to the question.",
                },
                "figures": {
                    "type": "array",
                    "description": "Every financial figure cited in the answer.",
                    "items": prompts.FIGURE_SCHEMA,
                },
                "could_not_determine": {
                    "type": "array",
                    "description": "Parts of the question that could not be answered from fetched data.",
                    "items": {"type": "string"},
                },
            },
            "required": ["summary", "figures", "could_not_determine"],
        },
    },
]


# ---------------------------------------------------------------------------
# The calculator
#
# Note that this uses ast, not eval(). eval() on a string the model produced is
# arbitrary code execution triggered by model output. It would work fine for
# months and then one day it would not.
# ---------------------------------------------------------------------------
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Expression contains something that is not plain arithmetic")


def calculate(expression: str) -> dict:
    try:
        value = _safe_eval(ast.parse(expression, mode="eval"))
        return {"expression": expression, "result": round(float(value), 6)}
    except Exception as error:
        # Errors are returned to the model, not raised. A good agent recovers
        # from a bad tool call by trying a different one. It cannot do that if
        # your loop crashes.
        return {"expression": expression, "error": str(error)}


def execute(name: str, args: dict) -> dict:
    """Dispatch a tool call by name. Always returns a dict, never raises."""
    try:
        if name == "get_company_facts":
            return edgar.get_company_facts(args["ticker"])
        if name == "calculate":
            return calculate(args["expression"])
        if name == "done":
            return {"acknowledged": True}
        return {"error": f"No tool named {name}"}
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}"}