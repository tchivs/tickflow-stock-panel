"""Positive custom-strategy parser and capability-free instruction interpreter."""
from __future__ import annotations

import ast
import json
import math
from dataclasses import dataclass
from typing import Final, Mapping


STRATEGY_PROGRAM_SCHEMA: Final = "strategy-program-v1"
_MAX_SOURCE_BYTES: Final = 64 * 1024
_MAX_LITERAL_TEXT: Final = 512
_MAX_CONTAINER_ITEMS: Final = 64
_MAX_DEPTH: Final = 16
_MAX_INSTRUCTIONS: Final = 256
_MAX_INT_BITS: Final = 256
_MAX_RUNTIME_TEXT_BYTES: Final = 4 * 1024
_MAX_MAPPING_BYTES: Final = 16 * 1024
_VALUE_INTRINSICS: Final = frozenset({"abs", "min", "max", "round"})


class StrategyProgramViolation(ValueError):
    """Raised when source cannot be lowered into the positive instruction set."""

    code = "strategy_program_forbidden"


@dataclass(frozen=True, slots=True)
class StrategyInstruction:
    """One immutable value instruction with tuple-only operands."""

    opcode: str
    operands: tuple[object, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "opcode": self.opcode,
            "operands": [
                operand.to_payload() if isinstance(operand, StrategyInstruction) else operand
                for operand in self.operands
            ],
        }


@dataclass(frozen=True, slots=True)
class CompiledStrategyProgram:
    """Schema-versioned immutable IR; it never retains submitted source."""

    schema_version: str
    result: StrategyInstruction

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "result": self.result.to_payload(),
        }

    def interpret(self, panel: Mapping[str, object]) -> dict[str, object]:
        return StrategyProgramPolicy.execute(self, panel)


class StrategyProgramPolicy:
    """Lower one documented ``run(panel)`` subset into explicit value operations."""

    def compile(self, source: str) -> CompiledStrategyProgram:
        if not isinstance(source, str) or not source or len(source.encode("utf-8")) > _MAX_SOURCE_BYTES:
            raise StrategyProgramViolation("strategy source is empty or exceeds the bounded parser input")
        try:
            module = ast.parse(source, mode="exec")
        except SyntaxError as error:
            raise StrategyProgramViolation("strategy source is not valid syntax") from error
        if len(module.body) != 1 or not isinstance(module.body[0], ast.FunctionDef):
            raise StrategyProgramViolation("strategy source must contain only run(panel)")
        function = module.body[0]
        arguments = function.args
        if (
            function.name != "run"
            or function.decorator_list
            or function.returns is not None
            or function.type_comment is not None
            or arguments.posonlyargs
            or len(arguments.args) != 1
            or arguments.args[0].arg != "panel"
            or arguments.args[0].annotation is not None
            or arguments.vararg is not None
            or arguments.kwarg is not None
            or arguments.kwonlyargs
            or arguments.defaults
            or arguments.kw_defaults
        ):
            raise StrategyProgramViolation("run must accept exactly one undecorated panel argument")
        if len(function.body) != 1 or not isinstance(function.body[0], ast.Return):
            raise StrategyProgramViolation("run may contain only one return instruction")
        result = self._lower(function.body[0].value, depth=0)
        if result.opcode != "mapping":
            raise StrategyProgramViolation("run must return a mapping instruction")
        program = CompiledStrategyProgram(STRATEGY_PROGRAM_SCHEMA, result)
        self.validate(program)
        return program

    def _lower(self, node: ast.expr | None, *, depth: int) -> StrategyInstruction:
        if node is None or depth > _MAX_DEPTH:
            raise StrategyProgramViolation("strategy expression exceeds the positive instruction grammar")
        if isinstance(node, ast.Constant):
            value = node.value
            if value is not None and not isinstance(value, (bool, int, float, str)):
                raise StrategyProgramViolation("literal type is not allowed")
            if isinstance(value, float) and not math.isfinite(value):
                raise StrategyProgramViolation("numeric literals must be finite")
            if isinstance(value, str) and len(value) > _MAX_LITERAL_TEXT:
                raise StrategyProgramViolation("literal text exceeds the bounded instruction limit")
            return StrategyInstruction("literal", (value,))
        if isinstance(node, ast.Dict):
            if len(node.keys) > _MAX_CONTAINER_ITEMS:
                raise StrategyProgramViolation("result mapping exceeds the bounded item limit")
            items: list[object] = []
            for key_node, value_node in zip(node.keys, node.values, strict=True):
                if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                    raise StrategyProgramViolation("result mapping keys must be literal text")
                key = key_node.value
                if not key or len(key) > 64 or not key.replace("_", "").isalnum():
                    raise StrategyProgramViolation("result mapping key is not allowed")
                items.extend((key, self._lower(value_node, depth=depth + 1)))
            return StrategyInstruction("mapping", tuple(items))
        if isinstance(node, ast.Subscript):
            if not isinstance(node.value, ast.Name) or node.value.id != "panel":
                raise StrategyProgramViolation("only direct panel value lookup is allowed")
            if not isinstance(node.slice, ast.Constant) or not isinstance(node.slice.value, str):
                raise StrategyProgramViolation("panel lookup requires a literal field name")
            field = node.slice.value
            if not field or len(field) > 64 or not field.replace("_", "").isalnum():
                raise StrategyProgramViolation("panel field name is not allowed")
            return StrategyInstruction("panel_value", (field,))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _VALUE_INTRINSICS:
                raise StrategyProgramViolation("call is not a fixed value intrinsic")
            if node.keywords:
                raise StrategyProgramViolation("value intrinsics do not accept keyword arguments")
            arguments = tuple(self._lower(argument, depth=depth + 1) for argument in node.args)
            if node.func.id == "abs" and len(arguments) != 1:
                raise StrategyProgramViolation("abs expects one value")
            if node.func.id in {"min", "max"} and not 1 <= len(arguments) <= 8:
                raise StrategyProgramViolation(f"{node.func.id} expects one to eight values")
            if node.func.id == "round" and not 1 <= len(arguments) <= 2:
                raise StrategyProgramViolation("round expects one value and an optional precision")
            return StrategyInstruction("intrinsic", (node.func.id, *arguments))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
            opcode = {ast.UAdd: "positive", ast.USub: "negative", ast.Not: "not"}[type(node.op)]
            return StrategyInstruction(opcode, (self._lower(node.operand, depth=depth + 1),))
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)
        ):
            opcode = {
                ast.Add: "add",
                ast.Sub: "subtract",
                ast.Mult: "multiply",
                ast.Div: "divide",
                ast.Mod: "modulo",
            }[type(node.op)]
            instruction = StrategyInstruction(
                opcode,
                (
                    self._lower(node.left, depth=depth + 1),
                    self._lower(node.right, depth=depth + 1),
                ),
            )
            if opcode == "multiply":
                _validate_static_multiplication(instruction.operands)
            return instruction
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            if not 2 <= len(node.values) <= 8:
                raise StrategyProgramViolation("boolean instruction has invalid arity")
            return StrategyInstruction(
                "all" if isinstance(node.op, ast.And) else "any",
                tuple(self._lower(value, depth=depth + 1) for value in node.values),
            )
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
            operator = node.ops[0]
            if not isinstance(operator, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                raise StrategyProgramViolation("comparison operator is not allowed")
            opcode = {
                ast.Eq: "equal",
                ast.NotEq: "not_equal",
                ast.Lt: "less",
                ast.LtE: "less_equal",
                ast.Gt: "greater",
                ast.GtE: "greater_equal",
            }[type(operator)]
            return StrategyInstruction(
                opcode,
                (
                    self._lower(node.left, depth=depth + 1),
                    self._lower(node.comparators[0], depth=depth + 1),
                ),
            )
        if isinstance(node, ast.IfExp):
            return StrategyInstruction(
                "choose",
                (
                    self._lower(node.test, depth=depth + 1),
                    self._lower(node.body, depth=depth + 1),
                    self._lower(node.orelse, depth=depth + 1),
                ),
            )
        raise StrategyProgramViolation(f"{type(node).__name__} is outside the positive instruction grammar")

    @staticmethod
    def validate(program: CompiledStrategyProgram) -> None:
        """Validate immutable IR structure without evaluating submitted values."""
        if (
            not isinstance(program, CompiledStrategyProgram)
            or program.schema_version != STRATEGY_PROGRAM_SCHEMA
        ):
            raise StrategyProgramViolation("strategy program schema is unsupported")
        instruction_count = [0]
        _validate_instruction(
            program.result, depth=0, instruction_count=instruction_count
        )

    @staticmethod
    def execute(
        program: CompiledStrategyProgram, panel: Mapping[str, object]
    ) -> dict[str, object]:
        StrategyProgramPolicy.validate(program)
        try:
            safe_panel = _primitive_mapping(panel)
            result = _interpret(program.result, safe_panel, depth=0)
            if not isinstance(result, dict) or not result or "signal" not in result:
                raise StrategyProgramViolation("strategy result must contain a signal")
            return _primitive_mapping(result)
        except MemoryError as error:
            raise StrategyProgramViolation(
                "strategy evaluation exceeded its memory budget"
            ) from error


def _primitive(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value.bit_length() > _MAX_INT_BITS:
            raise StrategyProgramViolation("integer value exceeds the bounded limit")
        return value
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _MAX_RUNTIME_TEXT_BYTES:
            raise StrategyProgramViolation("text value exceeds the bounded limit")
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise StrategyProgramViolation("interpreter values must be finite primitives")


def _primitive_mapping(value: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(value, Mapping) or len(value) > _MAX_CONTAINER_ITEMS:
        raise StrategyProgramViolation("interpreter mapping is invalid")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or len(key) > 64:
            raise StrategyProgramViolation("interpreter mapping key is invalid")
        result[key] = _primitive(item)
    try:
        encoded = json.dumps(
            result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    except MemoryError as error:
        raise StrategyProgramViolation(
            "interpreter mapping exceeds the bounded limit"
        ) from error
    if len(encoded) > _MAX_MAPPING_BYTES:
        raise StrategyProgramViolation("interpreter mapping exceeds the bounded limit")
    return result


def _validate_static_multiplication(operands: tuple[object, ...]) -> None:
    if len(operands) != 2:
        return
    literal_values = [
        operand.operands[0]
        if isinstance(operand, StrategyInstruction)
        and operand.opcode == "literal"
        and len(operand.operands) == 1
        else None
        for operand in operands
    ]
    left, right = literal_values
    text = left if isinstance(left, str) else right if isinstance(right, str) else None
    count = right if isinstance(left, str) else left if isinstance(right, str) else None
    if (
        isinstance(text, str)
        and isinstance(count, int)
        and not isinstance(count, bool)
        and max(count, 0) * len(text.encode("utf-8")) > _MAX_RUNTIME_TEXT_BYTES
    ):
        raise StrategyProgramViolation("text multiplication exceeds the bounded limit")
    if (
        isinstance(left, int)
        and not isinstance(left, bool)
        and isinstance(right, int)
        and not isinstance(right, bool)
        and left
        and right
        and left.bit_length() + right.bit_length() - 1 > _MAX_INT_BITS
    ):
        raise StrategyProgramViolation(
            "integer multiplication exceeds the bounded limit"
        )


def _validate_instruction(
    instruction: StrategyInstruction,
    *,
    depth: int,
    instruction_count: list[int],
) -> None:
    if not isinstance(instruction, StrategyInstruction) or depth > _MAX_DEPTH:
        raise StrategyProgramViolation("instruction tree is invalid")
    instruction_count[0] += 1
    if instruction_count[0] > _MAX_INSTRUCTIONS:
        raise StrategyProgramViolation("instruction count exceeds the bounded limit")
    opcode = instruction.opcode
    operands = instruction.operands
    if not isinstance(opcode, str) or not isinstance(operands, tuple):
        raise StrategyProgramViolation("instruction shape is invalid")
    if opcode == "literal":
        if len(operands) != 1:
            raise StrategyProgramViolation("literal instruction is invalid")
        _primitive(operands[0])
        return
    if opcode == "mapping":
        if not operands or len(operands) % 2 != 0:
            raise StrategyProgramViolation("mapping instruction is invalid")
        for index in range(0, len(operands), 2):
            key = operands[index]
            if (
                not isinstance(key, str)
                or not key
                or len(key) > 64
                or not key.replace("_", "").isalnum()
            ):
                raise StrategyProgramViolation("mapping instruction key is invalid")
            _validate_instruction(
                operands[index + 1],
                depth=depth + 1,
                instruction_count=instruction_count,
            )
        return
    if opcode == "panel_value":
        if (
            len(operands) != 1
            or not isinstance(operands[0], str)
            or not operands[0]
            or len(operands[0]) > 64
            or not operands[0].replace("_", "").isalnum()
        ):
            raise StrategyProgramViolation("panel lookup instruction is invalid")
        return
    if opcode == "intrinsic":
        if not operands or not isinstance(operands[0], str):
            raise StrategyProgramViolation("intrinsic instruction is invalid")
        name = operands[0]
        arguments = operands[1:]
        if (
            name not in _VALUE_INTRINSICS
            or (name == "abs" and len(arguments) != 1)
            or (name in {"min", "max"} and not 1 <= len(arguments) <= 8)
            or (name == "round" and not 1 <= len(arguments) <= 2)
        ):
            raise StrategyProgramViolation("intrinsic instruction is invalid")
        for argument in arguments:
            _validate_instruction(
                argument, depth=depth + 1, instruction_count=instruction_count
            )
        return
    arity = {
        "positive": 1,
        "negative": 1,
        "not": 1,
        "add": 2,
        "subtract": 2,
        "multiply": 2,
        "divide": 2,
        "modulo": 2,
        "equal": 2,
        "not_equal": 2,
        "less": 2,
        "less_equal": 2,
        "greater": 2,
        "greater_equal": 2,
        "choose": 3,
    }
    if opcode in {"all", "any"}:
        valid_arity = 2 <= len(operands) <= 8
    else:
        valid_arity = opcode in arity and len(operands) == arity.get(opcode)
    if not valid_arity:
        raise StrategyProgramViolation(f"instruction opcode {opcode!r} is invalid")
    for operand in operands:
        _validate_instruction(
            operand, depth=depth + 1, instruction_count=instruction_count
        )


def _interpret(
    instruction: StrategyInstruction, panel: Mapping[str, object], *, depth: int
) -> object:
    if not isinstance(instruction, StrategyInstruction) or depth > _MAX_DEPTH:
        raise StrategyProgramViolation("instruction tree is invalid")

    def evaluate(operand: object) -> object:
        if not isinstance(operand, StrategyInstruction):
            raise StrategyProgramViolation("instruction operand is invalid")
        return _interpret(operand, panel, depth=depth + 1)

    opcode = instruction.opcode
    operands = instruction.operands
    if opcode == "literal" and len(operands) == 1:
        return _primitive(operands[0])
    if opcode == "mapping" and len(operands) % 2 == 0:
        return {
            str(operands[index]): evaluate(operands[index + 1])
            for index in range(0, len(operands), 2)
        }
    if opcode == "panel_value" and len(operands) == 1:
        field = str(operands[0])
        if field not in panel:
            raise StrategyProgramViolation(f"panel field {field!r} is unavailable")
        return _primitive(panel[field])
    values = tuple(evaluate(operand) for operand in operands if isinstance(operand, StrategyInstruction))
    if opcode == "intrinsic" and operands and isinstance(operands[0], str):
        name = operands[0]
        arguments = tuple(evaluate(operand) for operand in operands[1:])
        if name == "abs":
            return abs(arguments[0])
        if name == "min":
            return min(arguments)
        if name == "max":
            return max(arguments)
        if name == "round":
            return round(*arguments)
    if len(values) == 1:
        if opcode == "positive":
            return +values[0]  # type: ignore[operator]
        if opcode == "negative":
            return -values[0]  # type: ignore[operator]
        if opcode == "not":
            return not values[0]
    if len(values) == 2:
        left, right = values
        if opcode == "multiply":
            text = (
                left
                if isinstance(left, str)
                else right
                if isinstance(right, str)
                else None
            )
            count = (
                right
                if isinstance(left, str)
                else left
                if isinstance(right, str)
                else None
            )
            if (
                isinstance(text, str)
                and isinstance(count, int)
                and not isinstance(count, bool)
                and max(count, 0) * len(text.encode("utf-8"))
                > _MAX_RUNTIME_TEXT_BYTES
            ):
                raise StrategyProgramViolation(
                    "text multiplication exceeds the bounded limit"
                )
        operations = {
            "add": lambda: left + right,  # type: ignore[operator]
            "subtract": lambda: left - right,  # type: ignore[operator]
            "multiply": lambda: left * right,  # type: ignore[operator]
            "divide": lambda: left / right,  # type: ignore[operator]
            "modulo": lambda: left % right,  # type: ignore[operator]
            "equal": lambda: left == right,
            "not_equal": lambda: left != right,
            "less": lambda: left < right,  # type: ignore[operator]
            "less_equal": lambda: left <= right,  # type: ignore[operator]
            "greater": lambda: left > right,  # type: ignore[operator]
            "greater_equal": lambda: left >= right,  # type: ignore[operator]
        }
        if opcode in operations:
            try:
                return _primitive(operations[opcode]())
            except (ArithmeticError, TypeError) as error:
                raise StrategyProgramViolation("value operation failed") from error
    if opcode == "all":
        return all(values)
    if opcode == "any":
        return any(values)
    if opcode == "choose" and len(values) == 3:
        return values[1] if values[0] else values[2]
    raise StrategyProgramViolation(f"instruction opcode {opcode!r} is invalid")
