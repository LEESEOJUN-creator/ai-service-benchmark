"""Convert observed per-request charges to KRW using user-supplied rates."""

from decimal import Decimal, InvalidOperation


def _decimal(value, label, *, positive=False):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label}: 유효한 숫자가 필요합니다") from exc
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise ValueError(f"{label}: {'0보다 큰' if positive else '0 이상의'} 유한 숫자가 필요합니다")
    return number


def normalize_rates(rates):
    if rates is None:
        return {}
    if not isinstance(rates, dict):
        raise ValueError("환산율 파일은 서비스 ID: 원/크레딧 객체여야 합니다")
    return {service: _decimal(rate, f"{service} 환산율", positive=True)
            for service, rate in rates.items() if rate is not None}


def converted_cost(result, service, rates):
    """Return amount/rate/raw as Decimals, or None for genuinely unmeasured cost."""
    raw = result.get("cost")
    if raw is None:
        return None
    amount = _decimal(raw, f"{service} 차감량")
    unit = str(result.get("cost_unit") or "").strip().lower()
    if unit in {"krw", "원", "₩"}:
        rate = Decimal(1)
    elif unit in {"credit", "credits", "크레딧"}:
        if service not in rates:
            raise ValueError(f"{service}: 1크레딧당 원화 환산율이 없습니다. --rates 로 입력하세요")
        rate = rates[service]
    else:
        raise ValueError(f"{service}: 알 수 없는 차감 단위 {result.get('cost_unit')!r}; 임의 환산 금지")
    return {"krw": amount * rate, "raw": amount, "unit": unit, "rate": rate}


def krw_text(amount):
    return f"{amount:,.2f}".rstrip("0").rstrip(".") + "원"
