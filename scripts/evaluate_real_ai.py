#!/usr/bin/env python3
"""実AI出力を、実行前に確定した期待基準(tests/real_ai/expected.json)に照らして機械評価する(機械判定できる項目のみ)。
  evaluate_real_ai.py <case> <review.json> [--role first|verifier]
判断の質(法的妥当性)は評価しない。human_review の項目は一覧表示のみ。"""
import sys, os, json, re
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import review_gate as G, legal_sources as L
def evaluate(case, path):
    rv = json.load(open(path, encoding="utf-8")); ct = open(os.path.join(ROOT, "tests", "real_ai", case, "contract.txt"), encoding="utf-8").read(); out = {}
    F, eng = G.gate(rv, None, "2026-11-24", ct); errs = [f["message"] for f in F if f["severity"] == "error"]
    jc = {(j.get("clause") or ""): j for j in rv["judgments"]}; revs = rv.get("revisions", [])
    def rev_for(clause):
        ids = {j["id"] for j in rv["judgments"] if clause in (j.get("clause") or "")}; return [r for r in revs if r.get("judgment_id") in ids]
    asserted = any(s.get("asserted_applicable") for j in rv["judgments"] for s in j.get("statutes", []))
    if case == "C1":
        out["E1_取適法を断定しない"] = not asserted and all(not s.get("asserted_applicable") for j in rv["judgments"] for s in j.get("statutes", []))
        nr = {n["term_label"]: n for n in rv.get("numeric_reviews", [])}
        j4 = [j for j in rv["judgments"] if "第4条" in (j.get("clause") or "")]; ids4 = {j["id"] for j in j4}
        n4 = [n for n in rv.get("numeric_reviews", []) if n.get("judgment_id") in ids4]
        out["E2_第4条の負担者=相手方"] = bool(n4) and all(n["burden_on"] == "相手方" for n in n4)
        j3 = [j for j in rv["judgments"] if "第3条" in (j.get("clause") or "")]; ids3 = {j["id"] for j in j3}
        n3 = [n for n in rv.get("numeric_reviews", []) if n.get("judgment_id") in ids3]
        out["E3_第3条の負担者=当社かつ法定率扱いなし"] = all(n["burden_on"] == "当社" for n in n3) and all(x.get("kind") != "法定率" for j in j3 for x in j.get("numbers", [])) if n3 else None
        ta4 = [t for t in rv.get("term_assessments", []) if t["judgment_id"] in ids4]
        out["E4_第4条を大きさのみで違法無効としない/経済的合理性を評価"] = bool(ta4) and all(t["dimensions"]["economic_rationality"]["status"] == "評価済" for t in ta4) and not any(G.NUMBER_BIG_ONLY.search(json.dumps(t, ensure_ascii=False)) for t in ta4)
        out["E5_第1条・第9条に修正なし(第1条は枠組み不足の指摘を人間確認)"] = (not rev_for("第9条"))
        out["E5b_第1条への修正提案あり(要人間確認: 期待基準では修正不要の想定)"] = bool(rev_for("第1条"))
        j5 = [j for j in rv["judgments"] if "第5条" in (j.get("clause") or "")]; ids5 = {j["id"] for j in j5}
        ta5 = [t for t in rv.get("term_assessments", []) if t["judgment_id"] in ids5]
        out["E6_第5条(金型)を検討(修正要/判断保留)"] = bool(ta5) and all(t["revision_decision"] in ("修正要", "判断保留") for t in ta5)
        out["E7_ゲートPASS"] = not errs
    else:
        out["E1_修正0件または根拠あり(件数を記録)"] = len(revs)
        out["E2_取適法を断定しない"] = not asserted
    out["_revisions"] = len(revs); out["_tier"] = rv.get("risk_tier"); out["_gate_errors"] = errs
    return out
if __name__ == "__main__":
    print(json.dumps(evaluate(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=1))
