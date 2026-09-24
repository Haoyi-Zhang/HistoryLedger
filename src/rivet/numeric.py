from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Iterable

WEIGHT_QUANTUM = Decimal("0.000000000001")


def decimal_weight(value: object) -> Decimal:
    """Return the frozen twelve-place event weight or raise ``ValueError``.

    The evidence model treats the decimal representation at twelve fractional
    places as the canonical weight surface.  This avoids history-order-dependent
    binary floating-point accumulation while retaining the precision serialized
    by the public ledger.
    """
    try:
        candidate = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid numeric weight {value!r}") from exc
    if not candidate.is_finite():
        raise ValueError(f"nonfinite numeric weight {value!r}")
    try:
        with localcontext() as context:
            context.prec = 60
            return candidate.quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:
        raise ValueError(f"numeric weight outside canonical range {value!r}") from exc


def weight_units(value: object) -> int:
    """Return a canonical weight as an integer multiple of ``WEIGHT_QUANTUM``."""
    canonical = decimal_weight(value)
    sign, digits, exponent = canonical.as_tuple()
    if exponent != -12:
        raise ValueError(f"weight is not on the canonical surface: {value!r}")
    magnitude = int("".join(str(digit) for digit in digits) or "0")
    return -magnitude if sign else magnitude


def sum_weight_units(values: Iterable[object]) -> int:
    """Sum canonical weights as exact integer units, independent of order."""
    return sum(weight_units(value) for value in values)


def units_to_decimal(units: int) -> Decimal:
    if isinstance(units, bool) or not isinstance(units, int):
        raise ValueError("units must be an integer")
    return Decimal(f"{units}e-12")


def units_to_weight(units: int) -> float:
    """Convert exact internal units once to the public numeric report value."""
    return float(units_to_decimal(units))


def canonical_weight(value: object) -> float:
    return units_to_weight(weight_units(value))


def sum_weights(values: Iterable[object]) -> float:
    """Accumulate exact units, then convert once to a numeric report value."""
    return units_to_weight(sum_weight_units(values))


def format_units(units: int) -> str:
    return format(units_to_decimal(units), ".12f")


def format_weight(value: object) -> str:
    return format_units(weight_units(value))
