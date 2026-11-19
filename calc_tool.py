import ast
import math
import operator as _op
import re

__all__ = ["calculate"]

_MAX_LEN = 500
_MAX_NODES = 100
_MAX_EXP = 1000
_MAX_MAGNITUDE_LOG10 = 300
_MAX_FACTORIAL = 1000
_MAX_COMB = 10000
_MAX_INT_DIGITS = 1000

_BIN_OPS = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.FloorDiv: _op.floordiv,
    ast.Mod: _op.mod,
}

_UNARY_OPS = {
    ast.UAdd: _op.pos,
    ast.USub: _op.neg,
}

_CONSTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
}


def _pow(a: int | float, b: int | float) -> int | float:
    if isinstance(a, bool) or isinstance(b, bool):
        raise ValueError("boolean not allowed")
    if abs(b) > _MAX_EXP:
        raise ValueError(f"exponent exceeds limit ({_MAX_EXP})")
    if a != 0 and abs(a) > 1:
        est = abs(b) * math.log10(abs(a))
        if est > _MAX_MAGNITUDE_LOG10:
            raise ValueError("power result too large")
    return a ** b


def _fact(n: int | float) -> int:
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError("factorial requires non-negative integer")
    if n > _MAX_FACTORIAL:
        raise ValueError(f"factorial limit is {_MAX_FACTORIAL}")
    return math.factorial(n)


def _comb(n: int | float, k: int | float) -> int:
    if not (isinstance(n, int) and isinstance(k, int)) or n < 0 or k < 0:
        raise ValueError("comb requires non-negative integers")
    if n > _MAX_COMB or k > _MAX_COMB:
        raise ValueError(f"comb limit is {_MAX_COMB}")
    return math.comb(n, k)


def _perm(n: int | float, k: int | float | None = None) -> int:
    if not isinstance(n, int) or n < 0 or (k is not None and (not isinstance(k, int) or k < 0)):
        raise ValueError("perm requires non-negative integers")
    if n > _MAX_COMB or (k is not None and k > _MAX_COMB):
        raise ValueError(f"perm limit is {_MAX_COMB}")
    return math.perm(n, k)


def _gamma(x: int | float) -> float:
    if abs(x) > 170:
        raise ValueError("gamma input out of range (max 170)")
    return math.gamma(x)


def _round(x: int | float, ndigits: int | float | None = None) -> int | float:
    if ndigits is None:
        return round(x)
    if not isinstance(ndigits, int) or abs(ndigits) > 100:
        raise ValueError("round ndigits must be integer within [-100, 100]")
    return round(x, ndigits)


def _min(*args: int | float) -> int | float:
    if not args:
        raise ValueError("min requires at least 1 argument")
    return min(args) if len(args) > 1 else args[0]


def _max(*args: int | float) -> int | float:
    if not args:
        raise ValueError("max requires at least 1 argument")
    return max(args) if len(args) > 1 else args[0]


def _sum(*args: int | float) -> int | float:
    if not args:
        raise ValueError("sum requires at least 1 argument")
    return sum(args)


def _log(x: int | float, base: int | float | None = None) -> float:
    return math.log(x) if base is None else math.log(x, base)


def _cbrt(x: int | float) -> float:
    if hasattr(math, "cbrt"):
        return math.cbrt(x)
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


_FUNCS = {
    "abs": abs,
    "round": _round,
    "min": _min,
    "max": _max,
    "sum": _sum,
    "pow": _pow,
    "sqrt": math.sqrt,
    "cbrt": _cbrt,
    "isqrt": math.isqrt,
    "hypot": math.hypot,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sind": lambda d: math.sin(math.radians(d)),
    "cosd": lambda d: math.cos(math.radians(d)),
    "tand": lambda d: math.tan(math.radians(d)),
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "asinh": math.asinh,
    "acosh": math.acosh,
    "atanh": math.atanh,
    "radians": math.radians,
    "degrees": math.degrees,
    "log": _log,
    "ln": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "expm1": math.expm1,
    "log1p": math.log1p,
    "ceil": math.ceil,
    "floor": math.floor,
    "trunc": math.trunc,
    "factorial": _fact,
    "gamma": _gamma,
    "gcd": math.gcd,
    "lcm": math.lcm,
    "comb": _comb,
    "perm": _perm,
    "fmod": math.fmod,
    "remainder": math.remainder,
}


def _normalize(expr: str) -> str:
    s = expr.strip().strip("=").strip()
    s = (
        s.replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("π", "pi")
    )
    # Strip thousands commas (1,000,000 -> 1000000) without touching fn args max(1, 2)
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)
    # Convert standalone percentages (15% -> (15/100)) while keeping modulo (10 % 3)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%(?!\s*\d)", r"(\1/100)", s)
    # Implicit multiplication: 2pi -> 2*pi, 2(3+4) -> 2*(3+4), preserving sci-notation 1e-5
    s = re.sub(r"(?<=\d)\s*(?=(?!e[+-]?\d)[a-zA-Z(])", "*", s)
    s = re.sub(r"\)\s*(?=[a-zA-Z0-9(])", ")*", s)
    return s


def _eval_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError("only numeric constants allowed")

    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"unknown symbol '{node.id}'")

    if isinstance(node, ast.UnaryOp):
        fn = _UNARY_OPS.get(type(node.op))
        if fn is None:
            raise ValueError("unsupported unary operator")
        return fn(_eval_node(node.operand))

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.BitXor):
            raise ValueError("use ** for power, not ^")
        if isinstance(node.op, ast.Pow):
            return _pow(_eval_node(node.left), _eval_node(node.right))
        fn = _BIN_OPS.get(type(node.op))
        if fn is None:
            raise ValueError("unsupported operator")
        return fn(_eval_node(node.left), _eval_node(node.right))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("only direct function calls allowed")
        if node.keywords:
            raise ValueError("keyword arguments not supported")
        fn = _FUNCS.get(node.func.id)
        if fn is None:
            raise ValueError(f"unknown function '{node.func.id}'")
        args = [_eval_node(a) for a in node.args]
        return fn(*args)

    raise ValueError(f"disallowed syntax: {type(node).__name__}")


def _format_num(val: int | float) -> str:
    if isinstance(val, bool):
        raise ValueError("invalid result type")
    if isinstance(val, int):
        s = str(val)
        if len(s) > _MAX_INT_DIGITS:
            raise ValueError(f"integer result exceeds {_MAX_INT_DIGITS} digits")
        return s
    if math.isnan(val):
        raise ValueError("result is NaN (undefined)")
    if math.isinf(val):
        return "inf" if val > 0 else "-inf"
    return f"{val:.15g}"


def _eval_single(raw: str) -> str:
    if len(raw) > _MAX_LEN:
        raise ValueError(f"expression too long (max {_MAX_LEN} chars)")
    cleaned = _normalize(raw)
    if not cleaned:
        raise ValueError("empty expression")
    tree = ast.parse(cleaned, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_NODES:
        raise ValueError(f"expression too complex (max {_MAX_NODES} AST nodes)")
    res = _eval_node(tree)
    return f"{cleaned} = {_format_num(res)}"


def calculate(expression: str) -> str:
    if not isinstance(expression, str) or not expression.strip():
        return "error: expression is empty. Pass a math expression string."

    parts = [p.strip() for p in re.split(r"[;\n]+", expression) if p.strip()]
    if len(parts) > 10:
        return "error: too many expressions at once (max 10)."

    outputs: list[str] = []
    for part in parts:
        try:
            outputs.append(_eval_single(part))
        except ZeroDivisionError:
            return f"error: division by zero in '{part}'."
        except OverflowError:
            return f"error: numeric overflow in '{part}'."
        except SyntaxError:
            return f"error: invalid math syntax in '{part}'. Use standard operators (+, -, *, /, //, %, **) and math functions."
        except RecursionError:
            return "error: expression nested too deeply."
        except (ValueError, TypeError) as exc:
            return f"error: {exc}"

    return "\n".join(outputs)