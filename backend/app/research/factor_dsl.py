"""Restricted, parsed factor-expression DSL.

Expressions are tokenized and parsed into a small immutable AST before any Polars
object is created.  The compiler deliberately has no escape hatch for source text.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Final, Literal, TypeAlias

import polars as pl

DSL_VERSION: Final = "factor-dsl-v2"
MAX_ROLLING_WINDOW: Final = 252

# Leakage gate threshold (FACT-04): |IC| between a clean factor and the displaced
# label must collapse to at most this.  Also used by admission's no_label_leakage
# stage; kept in the DSL so every DSL change re-verifies against it.
SHIFTED_LABEL_MAX_ABS_IC: Final = 0.02

# Governed/enriched numeric columns only.  Non-numeric identity and date columns
# are intentionally absent, so they cannot enter a factor expression.
ALLOWED_FIELDS: Final[frozenset[str]] = frozenset({
    "open", "high", "low", "close", "volume", "amount", "turnover_rate",
    "consecutive_limit_ups", "consecutive_limit_downs", "prev_close", "change_pct",
    "change_amount", "amplitude", "ma5", "ma10", "ma20", "ma30", "ma60",
    "ema5", "ema10", "ema20", "ema30", "ema60", "macd_dif", "macd_dea",
    "macd_hist", "boll_upper", "boll_lower", "kdj_k", "kdj_d", "kdj_j",
    "atr_14", "vol_ma5", "vol_ma10", "vol_ratio_5d", "high_60d", "low_60d",
    "momentum_5d", "momentum_10d", "momentum_20d", "momentum_30d", "momentum_60d",
    "annual_vol_20d", "rsi_6", "rsi_14", "rsi_24",
})

# Label/identity columns that carry forward-looking or per-row identity information.
# They are intentionally excluded from ALLOWED_FIELDS and denied explicitly so the
# diagnostic names the field instead of reporting a generic unknown field.
DENIED_FIELDS: Final[frozenset[str]] = frozenset({
    "date", "symbol", "label", "forward_return",
    "_forward_return", "_factor", "_rank", "_zscore",
})

_FUNCTION_ARITY: Final[dict[str, int]] = {
    "abs": 1,
    "sign": 1,
    "log1p": 1,
    "clip": 3,
    "rank": 1,
    "zscore": 1,
    "rolling_mean": 2,
}

PartitionContext: TypeAlias = Literal["pointwise", "per_date", "per_symbol"]

# Declared partition semantics for every stateful operator (FACT-04).  A function
# added to _FUNCTION_ARITY without a matching entry here is a compile error and
# fails the table-consistency test set(_FUNCTION_ARITY) == set(_FUNCTION_PARTITION).
_FUNCTION_PARTITION: Final[dict[str, PartitionContext]] = {
    "abs": "pointwise",
    "sign": "pointwise",
    "log1p": "pointwise",
    "clip": "pointwise",
    "rank": "per_date",          # matches .over("date") in _compile_node
    "zscore": "per_date",        # matches .over("date")
    "rolling_mean": "per_symbol",  # matches .over("symbol")
}


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """One-based source position for a validation diagnostic."""

    offset: int
    line: int
    column: int

    def display(self) -> str:
        return f"line {self.line}, column {self.column}"


@dataclass(frozen=True, slots=True)
class FactorDslDiagnostic:
    message: str
    location: SourceLocation

    def __str__(self) -> str:
        return f"{self.message} ({self.location.display()})"


class FactorDslError(ValueError):
    """Expression rejection raised before compilation can allocate a Polars Expr."""

    def __init__(self, message: str, location: SourceLocation) -> None:
        self.diagnostic = FactorDslDiagnostic(message, location)
        super().__init__(str(self.diagnostic))


@dataclass(frozen=True, slots=True)
class Number:
    value: float
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class Field:
    name: str
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class Unary:
    operator: str
    operand: Expression
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class Binary:
    operator: str
    left: Expression
    right: Expression
    location: SourceLocation


@dataclass(frozen=True, slots=True)
class Call:
    name: str
    arguments: tuple[Expression, ...]
    location: SourceLocation


Expression: TypeAlias = Number | Field | Unary | Binary | Call


@dataclass(frozen=True, slots=True)
class FactorFeatures:
    """Deterministic, explainable inputs for registry similarity ranking."""

    structural_signature: str
    shape_signature: str
    fields: frozenset[str]
    operators: frozenset[str]
    functions: frozenset[str]
    partition_context: frozenset[str]

    @property
    def operator_function_set(self) -> frozenset[str]:
        return self.operators | self.functions


@dataclass(frozen=True, slots=True)
class ParsedFactor:
    expression: Expression
    canonical_expression: str
    dsl_version: str
    features: FactorFeatures

    @property
    def referenced_fields(self) -> frozenset[str]:
        return self.features.fields

    def compile(self) -> pl.Expr:
        return compile_ast(self.expression)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    location: SourceLocation


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def _location(source: str, offset: int) -> SourceLocation:
    prefix = source[:offset]
    return SourceLocation(offset=offset, line=prefix.count("\n") + 1, column=offset - prefix.rfind("\n"))


def _tokenize(source: str) -> tuple[_Token, ...]:
    if not isinstance(source, str):
        raise TypeError("factor expression must be a string")
    tokens: list[_Token] = []
    offset = 0
    while offset < len(source):
        character = source[offset]
        if character.isspace():
            offset += 1
            continue
        location = _location(source, offset)
        if match := _NUMBER.match(source, offset):
            tokens.append(_Token("NUMBER", match.group(), location))
            offset = match.end()
            continue
        if match := _IDENTIFIER.match(source, offset):
            tokens.append(_Token("IDENTIFIER", match.group(), location))
            offset = match.end()
            continue
        if character in "+-*/(),":
            tokens.append(_Token(character, character, location))
            offset += 1
            continue
        raise FactorDslError(f"unsupported character {character!r}", location)
    tokens.append(_Token("EOF", "", _location(source, len(source))))
    return tuple(tokens)


class _Parser:
    def __init__(self, source: str) -> None:
        self._tokens = _tokenize(source)
        self._index = 0

    @property
    def current(self) -> _Token:
        return self._tokens[self._index]

    def _advance(self) -> _Token:
        token = self.current
        self._index += 1
        return token

    def _expect(self, kind: str, message: str) -> _Token:
        if self.current.kind != kind:
            raise FactorDslError(message, self.current.location)
        return self._advance()

    def parse(self) -> Expression:
        if self.current.kind == "EOF":
            raise FactorDslError("factor expression cannot be empty", self.current.location)
        expression = self._sum()
        if self.current.kind != "EOF":
            raise FactorDslError(f"unexpected token {self.current.value!r}", self.current.location)
        return expression

    def _sum(self) -> Expression:
        expression = self._product()
        while self.current.kind in {"+", "-"}:
            token = self._advance()
            expression = Binary(token.value, expression, self._product(), token.location)
        return expression

    def _product(self) -> Expression:
        expression = self._unary()
        while self.current.kind in {"*", "/"}:
            token = self._advance()
            expression = Binary(token.value, expression, self._unary(), token.location)
        return expression

    def _unary(self) -> Expression:
        if self.current.kind == "-":
            token = self._advance()
            return Unary("-", self._unary(), token.location)
        return self._primary()

    def _primary(self) -> Expression:
        token = self.current
        if token.kind == "NUMBER":
            self._advance()
            value = float(token.value)
            if not math.isfinite(value):
                raise FactorDslError("numeric literal must be finite", token.location)
            return Number(value, token.location)
        if token.kind == "IDENTIFIER":
            self._advance()
            if self.current.kind == "(":
                return self._call(token)
            _validate_field_name(token.value, token.location)
            return Field(token.value, token.location)
        if token.kind == "(":
            self._advance()
            expression = self._sum()
            self._expect(")", "expected ')' to close parenthesized expression")
            return expression
        raise FactorDslError("expected a numeric literal, governed field, function, or '('", token.location)

    def _call(self, name: _Token) -> Expression:
        if name.value not in _FUNCTION_ARITY:
            raise FactorDslError(f"unknown factor function {name.value!r}", name.location)
        self._expect("(", "expected '('")
        arguments: list[Expression] = []
        if self.current.kind != ")":
            arguments.append(self._sum())
            while self.current.kind == ",":
                self._advance()
                arguments.append(self._sum())
        self._expect(")", f"expected ')' after arguments to {name.value}")
        expected = _FUNCTION_ARITY[name.value]
        if len(arguments) != expected:
            raise FactorDslError(
                f"{name.value} expects {expected} argument{'s' if expected != 1 else ''}, got {len(arguments)}",
                name.location,
            )
        call = Call(name.value, tuple(arguments), name.location)
        _validate_call(call)
        return call


def _literal_number(expression: Expression, message: str, location: SourceLocation) -> float:
    if isinstance(expression, Number):
        return expression.value
    if isinstance(expression, Unary) and expression.operator == "-" and isinstance(expression.operand, Number):
        return -expression.operand.value
    raise FactorDslError(message, location)


def _validate_call(call: Call) -> None:
    if call.name not in _FUNCTION_PARTITION:
        raise FactorDslError(
            f"function {call.name!r} has no declared partition context "
            "(add an entry to _FUNCTION_PARTITION)",
            call.location,
        )
    if call.name == "clip":
        low = _literal_number(call.arguments[1], "clip lower bound must be a numeric literal", call.arguments[1].location)
        high = _literal_number(call.arguments[2], "clip upper bound must be a numeric literal", call.arguments[2].location)
        if low > high:
            raise FactorDslError("clip lower bound cannot exceed upper bound", call.location)
    elif call.name == "rolling_mean":
        window = _literal_number(call.arguments[1], "rolling_mean window must be an integer literal", call.arguments[1].location)
        if not window.is_integer() or not 1 <= window <= MAX_ROLLING_WINDOW:
            raise FactorDslError(
                f"rolling_mean window must be an integer from 1 to {MAX_ROLLING_WINDOW}", call.arguments[1].location
            )


def _denied_field_error(name: str, location: SourceLocation) -> FactorDslError:
    return FactorDslError(f"denied label/identity field {name!r} cannot enter a factor expression", location)


def _validate_field_name(name: str, location: SourceLocation) -> None:
    """Reject denied label/identity fields before the generic unknown-field path."""
    if name in DENIED_FIELDS:
        raise _denied_field_error(name, location)
    if name not in ALLOWED_FIELDS:
        raise FactorDslError(f"unknown governed numeric field {name!r}", location)


def _validate_expression(expression: Expression) -> None:
    if isinstance(expression, Number):
        if not math.isfinite(expression.value):
            raise FactorDslError("numeric literal must be finite", expression.location)
        return
    if isinstance(expression, Field):
        _validate_field_name(expression.name, expression.location)
        return
    if isinstance(expression, Unary):
        if expression.operator != "-":
            raise FactorDslError(f"unsupported unary operator {expression.operator!r}", expression.location)
        _validate_expression(expression.operand)
        return
    if isinstance(expression, Binary):
        if expression.operator not in {"+", "-", "*", "/"}:
            raise FactorDslError(f"unsupported binary operator {expression.operator!r}", expression.location)
        _validate_expression(expression.left)
        _validate_expression(expression.right)
        if expression.operator == "/" and _is_zero_literal(expression.right):
            raise FactorDslError("division by a literal zero is not allowed", expression.right.location)
        return
    if isinstance(expression, Call):
        if expression.name not in _FUNCTION_ARITY or len(expression.arguments) != _FUNCTION_ARITY[expression.name]:
            raise FactorDslError(f"invalid call to {expression.name!r}", expression.location)
        if expression.name not in _FUNCTION_PARTITION:
            raise FactorDslError(
                f"function {expression.name!r} has no declared partition context "
                "(add an entry to _FUNCTION_PARTITION)",
                expression.location,
            )
        for argument in expression.arguments:
            _validate_expression(argument)
        _validate_call(expression)
        return
    raise TypeError("expression is not a factor DSL AST node")


def _is_zero_literal(expression: Expression) -> bool:
    return (isinstance(expression, Number) and expression.value == 0) or (
        isinstance(expression, Unary) and isinstance(expression.operand, Number) and expression.operand.value == 0
    )


def _number_text(value: float) -> str:
    if value == 0:
        return "0"
    return format(value, ".15g")


def canonicalize(expression: Expression) -> str:
    """Serialize the validated AST without harmless whitespace or parentheses."""
    _validate_expression(expression)
    return _serialize(expression, 0, "")


def _serialize(expression: Expression, parent_precedence: int, side: str) -> str:
    if isinstance(expression, Number):
        return _number_text(expression.value)
    if isinstance(expression, Field):
        return expression.name
    if isinstance(expression, Call):
        return f"{expression.name}({', '.join(_serialize(arg, 0, '') for arg in expression.arguments)})"
    if isinstance(expression, Unary):
        text = f"-{_serialize(expression.operand, 3, 'right')}"
        return f"({text})" if parent_precedence > 3 else text
    if isinstance(expression, Binary):
        precedence = 1 if expression.operator in {"+", "-"} else 2
        left = _serialize(expression.left, precedence, "left")
        right_parent = precedence + 1 if expression.operator in {"-", "/"} else precedence
        right = _serialize(expression.right, right_parent, "right")
        text = f"{left} {expression.operator} {right}"
        return f"({text})" if precedence < parent_precedence else text
    raise TypeError("expression is not a factor DSL AST node")


def _ast_payload(expression: Expression, *, shape_only: bool) -> object:
    if isinstance(expression, Number):
        return {"kind": "number", "value": None if shape_only else _number_text(expression.value)}
    if isinstance(expression, Field):
        return {"kind": "field", "name": None if shape_only else expression.name}
    if isinstance(expression, Unary):
        return {"kind": "unary", "operator": expression.operator, "operand": _ast_payload(expression.operand, shape_only=shape_only)}
    if isinstance(expression, Binary):
        return {
            "kind": "binary", "operator": expression.operator,
            "left": _ast_payload(expression.left, shape_only=shape_only),
            "right": _ast_payload(expression.right, shape_only=shape_only),
        }
    if isinstance(expression, Call):
        return {
            "kind": "call", "name": expression.name,
            "arguments": [_ast_payload(arg, shape_only=shape_only) for arg in expression.arguments],
        }
    raise TypeError("expression is not a factor DSL AST node")


def _signature(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def extract_features(expression: Expression) -> FactorFeatures:
    """Return deterministic structural and dependency features for explainable ranking."""
    _validate_expression(expression)
    fields: set[str] = set()
    operators: set[str] = set()
    functions: set[str] = set()

    def visit(node: Expression) -> None:
        if isinstance(node, Field):
            fields.add(node.name)
        elif isinstance(node, Unary):
            operators.add(f"unary:{node.operator}")
            visit(node.operand)
        elif isinstance(node, Binary):
            operators.add(node.operator)
            visit(node.left)
            visit(node.right)
        elif isinstance(node, Call):
            functions.add(node.name)
            for argument in node.arguments:
                visit(argument)

    visit(expression)
    return FactorFeatures(
        structural_signature=_signature(_ast_payload(expression, shape_only=False)),
        shape_signature=_signature(_ast_payload(expression, shape_only=True)),
        fields=frozenset(fields),
        operators=frozenset(operators),
        functions=frozenset(functions),
        partition_context=_partition_context(expression),
    )


def _partition_context(expression: Expression) -> frozenset[str]:
    """Effective partition context: the union of every leaf operator's context.

    Fields and binary/unary operators are pointwise; a function call contributes
    its declared _FUNCTION_PARTITION context (the union collapses to pointwise
    when no stateful operator is present).
    """
    contexts: set[str] = set()

    def visit(node: Expression) -> None:
        if isinstance(node, Call):
            contexts.add(_FUNCTION_PARTITION[node.name])
            for argument in node.arguments:
                visit(argument)
        elif isinstance(node, Unary):
            visit(node.operand)
        elif isinstance(node, Binary):
            visit(node.left)
            visit(node.right)

    visit(expression)
    return frozenset(contexts) if contexts else frozenset({"pointwise"})


def parse_factor(source: str) -> ParsedFactor:
    """Parse and validate source text without constructing a Polars expression."""
    expression = _Parser(source).parse()
    _validate_expression(expression)
    return ParsedFactor(
        expression=expression,
        canonical_expression=canonicalize(expression),
        dsl_version=DSL_VERSION,
        features=extract_features(expression),
    )


def validate_factor(source: str) -> ParsedFactor:
    """Alias documenting a validation-only entry point."""
    return parse_factor(source)


def compile_factor(source: str) -> pl.Expr:
    """Validate then compile text via explicit AST dispatch only."""
    return parse_factor(source).compile()


def compile_ast(expression: Expression) -> pl.Expr:
    """Compile a validated AST through fixed Polars constructors and methods."""
    _validate_expression(expression)
    return _compile_node(expression)


def _compile_node(expression: Expression) -> pl.Expr:
    if isinstance(expression, Number):
        return pl.lit(expression.value)
    if isinstance(expression, Field):
        # Validation is repeated at this boundary: manually constructed ASTs do not
        # gain access to arbitrary columns.
        _validate_field_name(expression.name, expression.location)
        return pl.col(expression.name)
    if isinstance(expression, Unary):
        return -_compile_node(expression.operand)
    if isinstance(expression, Binary):
        left = _compile_node(expression.left)
        right = _compile_node(expression.right)
        if expression.operator == "+":
            return left + right
        if expression.operator == "-":
            return left - right
        if expression.operator == "*":
            return left * right
        if expression.operator == "/":
            return left / right
        raise FactorDslError(f"unsupported binary operator {expression.operator!r}", expression.location)
    if isinstance(expression, Call):
        arguments = tuple(_compile_node(argument) for argument in expression.arguments)
        if expression.name not in _FUNCTION_PARTITION:
            raise FactorDslError(
                f"function {expression.name!r} has no declared partition context "
                "(add an entry to _FUNCTION_PARTITION)",
                expression.location,
            )
        if expression.name == "abs":
            return arguments[0].abs()
        if expression.name == "sign":
            return arguments[0].sign()
        if expression.name == "log1p":
            return arguments[0].log1p()
        if expression.name == "clip":
            low = _literal_number(expression.arguments[1], "clip lower bound must be a numeric literal", expression.location)
            high = _literal_number(expression.arguments[2], "clip upper bound must be a numeric literal", expression.location)
            return arguments[0].clip(low, high)
        if expression.name == "rank":
            return arguments[0].rank().over("date")
        if expression.name == "zscore":
            value = arguments[0]
            return (value - value.mean().over("date")) / value.std().over("date")
        if expression.name == "rolling_mean":
            window = int(_literal_number(expression.arguments[1], "rolling_mean window must be an integer literal", expression.location))
            return arguments[0].rolling_mean(window_size=window, min_samples=1).over("symbol")
        raise FactorDslError(f"unknown factor function {expression.name!r}", expression.location)
    raise TypeError("expression is not a factor DSL AST node")


def shifted_label_ic(evaluated: pl.DataFrame, *, horizon: int) -> float:
    """Deterministic shifted-label leakage gate: IC with the label displaced one extra horizon.

    The label is displaced so it is misaligned with the factor: the forward return
    over ``[t + H, t + 2H]`` is correlated with the factor observed at ``t``.  A
    clean factor has no information about the misaligned window and its IC collapses
    to ~0; a lookahead factor that embeds future information shows nonzero IC.
    Returns ``abs(mean(per-date IC))`` and ``inf`` when no finite per-date
    correlation survives (an empty cross-section cannot be measured).  ``inf``
    is the documented fail-closed verdict: admission gate 2 treats it as a
    leakage failure (``inf <= SHIFTED_LABEL_MAX_ABS_IC`` is False), so a
    degenerate panel is REJECTED rather than silently admitted.  Consumers that
    distinguish "no data" from "strong leakage" must compare against ``inf``
    explicitly before interpreting the magnitude (IN-06).
    """
    displaced = evaluated.with_columns(
        (
            pl.col("close").shift(-2 * horizon).over("symbol")
            / pl.col("close").shift(-horizon).over("symbol")
            - 1.0
        ).alias("_shifted_label")
    )
    ic = displaced.group_by("date").agg(
        pl.corr(pl.col("_factor"), pl.col("_shifted_label")).alias("ic")
    )["ic"].drop_nulls()
    ic = ic.filter(ic.is_finite())
    return float(abs(ic.mean())) if len(ic) else float("inf")
