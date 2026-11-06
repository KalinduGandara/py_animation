"""Seed scoring for ``bouncekit batch --score`` (FR-603, FR-604).

A score is a small arithmetic expression over a render's metadata JSON, for example
``-abs(stats.blue - stats.pink)`` (closest race first). It is parsed with :mod:`ast`
and checked against a whitelist once; it is never passed to ``eval``. Higher scores
rank first.
"""

import ast
import math
import operator
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from bouncekit.errors import BouncekitError, ConfigError

__all__ = ["Score", "ScoreError", "compile_score", "rank"]

NAMES = ("duration", "frames", "seed", "sound_triggers")
"""Top-level metadata numbers a score may use by name."""
GROUPS = ("stats", "events", "params")
"""Metadata objects a score may read one field of, as ``group.field``."""

_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_CALLS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
}


class ScoreError(BouncekitError):
    """A score could not be computed for one render (missing value, bad arithmetic)."""


def _check(node: ast.AST, expr: str) -> None:
    """Raise ``ConfigError`` unless every node of the tree is on the whitelist."""

    def bad(what: str) -> ConfigError:
        return ConfigError(f"--score: {what} is not allowed in {expr!r}")

    if isinstance(node, ast.Expression):
        _check(node.body, expr)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise bad(f"constant {node.value!r}")
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in _BINARY:
            raise bad(f"operator {type(node.op).__name__}")
        _check(node.left, expr)
        _check(node.right, expr)
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY:
            raise bad(f"operator {type(node.op).__name__}")
        _check(node.operand, expr)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _CALLS:
            raise bad("this call")
        if node.keywords or not node.args:
            raise bad(f"{node.func.id}() without positional arguments")
        for arg in node.args:
            _check(arg, expr)
    elif isinstance(node, ast.Name):
        if node.id not in NAMES:
            raise bad(f"name {node.id!r} (use {', '.join(NAMES)} or {'/'.join(GROUPS)}.<field>)")
    elif isinstance(node, ast.Attribute):
        if not (isinstance(node.value, ast.Name) and node.value.id in GROUPS):
            raise bad("this attribute (only stats.<x>, events.<x>, params.<x>)")
        if node.attr.startswith("_"):
            raise bad(f"field {node.attr!r}")
    else:
        raise bad(type(node).__name__)


def _number(value: object, where: str) -> float:
    if isinstance(value, bool | int | float):
        return float(value)
    raise ScoreError(f"{where} is not a number: {value!r}")


@dataclass(frozen=True)
class Score:
    """A checked score expression; :meth:`evaluate` computes it for one metadata dict."""

    expr: str
    tree: ast.Expression

    def evaluate(self, metadata: Mapping[str, object]) -> float:
        """Return the score for ``metadata`` (a render's metadata JSON as a dict).

        Raises:
            ScoreError: if a value is missing or not a number, or the arithmetic fails
                or gives a non-finite result.
        """
        try:
            value = self._eval(self.tree.body, metadata)
        except (ArithmeticError, ValueError) as exc:
            raise ScoreError(f"{type(exc).__name__}: {exc}") from exc
        if not math.isfinite(value):
            raise ScoreError(f"score is not finite: {value!r}")
        return value

    def _eval(self, node: ast.expr, meta: Mapping[str, object]) -> float:
        if isinstance(node, ast.Constant):
            return _number(node.value, "constant")  # int/float, checked by _check
        if isinstance(node, ast.BinOp):
            return float(
                _BINARY[type(node.op)](self._eval(node.left, meta), self._eval(node.right, meta))
            )
        if isinstance(node, ast.UnaryOp):
            return _UNARY[type(node.op)](self._eval(node.operand, meta))
        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name)
            args = [self._eval(arg, meta) for arg in node.args]
            return float(_CALLS[node.func.id](*args))
        if isinstance(node, ast.Name):
            if node.id not in meta:
                raise ScoreError(f"metadata has no {node.id!r}")
            return _number(meta[node.id], node.id)
        assert isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
        group = meta.get(node.value.id)
        where = f"{node.value.id}.{node.attr}"
        if not isinstance(group, Mapping) or node.attr not in group:
            raise ScoreError(f"metadata has no {where}")
        return _number(group[node.attr], where)


def compile_score(expr: str) -> Score:
    """Parse and check a ``--score`` expression (see the module docstring).

    Raises:
        ConfigError: if it does not parse or uses anything outside the whitelist.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ConfigError(f"--score: cannot parse {expr!r}: {exc.msg}") from exc
    _check(tree, expr)
    return Score(expr, tree)


def rank(metas: Sequence[Mapping[str, object]], score: Score) -> list[dict[str, object]]:
    """Score each metadata dict (in job order) and return the ranking entries.

    Entries are ``{rank, video, seed, params, score, kept}`` sorted by score
    descending, equal scores in job order, unscorable ones last with ``score: None``
    and an ``error``. ``kept`` starts ``True`` for all.
    """
    scored: list[tuple[float, int, dict[str, object]]] = []
    failed: list[dict[str, object]] = []
    for index, meta in enumerate(metas):
        entry: dict[str, object] = {
            "rank": 0,
            "video": meta.get("video"),
            "seed": meta.get("seed"),
            "params": meta.get("params"),
            "score": None,
            "kept": True,
        }
        try:
            value = score.evaluate(meta)
        except ScoreError as exc:
            entry["error"] = str(exc)
            failed.append(entry)
            continue
        entry["score"] = value
        scored.append((-value, index, entry))
    scored.sort(key=lambda item: (item[0], item[1]))
    entries = [entry for _, _, entry in scored] + failed
    for position, entry in enumerate(entries, 1):
        entry["rank"] = position
    return entries
