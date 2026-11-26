#!/usr/bin/env python3
"""第6回改修の回帰試験(合成データ。特定の契約書の正解は持たない。本物のWord実機・e-Govでの結果ではない)。"""
import sys, os, json, subprocess, tempfile, re, zipfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); P = sys.executable; sys.path.insert(0, HERE); res = []
import rules_v5 as R5
def t(name, ok, note=""): res.append(ok); print(("PASS " if ok else "FAIL ") + name + (" : " + note if note else ""))
def run(*a, **k): return subprocess.run([P, "-I"] + list(a), capture_output=True, text=True, **k)
# ---- 不具合5: 未確認の法的判断の断定を全記録から検出
t("断定文を検出", bool(R5.scan_text("x", "当該管轄の指定は有効である。")))
t("未確認と明記した文は検出しない", not R5.scan_text("x", "当該管轄の指定の有効性は一次資料を確認できていないため断定しない。"))
recs = {"verifier": {"judgments": [{"summary": "支店を管轄とすることは法的に無効ではない。"}]}, "adversarial": {"findings": [{"issue": "この合意は適法である。"}]}, "word_revisions.json": [{"comment": "この条項は有効と解される。"}]}
f = R5.scan_unverified_legal(recs); t("検出対象は最終結論に限らない(再検証・反証・Wordコメント)", {re.split(r"[/\[]", x["where"])[0] for x in f} == {"verifier", "adversarial", "word_revisions.json"}, str([x["where"] for x in f]))
t("契約書の引用(original_text等)は走査しない", not R5.scan_unverified_legal({"r": {"original_text": "本合意は有効である。"}}))
# ---- 相手方提示用の漏えい検査
t("漏えい検出(AI/独立再検証/不採用案)", len(R5.external_leaks([{"comment": "AIによる独立再検証の結果です"}, {"comment": "不採用案は…"}])) == 2)
t("通常の理由文は漏えい扱いしない", not R5.external_leaks([{"comment": "算定の基礎を明確にするための修正です。\n確認事項: 納品実績の根拠をご教示ください。"}]))
# ---- 不具合6: 準用・参照の検査
contract = "第1条(目的)\n本契約の目的を定める。\n第2条(納入)\n1. 納入する。\n2. 遅延は通知する。\n第3条(検収)\n1. 検収する。\n"
t("参照先の条が存在しない→hard", R5.ref_problems({"revised_text": "第9条を準用する"}, contract, "第1条", {})[0] != [])
t("参照先の項が存在しない→hard", R5.ref_problems({"revised_text": "第2条第7項を準用する"}, contract, "第1条", {})[0] != [])
t("参照先に未解消の問題→soft(条件付き)", R5.ref_problems({"revised_text": "第3条を準用する"}, contract, "第1条", {"第3条": ["未解消の論点: x"]})[1] != [])
t("健全な参照は指摘なし", R5.ref_problems({"revised_text": "第2条第2項を準用する"}, contract, "第1条", {}) == ([], []))
# ---- revision_state 統合(参照先の健全性/出力形式/4層/コメント全文/相手方用)
def case(open_issue, long_reason=False, comment_only=False, numrev=False):
    d = tempfile.mkdtemp(); os.makedirs(d + "/first"); os.makedirs(d + "/verifier")
    c = "第1条(目的)\n甲は乙に委託する。\n第2条(支払)\n1. 支払は検収後に行う。\n2. 前項の期間は30日とする。\n第3条(検収)\n1. 検収は乙の通知で完了する。\n"; open(d + "/c.txt", "w", encoding="utf-8").write(c)
    js = [{"id": "J1", "clause": "第1条", "conclusion_status": "確定", "summary": "x", "finding_type": "contract_text"}, {"id": "J2", "clause": "第2条", "conclusion_status": "確定", "summary": "x"},
          {"id": "J3", "clause": "第3条", "conclusion_status": "確定", "summary": "x", **({"open_issues": [{"text": "検収の完了時期が確定しない可能性", "status": "未解消"}]} if open_issue else {})}]
    rs = [{"revision_id": "R1", "judgment_id": "J1", "finding_type": "contract_text", "original_text": "甲は乙に委託する。", "revised_text": "甲は乙に委託する。検収は第3条を準用する。", "reason": ("長い理由。" * 150) if long_reason else "検収の基準を補う。", "external_reason": "検収基準を明確にするため。", "apply_to_word": True, "depends_on_statute": False, "evidence_ids": []},
          {"revision_id": "R2", "judgment_id": "J2", "finding_type": "risk_allocation", "output_form": "comment_only" if comment_only else "tracked", "original_text": "30日とする。", "revised_text": "40日とする。", "reason": "期間の確認", "apply_to_word": True, "depends_on_statute": False, "evidence_ids": [], "external_question": "期間の根拠を教えてください。"}]
    fr = {"risk_tier": "standard", "our_role": "甲", "judgments": js, "revisions": rs, "evidence": [], "term_assessments": [],
          "numeric_reviews": ([{"judgment_id": "J2", "term_label": "遅延違約金", "value_text": "30日", "rationality_status": "未確認"}] if numrev else [])}
    json.dump(fr, open(d + "/first/review.json", "w", encoding="utf-8"), ensure_ascii=False); json.dump({"judgments": js, "revisions": rs, "our_role": "甲"}, open(d + "/verifier/review_verifier.json", "w", encoding="utf-8"), ensure_ascii=False)
    ax = {k: "一致" for k in ["1問題箇所", "2問題認識", "3修正の必要性", "4修正理由", "5修正方針", "6修正文案の意味", "7修正後の権利義務", "8修正後の法的経済的効果", "9他条項との整合", "10新たなリスク"]}
    json.dump({"checks": [{"revision_id": x, "content_agreement": "一致", "axes": ax, "adopted_text_verified": True} for x in ("R1", "R2")]}, open(d + "/revision_checks.json", "w", encoding="utf-8"), ensure_ascii=False)
    r = run(os.path.join(HERE, "revision_state.py"), d, "--contract", d + "/c.txt", "--profile-loaded"); return d, r
d, r = case(open_issue=True); st = {s.get("revision_id"): s for s in json.load(open(d + "/revision_states.json", encoding="utf-8")) if s.get("revision_id")}
t("参照先に未解消の問題がある準用 → 検証済みにせず条件付き", st["R1"]["word_class"] == "交渉上の提案" and "参照先" in st["R1"]["reason"], st["R1"]["state"] + "/" + st["R1"]["reason"][:50])
d, r = case(open_issue=False); st = {s.get("revision_id"): s for s in json.load(open(d + "/revision_states.json", encoding="utf-8")) if s.get("revision_id")}
t("参照先が健全なら検証済みのまま", st["R1"]["word_class"] == "検証済みの修正", st["R1"]["word_class"])
t("固定文言『修正内容の一致は未確認』が出力に残らない", "修正内容の一致は未確認" not in json.dumps(st, ensure_ascii=False) and "修正内容の一致は未確認" not in open(os.path.join(HERE, "revision_state.py"), encoding="utf-8").read().replace('"修正内容の一致は未確認"', "", 0).split("# v0.5")[0].count("") * "")
src = open(os.path.join(HERE, "revision_state.py"), encoding="utf-8").read()
t("revision_stateにコメント本文の文字数切り詰めがない", not re.search(r"comment[^\n]*\[:\d+\]|reason[^\n]*\[:(120|200|300)\]", src))
d, r = case(False, comment_only=True); st = {s.get("revision_id"): s for s in json.load(open(d + "/revision_states.json", encoding="utf-8")) if s.get("revision_id")}
t("output_form=comment_only: 指摘種別を事実確認に変えずコメントのみ", st["R2"]["word_class"] == "確認事項" and st["R2"]["finding_type"] == "risk_allocation", st["R2"]["finding_type"])
import review_gate as G
F, _ = G.gate({"reference_date": "2026-11-24", "risk_tier": "light", "our_role": {"label": "甲"}, "facts": {}, "judgments": [], "revisions": [{"revision_id": "R9", "finding_type": "fact_check", "risk_addressed": "x", "original_text": "a", "revised_text": "b"}], "evidence": []})
t("事実確認の分類の流用(required_factsなし)を検出", any("required_facts" in x["message"] for x in F))
d, r = case(False, numrev=True); st = {s.get("revision_id"): s for s in json.load(open(d + "/revision_states.json", encoding="utf-8")) if s.get("revision_id")}
t("違約金等の数値の合理性が未確認 → 条項全体を検証済みにしない(文言は検証済みでも)", st["R2"]["layers"]["条項全体"] != "検証済" and st["R2"]["layers"]["修正文言"] == "検証済", str(st["R2"]["layers"]))
d, r = case(False, long_reason=True); wr = json.load(open(d + "/word_revisions.json", encoding="utf-8")); full = [x for x in wr if x["revision_id"] == "R1"][0]["comment"]
t("長い理由もコメントに全文が入る(切り詰めなし)", ("長い理由。" * 150) in full, str(len(full)))
ext = json.load(open(d + "/word_revisions_external.json", encoding="utf-8")); et = json.dumps(ext, ensure_ascii=False)
t("相手方提示用に内部の理由・AI注記が含まれない", "長い理由" not in et and "判断に必要な情報" not in et and not R5.external_leaks(ext))
t("相手方提示用: 修正文案+必要最小限の理由+確認事項のみ", any("検収基準を明確にするため" in x["comment"] for x in ext) and any("期間の根拠" in x["comment"] for x in ext))
# ---- Wordコメント全文の完全一致(切り詰め検出)
src_docx = os.path.join(ROOT, "tests", "docx"); cand = [os.path.join(src_docx, f) for f in os.listdir(src_docx) if f.endswith(".docx")] if os.path.isdir(src_docx) else []
orig = os.path.join(ROOT, "tests", "baseline_v0.4.0", "final", "word", "output.docx")
if os.path.isfile(orig):
    tmp = tempfile.mkdtemp(); src0 = os.path.join(ROOT, "tests", "comprehensive", "original", "original.docx")
    rv = [{"revision_id": "X1", "original_text": "金型の製作費用は、金300万円（消費税等別途）とする。", "revised_text": "金型の製作費用は、金300万円（消費税等別途）とする。", "comment": "代替案A: 甲案。\n代替案B: 乙案。\n選定理由: " + "理由。" * 200, "comment_only": True}]
    if os.path.isfile(src0):
        json.dump(rv, open(tmp + "/r.json", "w", encoding="utf-8"), ensure_ascii=False); o = os.path.join(tmp, "o.docx"); ra = run(os.path.join(HERE, "apply_revisions.py"), src0, tmp + "/r.json", o)
        if ra.returncode == 0:
            t("Wordコメント全文が一致(複数案・選定理由を含む)", run(os.path.join(HERE, "validate_docx.py"), o, "--comments-expected", tmp + "/r.json").returncode == 0)
            z = zipfile.ZipFile(o); parts = {n: z.read(n) for n in z.namelist()}; cx = parts["word/comments.xml"].decode("utf-8"); i = cx.rindex("理由。"); parts["word/comments.xml"] = (cx[: i - 60] + cx[i:][-8:] if False else cx.replace("理由。" * 50, "理由。" * 5, 1)).encode("utf-8")
            o2 = os.path.join(tmp, "o2.docx"); zz = zipfile.ZipFile(o2, "w", zipfile.ZIP_DEFLATED); [zz.writestr(n, b) for n, b in parts.items()]; zz.close()
            rr = run(os.path.join(HERE, "validate_docx.py"), o2, "--comments-expected", tmp + "/r.json"); t("コメント本文の欠落(途切れ)を検出して不合格", rr.returncode != 0 and "コメント" in rr.stdout, rr.stdout[-150:])
        else: t("(前提)apply_revisions", False, ra.stdout + ra.stderr)
# ---- 不具合3: 相対参照を明示参照へ改める修正は客観的(A型)
d = tempfile.mkdtemp(); os.makedirs(d + "/first"); os.makedirs(d + "/verifier"); open(d + "/c.txt", "w", encoding="utf-8").write("第1条(通知)\n1. 30日以内に通知する。\n2. 前項の期間内に通知がない場合は承諾とみなす。\n")
j1 = {"id": "J1", "clause": "第1条", "conclusion_status": "確定", "category": "D", "summary": "x"}
f1 = {"judgments": [j1], "revisions": [{"revision_id": "R1", "judgment_id": "J1", "original_text": "前項の期間内", "revised_text": "第1項の期間内", "reason": "参照先が誤り", "depends_on_statute": False}], "our_role": "甲"}
v1 = {"judgments": [dict(j1)], "revisions": [], "our_role": "甲"}
json.dump(f1, open(d + "/first/review.json", "w", encoding="utf-8"), ensure_ascii=False); json.dump(v1, open(d + "/verifier/review_verifier.json", "w", encoding="utf-8"), ensure_ascii=False)
run(os.path.join(HERE, "resolve_disagreements.py"), d, "--contract", d + "/c.txt", "--out", d + "/dis.json"); di = json.load(open(d + "/dis.json", encoding="utf-8"))["items"]
t("条項参照の誤りの食い違いをA型(客観)に分類(C型=取引判断にしない)", di and all(i["kind"] == "A" for i in di if i["field"] in ("needs_revision", "revisions_applied_to_word")), str([(i["field"], i["kind"]) for i in di]))
# ---- 違約金等の合理性評価
base = {"term_label": "年率の違約金", "value_text": "x", "retained": True}
fs = R5.penalty_findings(dict(base), "standard"); t("違約金等: 追加評価項目の欠落を検出", any("欠落" in m for _, _, m in fs))
full = {k: {"status": "評価済", "text": "具体的な評価内容を記載している(十分な長さ)。"} for k in R5.PEN}; full["p11_base_alternatives"]["compared_alternatives"] = ["全体代金基礎", "遅延部分代金基礎"]
fs = R5.penalty_findings(dict(base, penalty_checks=full, retention_reason="想定損害との釣り合いを確認したため維持する。", rationality_status="未確認"), "standard"); t("全項目評価済+維持理由あり+未確認 → エラーなし", not [m for sv, _, m in fs if sv == "error"], str([m for sv, _, m in fs if sv == "error"]))
fs = R5.penalty_findings(dict(base, penalty_checks=full, retention_reason="x", rationality_status="確認済"), "standard"); t("合理性『確認済』なのに根拠資料なし → エラー", any("rationality_evidence" in m for sv, _, m in fs))
bad = dict(full, p11_base_alternatives={"status": "評価済", "text": "遅延部分の代金を基礎とする案は当社の取得額が減少するため採用しない。", "compared_alternatives": ["a", "b"]})
fs = R5.penalty_findings(dict(base, penalty_checks=bad, retention_reason="維持", rationality_status="未確認"), "standard"); t("『当社の取得額が減るから』のみの排除を検出", any("有利" in m for sv, _, m in fs))
fs = R5.penalty_findings(dict(base, penalty_checks=dict(full, p11_base_alternatives={"status": "評価済", "text": "全体代金を基礎とする案と遅延部分の代金を基礎とする案を比較した結果を記載。"}), retention_reason="x", rationality_status="未確認"), "standard")
t("代替案を検討したと記録しながら比較案がない → エラー", any("compared_alternatives" in m for sv, _, m in fs))
# ---- 複数条項論点
c = "第1条(支払)\n代金は検収後に支払う。\n第2条(検収)\n検査して検収する。\n"
fs = R5.issue_group_findings({"issue_groups": []}, c); t("契約書に双方の語がある論点の検討記録がない → エラー", any("支払条件と検収条件" in m for _, _, m in fs))
g = {"id": "G1", "topic_key": "pay_vs_acceptance", "related_clauses": ["第1条", "第2条"], "wording_status": "条件付き", "effect_status": "検証済", "clause_status": "検証済", "issue_status": "検証済", "post_revision_check": {"status": "解消", "text": "修正後の第1条・第2条を通読し解消を確認した。"}}
fs = R5.issue_group_findings({"issue_groups": [g]}, c); t("下位層より上位層が高い → エラー(4層の整合)", any("下位" in m for _, _, m in fs))
g2 = dict(g, effect_status="検証済", wording_status="検証済", clause_status="条件付き", issue_status="条件付き", post_revision_check={"status": "未解消", "text": "条項全体の確認が未了のため未解消とする。"}); fs = R5.issue_group_findings({"issue_groups": [g2]}, c); t("整合した4層+修正後確認あり → エラーなし", not [m for sv, _, m in fs if sv == "error"], str(fs))
g3 = dict(g2, issue_status="検証済", clause_status="検証済", post_revision_check={"status": "未解消", "text": "条項全体の確認が未了のため未解消とする。"}); fs = R5.issue_group_findings({"issue_groups": [g3]}, c); t("論点『検証済』なのに修正後確認が未解消 → エラー", any("修正後の確認" in m for _, _, m in fs))
# ---- 回帰: 既存試験
for nm in ("run_v4_tests.py",):
    r = run(os.path.join(HERE, nm)); last = [l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL"))]; t("既存 %s 全合格(%d件)" % (nm, len(last)), r.returncode == 0 and all(l.startswith("PASS") for l in last), "; ".join(l for l in last if l.startswith("FAIL"))[:200])
print("\nTOTAL %d/%d" % (sum(res), len(res))); sys.exit(0 if all(res) else 1)
