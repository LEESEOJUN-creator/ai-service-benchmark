"""Credit arithmetic only. UI reading and settlement verification are external."""

from decimal import Decimal, InvalidOperation


def credit_delta(before, after, *, settled, concurrent_activity=False, display_step="1"):
    """Inputs must be normalized numeric strings, not locale-dependent UI labels."""
    if before is None or after is None:
        return {"status": "unavailable", "consumed": None}
    try:
        start, end, step = Decimal(str(before)), Decimal(str(after)), Decimal(str(display_step))
    except InvalidOperation:
        return {"status": "invalid_reading", "consumed": None}
    if not all(v.is_finite() for v in (start, end, step)) or min(start, end) < 0 or step <= 0:
        return {"status": "invalid_reading", "consumed": None}
    if concurrent_activity or end > start:
        return {"status": "contaminated", "consumed": None}
    if not settled:
        return {"status": "pending", "consumed": None}
    difference = start - end
    if difference == 0:
        return {"status": "zero_or_below_display_precision", "consumed": None, "displayed_delta": "0", "display_step": str(step)}
    return {"status": "observed", "consumed": str(difference), "display_step": str(step)}
