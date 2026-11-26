#!/usr/bin/env python3
"""第4回改修の追加試験(既存46/37/33と同値性は別に維持)。合成データ=本物のWord/e-Gov/当社プロファイルでの結果ではない。"""
import sys, os, json, subprocess, tempfile, shutil, threading, http.server, hashlib
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); P = sys.executable; res = []
def t(name, ok, note=""): res.append(ok); print(("PASS " if ok else "FAIL ") + name + (" : " + note if note else ""))
def run(*a, **k): return subprocess.run([P, "-I"] + list(a), capture_output=True, text=True, **k)
# 1 独立オラクル比較: 適用断定の不一致0
r = run(os.path.join(HERE, "run_oracle_comparison.py")); t("独立オラクル72件: 適用断定の不一致0", r.returncode == 0)
# 2 review_mode: 一次資料確認の省略拒否
r = run(os.path.join(HERE, "review_mode.py"), "標準", "--skip", "確定的法的結論には機械取得した一次資料"); t("review_mode: 一次資料確認の省略を拒否", r.returncode == 2)
r = run(os.path.join(HERE, "review_mode.py"), "簡易", "--skip", "独立再検証"); t("review_mode: 簡易で独立再検証の省略は許可", r.returncode == 0)
# 3 revision_state: 合成案件
d = tempfile.mkdtemp(); os.makedirs(d + "/first"); os.makedirs(d + "/verifier")
contract = "第1条(目的)\nAは本件を委託する。\n第2条(支払)\n支払は翌月末日までに行う。\n第3条(解除)\n第5条に基づき解除できる。\n"; open(d + "/c.txt", "w", encoding="utf-8").write(contract)
js = [{"id": "J1", "clause": "第1条", "conclusion_status": "条件付き", "summary": "x"}, {"id": "J2", "clause": "第2条", "conclusion_status": "条件付き", "summary": "x"}, {"id": "J3", "clause": "第3条", "conclusion_status": "条件付き", "summary": "x"}]
revs = [{"revision_id": "R1", "judgment_id": "J1", "original_text": "Aは本件を委託する。", "revised_text": "Aは本件をBに委託する。", "reason": "r", "apply_to_word": True, "depends_on_statute": False, "evidence_ids": []},
        {"revision_id": "R2", "judgment_id": "J2", "original_text": "翌月末日までに", "revised_text": "受領日から60日以内に", "reason": "r", "apply_to_word": True, "depends_on_statute": True, "evidence_ids": ["E1"]},
        {"revision_id": "R3", "judgment_id": "J3", "original_text": "第5条に基づき", "revised_text": "第2条に基づき", "reason": "条番号誤り", "apply_to_word": True, "depends_on_statute": False, "mechanical_kind": "clause_ref", "evidence_ids": []},
        {"revision_id": "R4", "judgment_id": "J1", "original_text": "存在しない文言", "revised_text": "y", "reason": "r", "apply_to_word": True, "depends_on_statute": False, "evidence_ids": []}]
json.dump({"risk_tier": "standard", "our_role": "委託者", "judgments": js, "revisions": revs, "evidence": [{"id": "E1", "verified": False}], "term_assessments": []}, open(d + "/first/review.json", "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"judgments": js, "revisions": revs[:2], "our_role": "委託者"}, open(d + "/verifier/review_verifier.json", "w", encoding="utf-8"), ensure_ascii=False)
r = run(os.path.join(HERE, "revision_state.py"), d, "--contract", d + "/c.txt"); st = {s.get("revision_id"): s["state"] for s in json.load(open(d + "/revision_states.json", encoding="utf-8")) if s.get("revision_id")}
t("revision_state: 法令依存+一次資料未確認 → 根拠資料未確認", st.get("R2") == "根拠資料未確認", st.get("R2"))
t("revision_state: AI同士の一致+プロファイル未読込 → 条件付き(検証済みにしない)", st.get("R1") == "条件付き・要確認", st.get("R1"))
t("revision_state: 機械的修正(条番号) → 検証済み・反映可能", st.get("R3") == "検証済み・反映可能", st.get("R3"))
t("revision_state: 原文不一致の修正対象 → 反映禁止(第5回の区分変更: 旧『判断保留』から)", st.get("R4") == "反映禁止", st.get("R4"))
ap = json.load(open(d + "/approved_revisions.json", encoding="utf-8")); t("approved_revisions は検証済みのみ(R3のみ)", len(ap) == 1 and ap[0]["original_text"] == "第5条に基づき")
# 4 resolve_disagreements: 多数決しない・重大不一致を自動解消しない
r = run(os.path.join(HERE, "resolve_disagreements.py"), d, "--contract", d + "/c.txt", "--out", d + "/dis.json"); o = json.load(open(d + "/dis.json", encoding="utf-8"))
t("resolve_disagreements: 初回のみ修正案(第2条...)の重大不一致を『解消』にしない", all(not (i["serious"] and i["result"].startswith("解消")) for i in o["items"]), str([(i["clause"], i["field"], i["result"]) for i in o["items"]]))
# 5 PC取得連鎖(モックサーバ=本物のe-Gov/JFTCではない): 取得→SHA→取り込み、改ざん検知
raw = open(os.path.join(ROOT, "legal_cache", "raw", "raw_507M60200000009.json"), "rb").read()
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(s):
        if "/law_data/507AC" in s.path: s.send_response(404); s.end_headers(); return
        b, ct = (raw, "application/json") if "/law_data/" in s.path else (b'{"revisions":[]}', "application/json") if "/law_revisions/" in s.path else (b"%PDF-MOCK", "application/pdf")
        s.send_response(200); s.send_header("Content-Type", ct); s.end_headers(); s.wfile.write(b)
    def log_message(*a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start(); base = "http://127.0.0.1:%d" % srv.server_port
env = dict(os.environ, LEGAL_API_BASE=base, LEGAL_JFTC_BASE=base); out = tempfile.mkdtemp()
r = subprocess.run([P, os.path.join(ROOT, "pc", "fetch_legal_sources.py"), out], env=env, capture_output=True, text=True); t("fetch(モック): 必須取得成功・任意の404は記録して終了コード0", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-100:])
sub = os.path.join(out, sorted(os.listdir(out))[0]); cache = tempfile.mkdtemp(); r = run(os.path.join(HERE, "ingest_manifest.py"), sub, "--cache-dir", cache); t("ingest(モック): 取り込み成功", r.returncode == 0 and "機械取得" in r.stdout)
open(os.path.join(sub, "raw_rule_507M60200000009.json"), "ab").write(b" "); r = run(os.path.join(HERE, "ingest_manifest.py"), sub, "--cache-dir", tempfile.mkdtemp()); t("ingest: 転送中の改変(SHA不一致)を検知して失敗", r.returncode == 2 and "REJECT" in r.stdout)
real = json.load(open(os.path.join(ROOT, "legal_cache", "act_331AC0000000120.json"), encoding="utf-8")); t("モック取り込みが実キャッシュを汚染していない(取適法はmodel_transcriptionのまま)", real.get("acquisition") == "model_transcription")

# 6 第5回: AI転記と公式原文の比較(差異検出)
import copy as _c
src = json.load(open(os.path.join(ROOT, "legal_cache", "transcribed_backup", "rule_507M60200000009.json"), encoding="utf-8")); mod = _c.deepcopy(src); k0 = sorted(mod["provisions"])[0]; mod["provisions"][k0] = mod["provisions"][k0] + "改"; mod["provisions"]["99-9"] = "追加条文"
json.dump(src, open(d + "/t.json", "w", encoding="utf-8"), ensure_ascii=False); json.dump(mod, open(d + "/o.json", "w", encoding="utf-8"), ensure_ascii=False)
r = run(os.path.join(HERE, "compare_with_official.py"), d + "/t.json", d + "/o.json"); t("compare_with_official: 文言差を検出して終了コード1", r.returncode == 1 and "文言差" in r.stdout)
r = run(os.path.join(HERE, "compare_with_official.py"), d + "/t.json", d + "/t.json"); t("compare_with_official: 同一なら終了コード0", r.returncode == 0)
# 7 第5回: Word 確認事項(コメントのみ)・交渉上の提案
import docx as _d
doc = _d.Document(); [doc.add_paragraph(x) for x in ["第1条 支払は検収月末から90日以内とする。", "第2条 保証期間は6か月とする。"]]; doc.save(d + "/o.docx")
json.dump([{"revision_id": "R1", "clause": "第1条", "original_text": "検収月末から90日以内", "revised_text": "検収月末から90日以内", "comment": "【確認事項】支払期日が確定しない", "comment_only": True},
           {"revision_id": "R2", "clause": "第2条", "original_text": "6か月", "revised_text": "12か月", "comment": "【交渉上の提案(必須修正ではありません)】"}], open(d + "/w.json", "w", encoding="utf-8"), ensure_ascii=False)
r = run(os.path.join(HERE, "apply_revisions.py"), d + "/o.docx", d + "/w.json", d + "/out.docx"); t("Word: 確認事項(コメントのみ)+交渉上の提案を適用", r.returncode == 0, r.stdout.strip()[-80:])
r = run(os.path.join(HERE, "validate_docx.py"), d + "/out.docx", "--expect-ins", "1", "--expect-del", "1", "--expect-comments", "2"); t("Word: 構造検証(ins1/del1/コメント2)", r.returncode == 0, r.stdout.strip()[-60:])
# 8 第5回: revision_state の種別運用(契約書原文に基づく指摘は法令未取得でも『検証済み』になり得る/法令根拠は確認事項)
rv = json.load(open(d + "/first/review.json", encoding="utf-8")); rv["revisions"] = [dict(revs[0], finding_type="contract_text"), dict(revs[1], finding_type="law"), dict(revs[0], revision_id="R5", finding_type="economic")]
json.dump(rv, open(d + "/first/review.json", "w", encoding="utf-8"), ensure_ascii=False); vv = json.load(open(d + "/verifier/review_verifier.json", encoding="utf-8")); vv["revisions"] = revs[:2]; json.dump(vv, open(d + "/verifier/review_verifier.json", "w", encoding="utf-8"), ensure_ascii=False)
# 位置の一致のみ(検証記録なし)→提案止まり
r = run(os.path.join(HERE, "revision_state.py"), d + "/ ".strip(), "--contract", d + "/c.txt"); st0 = {s_.get("revision_id"): s_ for s_ in json.load(open(d + "/revision_states.json", encoding="utf-8")) if s_.get("revision_id")}
t("revision_state: 同一箇所の修正案があるだけ(10観点記録なし)では検証済みにならない", st0["R1"]["word_class"] != "検証済みの修正", st0["R1"]["word_class"])
AXS = ["1問題箇所", "2問題認識", "3修正の必要性", "4修正理由", "5修正方針", "6修正文案の意味", "7修正後の権利義務", "8修正後の法的経済的効果", "9他条項との整合", "10新たなリスク"]
json.dump({"checks": [{"revision_id": "R1", "axes": {x: "一致" for x in AXS}, "content_agreement": "一致", "adopted_text_verified": True}, {"revision_id": "R5", "axes": dict({x: "一致" for x in AXS}, **{"6修正文案の意味": "相違"}), "content_agreement": "効果差あり", "difference_note": "x", "adopted_text_verified": True}]}, open(d + "/revision_checks.json", "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"groups": [{"options_ids": ["R1", "R5"], "evaluations": {"R1": {"note": "n1"}, "R5": {"note": "n5"}}, "selected": "R1", "reason": "R1は原文に適合し効果差なし"}]}, open(d + "/option_selection.json", "w", encoding="utf-8"), ensure_ascii=False)
r = run(os.path.join(HERE, "revision_state.py"), d + "/ ".strip(), "--contract", d + "/c.txt"); st = {s_.get("revision_id"): s_ for s_ in json.load(open(d + "/revision_states.json", encoding="utf-8")) if s_.get("revision_id")}
t("revision_state: contract_text+10観点検証+選定記録 → 検証済みの修正(法令調査を要求しない)", st["R1"]["word_class"] == "検証済みの修正", st["R1"]["word_class"])
_ap = json.load(open(d + "/approved_revisions.json", encoding="utf-8")); t("複数案: 選定記録のある案のみ変更履歴・他案は不採用理由をコメント", [x["revision_id"] for x in _ap] == ["R1"] and "不採用" in _ap[0]["comment"])
os.remove(d + "/option_selection.json"); run(os.path.join(HERE, "revision_state.py"), d + "/ ".strip(), "--contract", d + "/c.txt"); _ap2 = json.load(open(d + "/approved_revisions.json", encoding="utf-8")); _cf = json.load(open(d + "/confirmations.json", encoding="utf-8"))
t("複数案: 選定記録なしなら先頭案を採用せずコメントのみ", not [x for x in _ap2 if x["revision_id"] == "R1"] and any("選定理由の記録なし" in x["comment"] for x in _cf))
t("revision_state: 法令根拠で一次資料なし → 確認事項(修正として反映しない)", st["R2"]["word_class"] == "確認事項", st["R2"]["word_class"])
t("revision_state: 経済的合理性 → 交渉上の提案", st["R5"]["word_class"] == "交渉上の提案", st["R5"]["word_class"])
print("追加試験(第4回/第5回): %d/%d 合格" % (sum(res), len(res))); sys.exit(0 if all(res) else 1)
