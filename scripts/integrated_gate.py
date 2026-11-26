#!/usr/bin/env python3
"""統合ゲート: 初回レビュー・独立再検証・反証レビューの突合と、リスク階層に応じた必須工程の確認。
  integrated_gate.py --first f.json --verifier v.json [--adversarial a.json] [--resolutions r.json] --contract c.txt [--cache-dir D] --out result.json
resolutions.json: {"不一致キー(条項/項目)": {"status":"解消|判断保留", "basis":"…"}, "ADV-1": {"decision":"採用|不採用","reason":"…"}}
合格は手続上の整合の確認にすぎず、法的判断の正確性を保証しない。
"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules_v5 as R5, review_gate as G, compare_judgments as CJ, risk_tier as RT, legal_sources as L
CHECKLIST = ["common_judgment", "missed_issues", "validity_vs_economics", "applicability_gaps", "logic_leaps", "no_revision_reasons", "new_risks"]
def adv_check(adv, ctext, cache_dir, err):
    ex = adv.get("examined") or {}
    miss = [k for k in CHECKLIST if k not in ex]
    if miss: err("反証レビュー: 検討項目%sの記録がない" % miss)
    f = adv.get("findings", [])
    if not f and not (adv.get("no_findings_reason") or "").strip(): err("反証レビュー: 指摘なしの場合は理由の記載が必要(検討した結果として問題なしと判断した根拠)")
    for x in f:
        g = x.get("grounds") or {}
        ok = False
        if g.get("contract_quote"): ok = L.norm(g["contract_quote"]) in ctext
        if g.get("source_id"):
            src = L.load(g["source_id"], cache_dir); ok = L.verify_quote(src, g.get("ref"), g.get("quote", ""), cache_dir) in ("MATCH", "MATCH_ON_TRANSCRIPT")
        if not ok: err("反証指摘%s: 根拠(契約書原文の引用または一次資料の引用)が確認できない(根拠のない反対意見は採用しない)" % x.get("id"))
        if x.get("recommended_revision") and not ok: err("反証指摘%s: 根拠なしに修正提案をしている" % x.get("id"))
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--first", required=True); ap.add_argument("--verifier"); ap.add_argument("--adversarial"); ap.add_argument("--resolutions")
    ap.add_argument("--contract", required=True); ap.add_argument("--cache-dir"); ap.add_argument("--today"); ap.add_argument("--out"); ap.add_argument("--disagreements"); ap.add_argument("--docx-report"); ap.add_argument("--records-dir"); a = ap.parse_args(); strict = not a.disagreements; partial = []; decisions = []
    ctext_raw = open(a.contract, encoding="utf-8").read(); ctext = L.norm(ctext_raw)
    first = json.load(open(a.first, encoding="utf-8")); res = json.load(open(a.resolutions, encoding="utf-8")) if a.resolutions else {}
    errs = []; info = []
    def err(m): errs.append(m)
    F1, _ = G.gate(first, a.cache_dir, a.today, ctext_raw); errs += ["[初回] " + f["message"] for f in F1 if f["severity"] == "error"]; info += ["[初回] " + f["message"] for f in F1 if f["severity"] != "error"]
    tier, why = RT.compute(first); declared = first.get("risk_tier", "standard"); tier = tier if RT.ORDER[tier] >= RT.ORDER[declared] else declared
    ver = json.load(open(a.verifier, encoding="utf-8")) if a.verifier and os.path.isfile(a.verifier) else None
    if tier in ("standard", "high") and ver is None:
        if strict: err("リスク階層%s: 独立再検証が未実施(%s)" % (tier, "; ".join(why)))
        else: partial.append("独立再検証が未実施(階層%s)" % tier)
    if ver is not None:
        F2, _ = G.gate(ver, a.cache_dir, a.today, ctext_raw); errs += ["[再検証] " + f["message"] for f in F2 if f["severity"] == "error"]; info += ["[再検証] " + f["message"] for f in F2 if f["severity"] != "error"]
        A_, B_, diffs = CJ.compare(first, ver)
        for k, field, x, y in diffs:
            key = "%s/%s" % (k, field); r = res.get(key)
            if field == "category": info.append("[分類不一致] %s 初回=%s 再検証=%s" % (k, x, y)); continue
            if not strict: continue   # 不一致の扱いはdisagreements.json(A/B/C分類)で判定する
            if not r or r.get("status") not in ("解消", "判断保留") or not (r.get("basis") or "").strip(): err("初回と再検証の不一致が放置されている: %s 初回=%s 再検証=%s(resolutionsで『解消(根拠)』または『判断保留』を記録すること)" % (key, x, y))
        for j in first.get("judgments", []):
            if (j.get("category") in ("A", "B") or tier == "high") and (j.get("clause") or j.get("id")) not in B_:
                m = "重大/高リスクの指摘%sが独立再検証で検証されていない" % (j.get("clause") or j.get("id"))
                if strict: err(m)
                else: partial.append(m)
    adv = None
    if tier == "high":
        if not a.adversarial or not os.path.isfile(a.adversarial):
            if strict: err("高リスク案件だが反証レビューが未実施")
            else: partial.append("高リスク案件だが反証レビューが未実施")
        else:
            adv = json.load(open(a.adversarial, encoding="utf-8")); adv_check(adv, ctext, a.cache_dir, err)
            for x in adv.get("findings", []):
                r = res.get(x.get("id"))
                if r and r.get("decision") == "要人間判断":
                    if (r.get("why_human") or "").strip() and r.get("options"): decisions.append("反証指摘%s: 人間判断が必要(理由: %s / 選択肢: %s)" % (x.get("id"), r["why_human"][:80], "; ".join(map(str, r["options"]))[:120]))
                    elif strict: err("反証指摘%s: 要人間判断なら理由と選択肢が必要" % x.get("id"))
                    else: decisions.append("反証指摘%s: 要人間判断だが理由/選択肢が未記載" % x.get("id"))
                    continue
                if r and r.get("decision") in ("採用", "不採用") and not (r.get("checks") or []):
                    m_ = "反証指摘%s: 採否の客観確認記録(checks: 契約原文/数値/事実/一次資料)がない" % x.get("id")
                    if strict: err(m_)
                    else: errs.append(m_)
                    continue
                if not r or r.get("decision") not in ("採用", "不採用") or not (r.get("reason") or "").strip():
                    if strict: err("反証指摘%sが未処理(採用/不採用と理由を記録すること)" % x.get("id"))
                    else: decisions.append("反証指摘%s(%s)の採否は未決(根拠: %s)" % (x.get("id"), x.get("severity", ""), (x.get("grounds") or {}).get("contract_quote", "")[:60]))
    status = None; unresolved_A = []
    if not strict:
        dj = json.load(open(a.disagreements, encoding="utf-8")); res_ = res
        for i in dj["items"]:
            if i["kind"] == "A" and i["result"].startswith("未解消") and not (res_.get("%s/%s" % (i["clause"], i["field"])) or {}).get("status") in ("解消",): unresolved_A.append("客観的不一致(未解消): %s/%s 初回=%s 再検証=%s" % (i["clause"], i["field"], i["first"], i["verifier"]))
            elif i["result"].startswith("判断事項"): decisions.append("%s型の判断事項: %s/%s" % (i["kind"], i["clause"], i["field"]))
        nonfirm = [m for m in info if "AI転記資料との照合のみ" in m]
        if nonfirm: partial.append("法令引用%d件がAI転記資料との照合のみ(機械取得原文との照合なし)" % len(nonfirm))
        dx = json.load(open(a.docx_report, encoding="utf-8")) if a.docx_report and os.path.isfile(a.docx_report) else None
        status = ("成果物検証失敗" if (dx and not dx.get("ok", True)) else "重大な不一致あり" if (errs or unresolved_A) else "一部検証不能" if partial else "判断事項付き完了" if decisions else "正常完了")
        errs_all = errs + unresolved_A
    if a.records_dir:   # v0.5: 最終結論だけでなく全記録(初回・再検証・反証・採否・Wordコメント)の未確認の法的判断の断定を検出する
        recs = R5.collect_records(a.records_dir)
        for sv in R5.scan_unverified_legal(recs): errs.append("未確認の法的判断の断定: %s『%s』" % (sv["where"], sv["sentence"]))
        for rel in ("word_revisions.json", "word_revisions_external.json"):
            pth = os.path.join(a.records_dir, rel)
        ex = os.path.join(a.records_dir, "word_revisions_external.json")
        if os.path.isfile(ex):
            for m_ in R5.external_leaks(json.load(open(ex, encoding="utf-8"))): errs.append(m_)
    out = {"tier": tier, "tier_reasons": why, "errors": errs + unresolved_A, "human_review_items": info, "decision_items": decisions, "unverifiable": partial, "status": status, "verifier_present": ver is not None, "adversarial_present": adv is not None,
           "pass": not (errs + unresolved_A) if status is None else status in ("正常完了", "判断事項付き完了"), "disclaimer": "合格は手続上の整合の確認であり、法的判断の正確性を保証しない。判断事項が残ることはシステムの異常ではない"}
    if a.out: json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for e in errs + unresolved_A: print("[error]", e)
    for i in info[:12]: print("[info]", i)
    for x in partial: print("[一部検証不能]", x)
    for x in decisions: print("[判断事項]", x)
    if status is None: print("TIER:", tier, "| RESULT:", "PASS" if not errs else "FAIL", "errors=%d" % len(errs)); sys.exit(1 if errs else 0)
    print("TIER:", tier, "| STATUS:", status, "| 客観的誤り/不一致=%d 一部検証不能=%d 判断事項=%d" % (len(errs + unresolved_A), len(partial), len(decisions)))
    sys.exit({"正常完了": 0, "判断事項付き完了": 0, "一部検証不能": 3, "重大な不一致あり": 1, "成果物検証失敗": 4}[status])
if __name__ == "__main__": main()
