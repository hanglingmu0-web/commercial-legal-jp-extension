#!/usr/bin/env python3
"""新規追加機構の単体試験(中間3)。AIの法的判断の正しさではなく、機械的検査の動作のみを対象とする。"""
import sys, os, json, copy, shutil, tempfile, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import legal_sources as L, make_fixture_cache as MF, term_calc as TC, risk_tier as RT, review_gate as G
R = []
def t(name, ok, detail=""): R.append((name, bool(ok), detail))
FROOT = tempfile.mkdtemp(); FIX = os.path.join(FROOT, "legal_cache"); MF.build(FIX)
os.environ.pop("LEGAL_ALLOW_FIXTURE", None)
act = L.load("act_331AC0000000120", FIX); realact = L.load("act_331AC0000000120")
t("fixture_blocked_without_env", L.reliability(act, FIX).startswith("試験用フィクスチャ"), L.reliability(act, FIX))
os.environ["LEGAL_ALLOW_FIXTURE"] = "1"
t("fixture_ok_with_env", L.can_support_firm(act, FIX))
t("real_cache_ai_transcription_not_firm", not L.can_support_firm(realact) and "AI転記" in L.reliability(realact), L.reliability(realact))
t("guide_not_firm", not L.can_support_firm(L.load("guide_jftc_text_r7_11")))
rule = L.load("rule_507M60200000009"); t("real_rule_trace_ok", L.trace(rule)["ok"])
# raw改ざん検出
c2 = os.path.join(tempfile.mkdtemp(), "legal_cache"); shutil.copytree(FIX, c2); rp = os.path.join(c2, "raw", "raw_act_331AC0000000120.json")
open(rp, "a").write(" "); t("tamper_raw_detected", "不一致" in L.trace(L.load("act_331AC0000000120", c2), c2)["reason"])
c3 = os.path.join(tempfile.mkdtemp(), "legal_cache"); shutil.copytree(FIX, c3); j = json.load(open(os.path.join(c3, "act_331AC0000000120.json"), encoding="utf-8")); j["provisions"]["6-1"] += "改竄"; json.dump(j, open(os.path.join(c3, "act_331AC0000000120.json"), "w", encoding="utf-8"), ensure_ascii=False)
t("tamper_cache_detected", "不一致" in L.trace(L.load("act_331AC0000000120", c3), c3)["reason"])
t("verify_quote_match", L.verify_quote(act, "6-1", "遅延利息", FIX) == "MATCH")
t("verify_quote_nomatch", L.verify_quote(act, "6-1", "存在しない文言ですよ", FIX) in ("NO_MATCH", "NOT_VERBATIM", "NO_MATCH_RAW"), L.verify_quote(act, "6-1", "存在しない文言ですよ", FIX))
t("verify_quote_ref_missing", L.verify_quote(act, "99-1", "x", FIX) == "REF_MISSING")
t("verify_quote_transcript_only", L.verify_quote(realact, "6-1", "遅延利息") == "MATCH_ON_TRANSCRIPT", L.verify_quote(realact, "6-1", "遅延利息"))
cur = L.currency(act, "2026-11-24", today="2026-11-24", tier="high", cache_dir=FIX)
t("currency_axes", all(k in cur for k in ("retrieved_at", "promulgation_date", "enforcement_date", "transitional_provisions_retrieved", "last_verified_at", "reference_date", "needs_refresh", "caveats")))
t("currency_high_stale", bool(L.currency(act, "2026-11-26", today="2026-11-26", tier="high", cache_dir=FIX)["needs_refresh"]))
t("currency_light_ok", not L.currency(act, "2026-12-01", today="2026-12-01", tier="light", cache_dir=FIX)["needs_refresh"])
t("transitional_caveat", any("経過" in c for c in cur["caveats"]) or not cur["transitional_provisions_retrieved"], str(cur["caveats"]))
# 数値再計算
t("calc_annual", TC.recompute({"type": "annual_rate_over_days", "assumptions": {"principal_yen": 1_000_000, "rate_percent": 14.6, "days": 30}}) == 12000)
t("calc_daily", TC.recompute({"type": "daily_rate_over_days", "assumptions": {"amount_yen": 1_000_000, "daily_percent": 0.1, "days": 30}}) == 30000)
t("calc_bad", TC.recompute({"type": "zzz", "assumptions": {}}) is None)
# リスク階層
t("tier_light", RT.compute({"judgments": [{"id": "J1", "category": "G", "numbers": []}], "revisions": []})[0] == "light")
t("tier_high_cat", RT.compute({"judgments": [{"id": "J1", "category": "B", "numbers": []}], "revisions": []})[0] == "high")
# 統合ゲート/修正選別 (最小の合成ケースで挙動のみ確認)
def run(cmd): p = subprocess.run([sys.executable, "-I"] + cmd, capture_output=True, text=True, cwd=HERE); return p.returncode, p.stdout + p.stderr
W = tempfile.mkdtemp(); ctext = "第1条 甲は乙に年率36.5%の遅延損害金を支払う。委託者"; open(os.path.join(W, "c.txt"), "w", encoding="utf-8").write(ctext)
from review_gate import DIMS, NUMS
TX = "十分に実質的な評価記述であるという試験用の長い文章。"
def mk(jid="J1", cat="B", rev=True, status="確定", verified="検証済", tier="high"):
    j = {"id": jid, "clause": "第1条", "category": cat, "category_reason": "試験", "conclusion_status": status, "legally_mandatory": False, "statutes": [], "claims": [], "numbers": []}
    r = {"revision_id": "R1", "reason": "試験", "original_text": "a", "revised_text": "b", "risk_addressed": "過大な遅延損害金", "depends_on_statute": False, "apply_to_word": True, "judgment_id": jid, "verification_status": verified, "evidence_ids": []}
    ta = {"judgment_id": jid, "dimensions": {k: {"status": "評価済", "assessment": TX} for k in DIMS}, "revision_decision": "修正要" if rev else "修正不要", "no_revision_reason": "", "legal_conclusion": ""}
    return {"reference_date": "2026-11-24", "risk_tier": tier, "our_role": {"label": "委託者"}, "facts": {}, "evidence": [], "judgments": [j], "revisions": [r] if rev else [], "term_assessments": [ta], "numeric_reviews": []}
def save(n, o): p = os.path.join(W, n); json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False); return p
f = save("f.json", mk()); v = save("v.json", mk())
rc, out = run(["integrated_gate.py", "--first", f, "--contract", os.path.join(W, "c.txt"), "--out", os.path.join(W, "g0.json")]); t("ig_missing_verifier_fails", rc == 1 and "独立再検証が未実施" in out, out[-200:])
rc, out = run(["integrated_gate.py", "--first", f, "--verifier", v, "--contract", os.path.join(W, "c.txt"), "--out", os.path.join(W, "g1.json")]); t("ig_high_requires_adversarial", rc == 1 and "反証レビューが未実施" in out, out[-200:])
adv_ok = save("a_ok.json", {"examined": {k: "検討済" for k in ("common_judgment", "missed_issues", "validity_vs_economics", "applicability_gaps", "logic_leaps", "no_revision_reasons", "new_risks")}, "findings": [], "no_findings_reason": "各検討項目を確認し、契約書原文に照らして新たな問題は認められなかった"})
rc, out = run(["integrated_gate.py", "--first", f, "--verifier", v, "--adversarial", adv_ok, "--contract", os.path.join(W, "c.txt"), "--out", os.path.join(W, "g2.json")]); t("ig_all_present_pass", rc == 0, out[-300:])
adv_bad = save("a_bad.json", {"examined": {"common_judgment": "x"}, "findings": [], "no_findings_reason": ""})
rc, out = run(["integrated_gate.py", "--first", f, "--verifier", v, "--adversarial", adv_bad, "--contract", os.path.join(W, "c.txt")]); t("ig_adv_incomplete_fails", rc == 1 and "検討項目" in out)
adv_nog = save("a_nog.json", dict(json.load(open(adv_ok)), findings=[{"id": "ADV-1", "issue": "懸念", "grounds": {}, "recommended_revision": "直せ"}]))
rc, out = run(["integrated_gate.py", "--first", f, "--verifier", v, "--adversarial", adv_nog, "--contract", os.path.join(W, "c.txt")]); t("ig_ungrounded_adv_rejected", rc == 1 and "根拠" in out)
# 不一致放置
vd = mk(); vd["judgments"][0]["conclusion_status"] = "判断保留"; vd["revisions"] = []; vd["term_assessments"][0]["revision_decision"] = "判断保留"; vdp = save("vd.json", vd)
rc, out = run(["integrated_gate.py", "--first", f, "--verifier", vdp, "--adversarial", adv_ok, "--contract", os.path.join(W, "c.txt")]); t("ig_unresolved_disagreement_fails", rc == 1 and "不一致が放置" in out, out[-300:])
# 修正選別
out_d = os.path.join(W, "sel"); rc, o = run(["select_revisions.py", "--first", f, "--verifier", v, "--gate-result", os.path.join(W, "g2.json"), "--out-dir", out_d]); t("select_approved", "approved=1 held=0" in o, o)
rc, o = run(["select_revisions.py", "--first", f, "--verifier", vdp, "--gate-result", os.path.join(W, "g2.json"), "--out-dir", out_d]); t("select_holds_when_verifier_disagrees", "approved=0 held=1" in o, o)
fu = mk(verified="未検証"); fup = save("fu.json", fu); rc, o = run(["select_revisions.py", "--first", fup, "--verifier", v, "--gate-result", os.path.join(W, "g2.json"), "--out-dir", out_d]); t("select_ignores_ai_self_report_when_verifier_agrees", "approved=1 held=0" in o, o)
fc = mk(verified="検証済"); fcp = save("fc.json", fc); rc, o = run(["select_revisions.py", "--first", fcp, "--verifier", vdp, "--gate-result", os.path.join(W, "g2.json"), "--out-dir", out_d]); t("select_holds_ai_claimed_verified_without_verifier_agreement", "approved=0 held=1" in o, o)
fh = mk(status="判断保留"); fhp = save("fh.json", fh); rc, o = run(["select_revisions.py", "--first", fhp, "--verifier", v, "--gate-result", os.path.join(W, "g2.json"), "--out-dir", out_d]); t("select_holds_held_judgment", "approved=0 held=1" in o, o)
# ゲート: 修正不要の理由が任意設定のみ
g = mk(rev=False); g["term_assessments"][0]["dimensions"]["economic_rationality"] = {"status": "未評価", "assessment": ""}; g["term_assessments"][0]["no_revision_reason"] = "当事者間の任意設定であり法令に禁止はない"
F_, _ = G.gate(g, FIX, "2026-11-24", ctext); t("gate_voluntary_only_no_revision", any("経済的合理性" in f_["message"] for f_ in F_ if f_["severity"] == "error"))
g = mk(rev=False); g["term_assessments"][0]["dimensions"]["legal_validity"]["assessment"] = "数値が大きいため無効と考えられる(根拠なしの記述)"
F_, _ = G.gate(g, FIX, "2026-11-24", ctext); t("gate_large_number_invalid", any("違法/無効" in f_["message"] or "大きい" in f_["message"] for f_ in F_ if f_["severity"] == "error"), str([f_["message"] for f_ in F_ if f_["severity"]=="error"]))
# 数値審査: 立場誤認
n = mk(rev=False); n["judgments"][0]["numbers"] = [{"label": "遅延損害金年率36.5%", "value_percent": 36.5, "kind": "任意設定", "negotiation_basis": "試験"}]
n["numeric_reviews"] = [{"judgment_id": "J1", "term_label": "遅延損害金", "value_text": "36.5%", "burden_on": "相手方", "payer": "委託者", "checks": {k: {"status": "評価済", "text": TX} for k in NUMS}, "calc_examples": []}]
F_, _ = G.gate(n, FIX, "2026-11-24", ctext); t("gate_position_misrecognition", any("立場の誤認" in f_["message"] for f_ in F_ if f_["severity"] == "error"), str([f_["message"] for f_ in F_ if f_["severity"]=="error"][:3]))
n["numeric_reviews"][0]["burden_on"] = "当社"; n["numeric_reviews"][0]["calc_examples"] = [{"assumed": True, "type": "annual_rate_over_days", "assumptions": {"principal_yen": 1_000_000, "rate_percent": 36.5, "days": 30}, "result_yen": 99999}]
F_, _ = G.gate(n, FIX, "2026-11-24", ctext); t("gate_calc_mismatch", any("再計算" in f_["message"] for f_ in F_ if f_["severity"] == "error"))
n["numeric_reviews"][0]["calc_examples"][0]["result_yen"] = TC.recompute(n["numeric_reviews"][0]["calc_examples"][0]); n["numeric_reviews"][0]["calc_examples"][0]["assumed"] = False
F_, _ = G.gate(n, FIX, "2026-11-24", ctext); t("gate_calc_not_marked_assumed", any("assumed" in f_["message"] for f_ in F_ if f_["severity"] == "error"))
# パイプラインログ
lg = os.path.join(W, "log.jsonl"); rc, o = run(["pipeline_log.py", "run", lg, "gate", "--artifact", f, "--", sys.executable, "-I", "review_gate.py", f]); rc2, o2 = run(["pipeline_log.py", "mark", lg, "first_review", "--status", "ok", "--duration-ms", "1234", "--artifact", f])
lines = [json.loads(x) for x in open(lg, encoding="utf-8")]; t("pipeline_log_records", len(lines) == 2 and lines[0]["kind"] == "executed" and lines[1]["kind"] == "external" and lines[1]["duration_ms"] == 1234)
p = sum(1 for _, ok, _ in R if ok)
for n_, ok, d_ in R:
    if not ok: print("[FAIL]", n_, d_)
rd = os.path.join(ROOT, "logs"); os.makedirs(rd, exist_ok=True); json.dump({"ts": datetime.datetime.now().isoformat(), "results": [{"name": a, "ok": b, "detail": c} for a, b, c in R]}, open(os.path.join(rd, "pipeline_tests_%s.json" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S")), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("追加機構の単体試験: %d/%d 合格" % (p, len(R))); sys.exit(0 if p == len(R) else 1)
