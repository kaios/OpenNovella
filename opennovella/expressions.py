"""Safe evaluation of conditions, values and variable statements.

Story authors write small expressions such as ``courage >= 3`` or
``met_alice and not angry``. These are evaluated with a tiny whitelist-based
interpreter built on Python's ``ast`` module - arbitrary Python code is never
executed, so stories downloaded from strangers are safe to play.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any, Mapping

__all__ = ["ExpressionError", "evaluate", "parse_value", "run_statements",
           "apply_operation", "interpolate", "check_expression", "names_in"]


class ExpressionError(Exception):
    pass


_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_CMP_OPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
}
_UNARY_OPS = {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos}

# Friendly spellings beginners tend to type.
_CONSTANTS = {"true": True, "false": False, "yes": True, "no": False,
              "none": None, "null": None}
_FUNCTIONS = {"min": min, "max": max, "abs": abs, "round": round,
              "len": len, "int": int, "str": str}

_MAX_POW = 1000


_STRING_RE = re.compile(r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""")


def _normalise(text: str) -> str:
    # Allow &&, || and ! for people coming from other languages, without
    # touching anything inside quoted text.
    parts = _STRING_RE.split(text)
    for i in range(0, len(parts), 2):
        p = parts[i].replace("&&", " and ").replace("||", " or ")
        parts[i] = re.sub(r"!(?!=)", " not ", p)
    return "".join(parts).strip()


def _parse(text: str, mode: str = "eval") -> ast.AST:
    try:
        return ast.parse(_normalise(text), mode=mode)
    except SyntaxError as exc:
        raise ExpressionError(f"Could not understand “{text}” ({exc.msg}).") from None


class _Evaluator:
    def __init__(self, variables: Mapping[str, Any], strict: bool):
        self.variables = variables
        self.strict = strict

    def eval(self, node: ast.AST) -> Any:
        method = getattr(self, "_" + type(node).__name__, None)
        if method is None:
            raise ExpressionError(f"“{type(node).__name__}” is not allowed in expressions.")
        return method(node)

    def _Expression(self, node):
        return self.eval(node.body)

    def _Constant(self, node):
        if isinstance(node.value, (int, float, str, bool)) or node.value is None:
            return node.value
        raise ExpressionError("Unsupported value.")

    def _Name(self, node):
        name = node.id
        if name in self.variables:
            return self.variables[name]
        if name.lower() in _CONSTANTS:
            return _CONSTANTS[name.lower()]
        if name in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[name]
        if self.strict:
            raise ExpressionError(f"Unknown variable “{name}”.")
        return 0  # forgiving default: unknown variables count as 0 / false

    def _BoolOp(self, node):
        if isinstance(node.op, ast.And):
            result = True
            for v in node.values:
                result = self.eval(v)
                if not result:
                    return result
            return result
        result = False
        for v in node.values:
            result = self.eval(v)
            if result:
                return result
        return result

    def _BinOp(self, node):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ExpressionError("Unsupported operator.")
        left, right = self.eval(node.left), self.eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POW:
            raise ExpressionError("Number too large.")
        if isinstance(node.op, ast.Add) and (isinstance(left, str) or isinstance(right, str)):
            return f"{left}{right}"
        try:
            return op(left, right)
        except ZeroDivisionError:
            raise ExpressionError("Division by zero.") from None
        except TypeError as exc:
            raise ExpressionError(str(exc)) from None

    def _UnaryOp(self, node):
        return _UNARY_OPS[type(node.op)](self.eval(node.operand))

    def _Compare(self, node):
        left = self.eval(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.eval(comp)
            fn = _CMP_OPS.get(type(op))
            if fn is None:
                raise ExpressionError("Unsupported comparison.")
            try:
                if not fn(left, right):
                    return False
            except TypeError:
                return False
            left = right
        return True

    def _IfExp(self, node):
        return self.eval(node.body) if self.eval(node.test) else self.eval(node.orelse)

    def _Call(self, node):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS or node.keywords:
            raise ExpressionError("Only min, max, abs, round, len, int and str can be called.")
        args = [self.eval(a) for a in node.args]
        try:
            return _FUNCTIONS[node.func.id](*args)
        except (TypeError, ValueError) as exc:
            raise ExpressionError(str(exc)) from None

    def _List(self, node):
        return [self.eval(e) for e in node.elts]

    _Tuple = _List


def evaluate(text: Any, variables: Mapping[str, Any] | None = None,
             strict: bool = False) -> Any:
    """Evaluate an expression string against the given variables."""
    if not isinstance(text, str):
        return text
    if not text.strip():
        return None
    return _Evaluator(variables or {}, strict).eval(_parse(text))


def check_expression(text: str) -> str | None:
    """Return an error message if the expression is invalid, else None."""
    try:
        tree = _parse(text)
        _Evaluator({}, strict=False).eval(tree)
    except ExpressionError as exc:
        msg = str(exc)
        # Runtime-only problems (types, division) are fine at edit time.
        if msg.startswith(("Could not understand", "“", "Only", "Unsupported")):
            return msg
    except Exception:  # pragma: no cover - defensive
        return None
    return None


def names_in(text: str) -> set[str]:
    """Variable names used by an expression."""
    try:
        tree = _parse(text)
    except ExpressionError:
        return set()
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    calls = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {n for n in names - calls
            if n.lower() not in _CONSTANTS and n not in ("True", "False", "None")}


def parse_value(text: Any, variables: Mapping[str, Any] | None = None) -> Any:
    """Evaluate a value; bare words that aren't variables become plain text."""
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    if stripped == "":
        return ""
    try:
        return evaluate(stripped, variables, strict=True)
    except ExpressionError:
        # e.g. the author typed  Sam  instead of  "Sam"
        return stripped


def apply_operation(current: Any, operation: str, value: Any) -> Any:
    if operation in ("=", "", None):
        return value
    if current is None:
        current = 0
    try:
        if operation == "+=":
            if isinstance(current, str) or isinstance(value, str):
                return f"{current}{value}"
            return current + value
        if operation == "-=":
            return current - value
        if operation == "*=":
            return current * value
        if operation == "/=":
            return current / value
    except (TypeError, ZeroDivisionError) as exc:
        raise ExpressionError(f"Cannot apply {operation} to {current!r} and {value!r}: {exc}") from None
    raise ExpressionError(f"Unknown operation “{operation}”.")


_STATEMENT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(=|\+=|-=|\*=|/=)\s*(.+?)\s*$")


def parse_statements(text: str) -> list[tuple[str, str, str]]:
    """Split ``"a = 1; b += 2"`` into [(name, op, value_text), ...]."""
    out = []
    for part in re.split(r"[;\n]", text or ""):
        if not part.strip():
            continue
        m = _STATEMENT_RE.match(part)
        if not m or m.group(2) == "=" and m.group(3).startswith("="):
            raise ExpressionError(
                f"“{part.strip()}” should look like  name = value  or  name += 1")
        out.append((m.group(1), m.group(2), m.group(3)))
    return out


def run_statements(text: str, variables: dict[str, Any]) -> None:
    """Execute effect statements such as ``courage += 1; met_bob = true``."""
    for name, op, value_text in parse_statements(text):
        value = parse_value(value_text, variables)
        variables[name] = apply_operation(variables.get(name), op, value)


_INTERP_RE = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _format(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def interpolate(text: str, variables: Mapping[str, Any]) -> str:
    """Replace ``{name}`` with the variable's value. ``{{`` gives a literal brace."""
    if not text or "{" not in text and "}" not in text:
        return text

    def repl(m: re.Match) -> str:
        tok = m.group(0)
        if tok == "{{":
            return "{"
        if tok == "}}":
            return "}"
        name = m.group(1)
        return _format(variables[name]) if name in variables else tok

    return _INTERP_RE.sub(repl, text)
