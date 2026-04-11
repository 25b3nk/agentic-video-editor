"""
Expression evaluator for workflow `{{...}}` syntax.

Expressions can appear in step inputs and conditions. They reference:
  - {{param_name}}                        User parameter
  - {{analysis.beat_detection.beats[0]}} Analysis result
  - {{steps.step_id.output_name}}        Previous step output
  - {{video.duration}}                    Source video metadata (alias for analysis.metadata)

Expressions can also contain arithmetic and comparisons:
  - {{beat_1}} - 0.5
  - {{analysis.metadata.width}} > {{analysis.metadata.height}}
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.engine.executor import ExecutionContext

_EXPR_PATTERN = re.compile(r"\{\{(.+?)\}\}")


def resolve_path(obj: Any, path: str) -> Any:
    """Navigate a nested dict/list with dot and bracket notation.

    e.g. "beat_detection.beats[0]" on {"beat_detection": {"beats": [1.5, 3.0]}}
    returns 1.5.
    """
    parts = re.split(r"\.|\[|\]", path)
    for part in parts:
        if part == "":
            continue
        if isinstance(obj, dict):
            obj = obj[part]
        elif isinstance(obj, list):
            obj = obj[int(part)]
        else:
            raise KeyError(f"Cannot navigate '{part}' on {type(obj).__name__}")
    return obj


def _resolve_variable(name: str, ctx: "ExecutionContext") -> Any:
    """Resolve a single variable name against the execution context."""
    if name.startswith("analysis.metadata."):
        # Shorthand: analysis.metadata.X == video.X
        sub = name[len("analysis."):]
        return resolve_path(ctx.analysis, sub)
    if name.startswith("analysis."):
        return resolve_path(ctx.analysis, name[len("analysis."):])
    if name.startswith("steps."):
        # steps.step_id.output_name
        rest = name[len("steps."):]
        dot = rest.index(".")
        step_id = rest[:dot]
        output_name = rest[dot + 1:]
        return resolve_path(ctx.step_outputs.get(step_id, {}), output_name)
    if name.startswith("video."):
        # Alias for analysis.metadata.*
        sub = name[len("video."):]
        return resolve_path(ctx.analysis.get("metadata", {}), sub)
    # Plain parameter name
    if name in ctx.params:
        return ctx.params[name]
    raise KeyError(f"Unknown variable: '{name}'")


def evaluate(expression: str, ctx: "ExecutionContext") -> Any:
    """
    Evaluate an expression string.

    If the entire string is a single `{{...}}` token, return the native value.
    Otherwise interpolate all tokens and return a string (or evaluate arithmetic).
    """
    expression = expression.strip()
    matches = list(_EXPR_PATTERN.finditer(expression))

    if not matches:
        # Pure literal — try to coerce to number, else return as-is
        return _try_coerce(expression)

    # Single token with no surrounding text → return native value
    if len(matches) == 1 and matches[0].start() == 0 and matches[0].end() == len(expression):
        return _resolve_variable(matches[0].group(1).strip(), ctx)

    # Multiple tokens or tokens embedded in text → interpolate then evaluate
    interpolated = expression
    for m in reversed(matches):  # reverse so positions stay valid
        value = _resolve_variable(m.group(1).strip(), ctx)
        interpolated = interpolated[: m.start()] + str(value) + interpolated[m.end():]

    # Normalize YAML-style literals before evaluating as Python
    interpolated_for_eval = _normalize_literals(interpolated)

    # Try to evaluate as a Python expression (arithmetic / comparisons)
    try:
        tree = ast.parse(interpolated_for_eval, mode="eval")
        # Safety: only allow safe node types
        _assert_safe_ast(tree)
        return eval(compile(tree, "<expr>", "eval"))  # noqa: S307
    except Exception:
        return interpolated


def _try_coerce(value: str) -> Any:
    """Try to convert a literal string to a Python value."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() == "null":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    # Handle list/dict/tuple literals like [], [1,2,3], {}
    try:
        coerced = ast.literal_eval(value)
        if isinstance(coerced, (list, dict, tuple)):
            return coerced
    except (ValueError, SyntaxError):
        pass
    return value


_SAFE_NODES = {
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.And, ast.Or, ast.Not, ast.IfExp,
    ast.Name, ast.Load,  # needed for None, True, False literals
}

# Only these names are allowed in expressions (Python builtins used as literals)
_SAFE_NAME_IDS = {"None", "True", "False"}

# Normalize YAML-style literals to their Python equivalents
_NULL_PATTERN = re.compile(r"\bnull\b")
_TRUE_PATTERN = re.compile(r"\btrue\b")
_FALSE_PATTERN = re.compile(r"\bfalse\b")


def _normalize_literals(text: str) -> str:
    """Replace YAML null/true/false with Python None/True/False in non-token text."""
    text = _NULL_PATTERN.sub("None", text)
    text = _TRUE_PATTERN.sub("True", text)
    text = _FALSE_PATTERN.sub("False", text)
    return text


def _assert_safe_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in _SAFE_NAME_IDS:
            raise ValueError(f"Unsafe name reference: {node.id!r}")
        elif type(node) not in _SAFE_NODES:
            raise ValueError(f"Unsafe expression node: {type(node).__name__}")


def resolve_step_inputs(inputs: dict, ctx: "ExecutionContext") -> dict:
    """Recursively resolve all expressions in a step's inputs dict."""
    resolved = {}
    for key, value in inputs.items():
        resolved[key] = resolve_value(value, ctx)
    return resolved


def resolve_value(value: Any, ctx: "ExecutionContext") -> Any:
    """Resolve a single value that may be a string expression, dict, or list."""
    if isinstance(value, str):
        return evaluate(value, ctx)
    if isinstance(value, dict):
        return {k: resolve_value(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(v, ctx) for v in value]
    return value
