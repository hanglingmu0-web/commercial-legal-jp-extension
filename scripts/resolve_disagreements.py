#!/usr/bin/env python3
"""初回レビューと独立再検証の不一致を分類し、10段階の解消工程を順に適用する。多数決・AIの一致は法的確定の根拠にしない。
  resolve_disagreements.py <案件dir(first/review.json, verifier/review_verifier.json, [adversarial/*.json])> --contract contract.txt [--facts facts.json] [--profile-loaded] [--out out.json]
分類(10): 表現のみ/リスク分類のみ/指摘理由/修正文案/修正要否/法令適用判定/権利義務認識/重大リスク認識/根拠資料認識/その他の実質的判断
  ・重大扱い: 修正要否・法令適用判定・権利義務認識・重大リスク認識(A/B該当の食い違い)
  ・『権利義務認識』『指摘理由』の食い違いは項目比較では判別できない → 本工程は検出せず、検証者・人間の読解に委ねる(『未検出』と明記。無いことの証明ではない)
解消工程: 1契約原文再確認 2当社の立場 3事実関係 4一次資料 5適用要件 6実務プロファイル 7数値・計算 8法的有効性/経済合理性 9追加の反証レビュー 10人間
結果: 解消(根拠付き) / 保守側で保留(Word反映せず・要確認) / 未解消→人間判断。未解消・保守側保留は select_revisions の --resolutions と連動して反映を止める。"""
import sys, os, json, re, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import compare_judgments as C, legal_sources as L, rules_v5 as R5
SERIOUS = {"修正要否", "法令適用判定", "権利義務認識", "重大リスク認識"}
def nkey(k):
    m = re.match(r"^(第[0-9０-９]+条)", k or ""); return m.group(1) if m else ("契約全体" if (k or "").startswith("契約全体") else k)
def norm(rv):
    rv = json.loads(json.dumps(rv))
    for j in rv.get("judgments", []): j["clause"] = nkey(j.get("clause"))
    return rv
def classify(field, a, b):
    if field == "条項の判断が片方のみ": return "その他の実質的判断", "判断単位(条項)の欠落: 片側が当該条項を判断していない"
    if field == "needs_revision": return "修正要否", "修正要否の食い違い(%s/%s)" % (a, b)
    if field == "asserted_applicable": return "法令適用判定", "法令適用の断定可否の食い違い"
    if field == "category":
        if (a in "AB") != (b in "AB"): return "重大リスク認識", "A/B(重大)該当の食い違い(%s/%s)" % (a, b)
        return "リスク分類のみ", "分類 %s/%s(同じ側のリスクを別名で分類)" % (a, b)
    if field == "status":
        if "確定" in (a, b): return "根拠資料認識", "一方が『確定』(根拠資料の十分性の認識差) %s/%s" % (a, b)
        return "表現のみ", "確度区分 %s/%s(結論の方向は同一か別項目で判定)" % (a, b)
    if field == "revisions_applied_to_word": return "修正文案", "Word反映可否の食い違い(%s/%s)" % (a, b)
    if field == "number_kinds": return ("法令適用判定" if "法定率" in (a or []) + (b or []) else "その他の実質的判断"), "数値の根拠区分の食い違い %s/%s" % (a, b)
    return "その他の実質的判断", field
def kind_of(field, cat, dep):
    """A=客観的に解消すべき(原文・数値・事実・網羅) / B=法的解釈・評価 / C=契約条件・経営判断(複数の合理的選択肢があり得る)"""
    if field in ("条項の判断が片方のみ", "number_kinds"): return "A"
    if field in ("asserted_applicable", "status", "category"): return "B"
    if field == "needs_revision": return "B" if dep else "C"
    if field == "revisions_applied_to_word": return "C"
    return "B"
def positions(fr, vr, k):
    out = []
    for lab, rv in (("初回レビュー", fr), ("独立再検証", vr)):
        js = [j for j in rv.get("judgments", []) if j.get("clause") == k]
        for j in js:
            ta = next((t for t in rv.get("term_assessments", []) if t.get("judgment_id") == j["id"]), {}); dm = ta.get("dimensions", {})
            g = lambda n: (dm.get(n) or {}).get("assessment")
            rv_ = [x for x in rv.get("revisions", []) if x.get("judgment_id") == j["id"]]
            out.append({"source": lab, "結論区分": j.get("conclusion_status"), "分類": j.get("category"), "要旨": j.get("summary"), "法的評価": g("legal_validity"), "経済的評価": g("economic_rationality"), "リスク配分": g("risk_allocation"), "交渉": g("negotiation"),
                        "修正案": [{"対象文言": x.get("original_text"), "修正文": x.get("revised_text"), "理由": x.get("reason")} for x in rv_] or "修正案なし", "修正不要の理由": ta.get("no_revision_reason")})
    return out
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("dir"); ap.add_argument("--contract", required=True); ap.add_argument("--facts"); ap.add_argument("--profile-loaded", action="store_true"); ap.add_argument("--out"); a = ap.parse_args()
    fr = norm(json.load(open(os.path.join(a.dir, "first", "review.json"), encoding="utf-8"))); vr = norm(json.load(open(os.path.join(a.dir, "verifier", "review_verifier.json"), encoding="utf-8")))
    text = open(a.contract, encoding="utf-8").read(); A, B, diffs = C.compare(fr, vr)
    adv = [f for f in (os.listdir(os.path.join(a.dir, "adversarial")) if os.path.isdir(os.path.join(a.dir, "adversarial")) else []) if f.endswith(".json")]
    app_overall = None
    if a.facts and os.path.isfile(a.facts):
        import applicability as AP; app_overall = AP.judge(json.load(open(a.facts, encoding="utf-8")))
    cache = {s: L.reliability(L.load(s)) for s in L.all_sources()}; firm_any = any("一次・原文(機械取得" in v for v in cache.values())
    rev = lambda r, k: [x for x in r.get("revisions", []) if (next((j for j in r["judgments"] if j["id"] == x.get("judgment_id")), {}) or {}).get("clause") == k]
    items = []
    clause_ne = {(k, f): (x, y) for k, f, x, y in diffs if f == "needs_revision"}
    for k, f, x, y in diffs:
        cat, why = classify(f, x, y); steps = []; res = None
        # 1 契約原文
        ok1 = (k in text) or k == "契約全体"; qs = [r.get("original_text") for rr in (fr, vr) for r in rev(rr, k) if r.get("original_text")]; miss = [q for q in qs if q not in text]
        steps.append(("1.契約原文再確認", "条項は原文に存在=%s / 修正対象文言の原文照合 不一致%d件" % (ok1, len(miss))))
        # 2,3
        steps.append(("2.当社の立場", "両者とも our_role=%s/%s %s" % (fr.get("our_role"), vr.get("our_role"), "(一致: 原因ではない)" if fr.get("our_role") == vr.get("our_role") else "(不一致: 原因候補)")))
        steps.append(("3.事実関係", "facts一致=%s %s" % (fr.get("facts") == vr.get("facts"), "(不一致の場合は事実の差が原因候補)")))
        dep = any(r.get("depends_on_statute") for rr in (fr, vr) for r in rev(rr, k)) or f in ("asserted_applicable",) or (f == "number_kinds" and cat == "法令適用判定")
        # 4 一次資料
        steps.append(("4.一次資料", ("当該論点は法令に依存。機械取得原文=%s → %s" % (firm_any, "確認可能" if firm_any else "未確認のため法令を根拠とする解消は不可")) if dep else "法令に依存しない論点(契約文言・事業判断)"))
        # 5 適用要件
        if dep:
            ov = app_overall and app_overall.get("overall")
            steps.append(("5.適用要件", "適用判定=%s → %s" % (ov, "適用が確定していないため法令前提の修正は採用しない(規則)" if (not ov or not ov.startswith("適用あり")) else "適用あり")))
        else: steps.append(("5.適用要件", "該当なし"))
        steps.append(("6.実務プロファイル", "適用可能" if a.profile_loaded else "不可: 当社プロファイル/プレイブック未読込(暫定基準のみ。当社基準としては扱わない)"))
        steps.append(("7.数値・計算", "数値の食い違いなし" if f != "number_kinds" else "数値の根拠区分の食い違い: 適用未確定の率は法定率にせず任意設定とする規則(review_gate)で判定可能"))
        steps.append(("8.法的有効性/経済合理性", "項目比較では判別不可(判断理由の読解が必要)"))
        steps.append(("9.追加反証レビュー", "実施済(%s)" % ",".join(adv) if adv else "未実施"))
        # 結果(多数決はしない)
        human = True; ca = "未解消→人間判断"
        if miss and f in ("needs_revision", "revisions_applied_to_word"): res = "原文と一致しない修正対象文言あり(誤引用)。当該修正は反映せず、文言を原文に合わせて再作成する"; ca = "未解消→人間判断"
        elif f == "number_kinds" and "法定率" not in (x or []) + (y or []):
            res = "数値の根拠区分は片側が記録していないだけで、法定率と任意設定の判定の食い違いはない(いずれも法定率とは扱っていない)。実務上の影響なし"; ca = "解消(影響なし)"; human = False
        elif cat in ("表現のみ", "リスク分類のみ") and (k, "needs_revision") not in clause_ne:
            res = "修正要否が同一で結論の方向は同じ。実務上の影響なし。分類基準の曖昧さとして review_criteria 改訂候補に記録"; ca = "解消(影響なし)"; human = False
        elif cat == "修正文案" and (k, "needs_revision") not in clause_ne:
            res = "要否は同一。Word反映は両者の合意がないため反映しない(保守側)。文言は人間が確認"; ca = "保守側で保留"
        elif dep and not (app_overall and str(app_overall.get("overall", "")).startswith("適用あり")):
            res = "法令適用が未確定のため、法令を前提とする修正・断定は採用しない(Word反映せず)。事実(資本金・従業員数)の確認後に再判定"; ca = "保守側で保留"
        elif cat in SERIOUS or cat == "根拠資料認識":
            res = "自動工程では解消できない(重大な食い違い)。%s" % ("反証レビュー結果を参照して人間が判断" if adv else "反証レビューを実施し、人間が判断") ; ca = "未解消→人間判断"
        else: res = "自動工程では解消できない"; ca = "未解消→人間判断"
        kd = kind_of(f, cat, dep)
        if miss and f in ("needs_revision", "revisions_applied_to_word"): kd = "A"   # 修正対象文言が原文と一致しない=客観的な誤り
        # v0.5: 条項・項の参照誤り(実在しない条/項、前項参照の誤り等)は契約書原文で客観的に判定できる → A型(取引判断=C型にしない)
        refbad = []
        for rr in (fr, vr):
            for x_ in rev(rr, k):
                if x_.get("mechanical_kind") == "clause_ref": refbad.append(x_.get("revision_id"))
                if re.search(r"(前項|前条|前各項|同条|同項)", x_.get("original_text", "")) and not re.search(r"(前項|前条|前各項|同条|同項)", x_.get("revised_text", "")): refbad.append(x_.get("revision_id"))   # 相対参照を明示参照へ改める修正は参照先の客観確認事項
                for cc, pp in R5.ref_targets(x_.get("revised_text", ""), k):
                    if R5.clause_block(text, cc) is None or (pp and not R5.paragraph_exists(text, cc, pp)): refbad.append(x_.get("revision_id"))
        if refbad and f in ("needs_revision", "revisions_applied_to_word", "その他"): kd = "A"
        if refbad and kd == "A" and not res: res = "条項参照の誤りは契約書原文で客観的に判定できる事項(A型)。原文の条・項番号と照合して解消する"
        pos = positions(fr, vr, k) if kd in ("B", "C") else None
        if kd == "B" and ca.startswith("未解消"): ca = "判断事項として提示(解釈併記)"; res = (res or "") + " 解消できない場合は各解釈の根拠・成立条件・実務上の影響(下記positions)を併記し、法務担当者が判断する"
        if kd == "C": ca = "判断事項として提示(選択肢)"; res = "契約条件・経営判断に関する食い違い。単一の結論に統合せず、双方の案と評価を提示する(下記positions)"; human = True
        items.append({"kind": kd, "positions": pos, "clause": k, "first": x, "verifier": y, "field": f, "category": cat, "serious": cat in SERIOUS, "cause_hint": why, "practical_impact": ("大(修正の採否・法令前提が変わる)" if cat in SERIOUS else "小〜中(結論の方向は同じ)"),
                      "resolvable_by_primary_source": "可(機械取得原文の取得後)" if dep else "不可(法令に依存しない)", "resolvable_by_profile": "可(プロファイル読込後)" if cat in ("修正要否", "重大リスク認識", "リスク分類のみ") else "限定的",
                      "steps": steps, "result": ca, "result_detail": res, "human_required": human})
    out = {"dir": a.dir, "items": items, "undetected_categories": ["権利義務認識", "指摘理由"], "note": "多数決・AIの一致は根拠にしていない。『未検出』カテゴリは項目比較で判別できず、無いことの証明ではない。",
           "summary": {"by_kind": {kk: sum(i["kind"] == kk for i in items) for kk in "ABC"}, "decision_items": sum(i["result"].startswith("判断事項") for i in items), "unresolved_objective": sum(i["kind"] == "A" and i["result"].startswith("未解消") for i in items), "total": len(items), "serious": sum(i["serious"] for i in items), "resolved": sum(i["result"].startswith("解消") for i in items), "hold_conservative": sum(i["result"] == "保守側で保留" for i in items), "human": sum(i["result"].startswith("未解消") for i in items)}}
    for i in items: print("%s %-8s %-10s %-16s → %s" % (i["kind"], i["clause"], i["field"], i["category"], i["result"]))
    print(json.dumps(out["summary"], ensure_ascii=False))
    if a.out: json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
if __name__ == "__main__": main()
