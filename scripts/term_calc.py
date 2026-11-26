"""数値条件の計算例の再計算(ゲートが検算に使う)。仮定値は assumed=true として実際の契約条件と区別する。"""
from decimal import Decimal, ROUND_FLOOR
def _yen(x): return int(Decimal(repr(round(x, 6))).to_integral_value(rounding=ROUND_FLOOR))   # 円未満切捨(計算例の表示規則。実契約の端数処理は契約条項に従う)
def recompute(ex):
    t, a = ex.get("type"), ex.get("assumptions") or {}
    try:
        if t == "annual_rate_over_days": return _yen(a["principal_yen"] * a["rate_percent"] / 100 * a["days"] / a.get("basis_days", 365))
        if t == "daily_rate_over_days": return _yen(a["amount_yen"] * a["daily_percent"] / 100 * a["days"])
        if t == "flat": return int(a["amount_yen"])
    except (KeyError, TypeError, ZeroDivisionError): return None
    return None
