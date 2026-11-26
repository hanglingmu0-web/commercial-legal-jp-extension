#!/usr/bin/env python3
"""案件のリスク階層(light/standard/high)を、review.json から機械的に算定する。階層に応じて検証の厚みを変える(軽微な案件に過剰な検証をしない)。"""
import sys, os, json
POL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "risk_policy.json")
ORDER = {"light": 0, "standard": 1, "high": 2}
def compute(rv, policy=None):
    pol = policy or json.load(open(POL, encoding="utf-8")); reasons = []; tier = "light"
    def up(t, why):
        nonlocal tier
        if ORDER[t] > ORDER[tier]: tier = t
        reasons.append("%s: %s" % (t, why))
    hi = pol["high_if"]; cv = (rv.get("contract_value_yen") or 0)
    for j in rv.get("judgments", []):
        if j.get("category") in hi["categories"] and j.get("conclusion_status") != "判断保留": up("high", "%sが分類%s" % (j.get("id"), j.get("category")))
    revs = rv.get("revisions", [])
    for n in rv.get("numeric_reviews", []):
        up("standard", "数値条件『%s』あり" % n.get("term_label"))
        for ex in n.get("calc_examples", []):
            from term_calc import recompute
            r = recompute(ex)
            if r is not None and cv and r / cv >= hi["numeric_exposure_ratio_of_contract_value"]: up("high", "『%s』の計算例の負担額が契約金額の%.0f%%以上(仮定値に基づく)" % (n.get("term_label"), hi["numeric_exposure_ratio_of_contract_value"] * 100))
    if revs: up("standard", "修正提案あり")
    if hi.get("conditional_applicability_with_revision") and any(r.get("depends_on_statute") for r in revs): up("high", "法令適用に依存する修正提案あり")
    return tier, reasons
if __name__ == "__main__":
    t, r = compute(json.load(open(sys.argv[1], encoding="utf-8"))); print(t); [print(" -", x) for x in r]
