#!/usr/bin/env python3
"""単一レビュー(review.json)の検査ゲート。一次資料キャッシュ・適用要件エンジン・契約書原文と突き合わせる。
各指摘に検証種別を付す: 機械検証(確定的に検出) / 要人間判断(機械では判定不能)。
重要: 合格は『手続上の不備が検出されなかった』ことのみを意味し、法的判断の正確性を保証しない。
使い方: review_gate.py review.json [--cache-dir DIR] [--today YYYY-MM-DD] [--contract contract.txt]
"""
import sys, os, re, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legal_sources as L, applicability as A, check_review_output as C, risk_tier as RT
from term_calc import recompute
import rules_v5 as R5
DIMS = ["legal_validity", "mandatory_law", "applicability", "economic_rationality", "our_position", "risk_allocation", "performability", "dispute_effectiveness", "negotiation", "playbook_alignment"]
NUMS = ["n1_legal_regulation", "n2_law_applies", "n3_basis", "n4_beneficiary_burden", "n5_vs_consideration", "n6_vs_expected_loss", "n7_calc_method", "n8_overlap", "n9_over_under_burden"]
ST = {"評価済", "未評価", "不明"}
ONLY_VOLUNTARY = re.compile(r"(任意(に)?設定|禁止(されて)?(い)?ない|違法(では|で)ない|法令上(の)?問題(は)?ない|強行法規(に)?(違反|抵触)しない|有効(である|だ)|当事者の自由|契約自由)")
NUMBER_BIG_ONLY = re.compile(r"(高率|過大|高すぎ|大きい)(である)?(ため|ので|から)(違法|無効|公序良俗違反)")

def gate(rv, cache_dir=None, today=None, contract_text=None):
    F = []
    def err(msg, kind="機械検証", sev="error"): F.append({"severity": sev, "kind": kind, "message": msg})
    ref = rv.get("reference_date"); today = today or ref; tier = rv.get("risk_tier", "standard")
    event = (rv.get("facts") or {}).get("contract_date")
    for m in C.check(rv): err("[構造] " + m)
    ev = {e["id"]: e for e in rv.get("evidence", [])}
    eng = A.judge(dict(rv.get("facts") or {}, reference_date=ref), cache_dir) if rv.get("facts") is not None else None
    tier_calc, why = RT.compute(rv)
    if RT.ORDER[tier] < RT.ORDER[tier_calc]: err("リスク階層を過小申告(申告%s < 算定%s: %s)" % (tier, tier_calc, "; ".join(why)))
    for e in ev.values():
        sid = e.get("source_id"); src = L.load(sid, cache_dir) if sid else None
        if sid and src is None and e.get("retrieval_status") in ("未取得", "取得失敗") and not e.get("verified"): continue
        if sid and src is None: err("資料%s: キャッシュに存在しない資料(source_id=%s) → 一次資料未確認" % (e["id"], sid)); continue
        if src is not None:
            if e.get("verified") and not L.can_support_firm(src, cache_dir): err("資料%s: verified=trueだがキャッシュの信頼区分は『%s』" % (e["id"], L.reliability(src, cache_dir)))
            if e.get("source_type") == "一次" and L.acquisition(src) != L.ACQ_MACHINE: err("資料%s: 一次資料と申告されているが取得区分は%s(AI転記・要約・解説は一次資料として扱えない)" % (e["id"], L.acquisition(src)))
    for j in rv.get("judgments", []):
        jid = j.get("id"); firm = j.get("conclusion_status") == "確定"
        for s in j.get("statutes", []):
            for i in s.get("evidence_ids", []):
                e = ev.get(i); src = L.load(e["source_id"], cache_dir) if e and e.get("source_id") else None
                if firm:
                    if src is None: err("%s: 確定の根拠資料%sがキャッシュにない(一次資料未確認)" % (jid, i))
                    else:
                        if not L.can_support_firm(src, cache_dir): err("%s: 『確定』の根拠にできない資料%s(%s)" % (jid, i, L.reliability(src, cache_dir)))
                        cur = L.currency(src, ref, event, today, tier, cache_dir)
                        if cur["needs_refresh"]: err("%s: 資料%sの現行性が未確認(%s)" % (jid, i, "; ".join(cur["needs_refresh"])))
                if src is not None and src.get("kind") != "Guidance":
                    comp = L.effectiveness(src, ref) if ref else "不明"; decl = s.get("effective_status")
                    if decl and comp != "不明" and decl != comp: err("%s/%s: 有効性の申告『%s』が資料(施行%s)から算出した基準日(%s)時点の『%s』と不一致" % (jid, s.get("name"), decl, src.get("enforcement_date"), ref, comp))
                    nm = s.get("name")
                    if nm in (src.get("former_titles") or []) and not s.get("former_name_note"): err("%s: 旧名称『%s』を現行名称として記載(現行名称: %s)" % (jid, nm, src["law_title"]))
                    elif nm and nm != src.get("law_title") and nm not in (src.get("abbrev") or []) and nm not in (src.get("former_titles") or []): err("%s: 法令名『%s』が資料の名称/略称/旧名称のいずれとも一致しない" % (jid, nm))
            if s.get("asserted_applicable") or j.get("legally_mandatory"):
                if eng is None: err("%s: 適用を断定しているが facts(事実関係)がなく適用要件判定を実行できない" % jid)
                elif not eng["asserted_applicable"]: err("%s: 適用を断定したがエンジン判定は『%s』(必要事実: %s)" % (jid, eng["overall"], "; ".join(eng["required_facts"]) or "なし"))
            if eng is not None:
                by = {r["name"]: r["status"] for r in eng["requirements"]}
                for r in s.get("requirements", []):
                    if r.get("name") in by and by[r["name"]] != r.get("status"): err("%s: 要件『%s』の判定『%s』がエンジン判定『%s』と不一致" % (jid, r["name"], r.get("status"), by[r["name"]]))
        if j.get("statutes") and not j.get("claims"):
            err("%s: 法令を挙げているが引用(claims)がなく、条文との照合ができない" % jid, kind="機械検証" if firm else "要人間判断", sev="error" if firm else "info")
        for c in j.get("claims", []):
            src = L.load(c.get("source_id"), cache_dir); res = L.verify_quote(src, c.get("ref"), c.get("quote", ""), cache_dir)
            if res == "SOURCE_MISSING": err("%s: 引用元資料%sがキャッシュにない" % (jid, c.get("source_id")))
            elif res == "REF_MISSING": err("%s: 引用元に条項『%s』が存在しない(架空/誤引用の疑い)" % (jid, c.get("ref")))
            elif res in ("NO_MATCH", "NO_MATCH_RAW"): err("%s: 引用文が%s %sの%sに含まれない" % (jid, c.get("source_id"), c.get("ref"), "原文" if res == "NO_MATCH" else "取得原文(raw)"))
            elif res == "NOT_VERBATIM": err("%s: 引用元%sは原文でない(要約/未検証)ため引用照合不能" % (jid, c.get("source_id")))
            elif res == "TRACE_FAIL": err("%s: 引用元%sの取得原文への追跡に失敗" % (jid, c.get("source_id")))
            else:
                if res == "MATCH_ON_TRANSCRIPT":
                    err("%s: 引用はAI転記資料との照合のみ(取得原文との照合ではない)" % jid, kind="機械検証" if firm else "要人間判断", sev="error" if firm else "info")
                miss = [k for k in c.get("key_terms", []) if L.norm(k) not in L.norm(c["quote"])]
                if not c.get("key_terms"): err("%s: 主張『%s』に key_terms(根拠となるべき語)がなく関連性を検査できない" % (jid, c.get("text", "")[:30]))
                elif miss: err("%s: 引用箇所に主張の要点語%sが含まれない(実在するが当該判断の根拠とならない可能性)" % (jid, miss))
                F.append({"severity": "info", "kind": "要人間判断", "message": "%s: 引用箇所が主張を論理的に支えるか(解釈の飛躍の有無)は機械判定不能" % jid})
        for n in j.get("numbers", []):
            lab = n.get("label")
            if n.get("kind") == "法定率":
                br = n.get("basis_ref") or {}; src = L.load(br.get("source_id"), cache_dir)
                if src is None: err("%s: 数値『%s』の根拠資料がない" % (jid, lab)); continue
                val = L.rate_from_text(L.get_text(src, br.get("ref")))
                if val is None: err("%s: 数値『%s』の根拠条項から率を読み取れない" % (jid, lab))
                elif val != n.get("value_percent"): err("%s: 数値『%s』%s%%が根拠条項の%s%%と不一致" % (jid, lab, n.get("value_percent"), val))
                if eng is None or not eng["asserted_applicable"]: err("%s: 数値『%s』を法定率として扱っているが当該法令の適用が確定していない" % (jid, lab))
            elif n.get("kind") == "任意設定":
                if not n.get("negotiation_basis"): err("%s: 任意設定の数値『%s』に設定根拠(経済的合理性・交渉上の根拠)がない" % (jid, lab))
                F.append({"severity": "info", "kind": "要人間判断", "message": "%s: 数値『%s』の経済的合理性・当事者への影響は機械判定不能" % (jid, lab)})
            else: err("%s: 数値『%s』のkindが法定率/任意設定のいずれでもない(法定率と任意条件の混同防止)" % (jid, lab))
    jmap = {j.get("id"): j for j in rv.get("judgments", [])}
    for r in rv.get("revisions", []):
        rid = r.get("revision_id")
        if r.get("depends_on_statute") and (eng is None or not eng["asserted_applicable"]) and r.get("apply_to_word"): err("%s: 法令適用を前提とする修正をWord反映対象にしているが、適用要件が確定していない(%s)" % (rid, eng["overall"] if eng else "facts無し"))
        if not r.get("risk_addressed"): err("%s: 修正で解消するリスクが未記載(第9章)" % rid)
        if r.get("judgment_id") and r["judgment_id"] not in jmap: err("%s: 参照先の判断%sが存在しない" % (rid, r["judgment_id"]))
        elif r.get("judgment_id") and jmap[r["judgment_id"]].get("conclusion_status") == "判断保留" and r.get("apply_to_word"): err("%s: 判断保留の判断に基づく修正をWord反映対象にしている" % rid)
    # ---- 合理性評価(法的有効性と契約条件の合理性の分離)
    ta = {t.get("judgment_id"): t for t in rv.get("term_assessments", [])}
    ctext = L.norm(contract_text) if contract_text else None
    for j in rv.get("judgments", []):
        t = ta.get(j.get("id")); jid = j.get("id")
        sensitive = bool(j.get("numbers")) or any(r.get("judgment_id") == jid for r in rv.get("revisions", [])) or j.get("category") in ("A", "B")
        if sensitive and tier != "light" and t is None: err("%s: 数値条件・修正・重大分類を含むのに合理性評価(term_assessments)がない" % jid); continue
        if t is None: continue
        dims = t.get("dimensions") or {}
        miss = [k for k in DIMS if k not in dims]
        if miss: err("%s: 評価軸が欠落%s(法的有効性と合理性等は独立に評価する)" % (jid, miss))
        for k in DIMS:
            v = dims.get(k)
            if not v: continue
            if v.get("status") not in ST: err("%s: 評価軸%sのstatusが不正" % (jid, k))
            if v.get("status") == "評価済" and len((v.get("assessment") or "").strip()) < 15: err("%s: 評価軸%sが『評価済』だが評価内容が実質的でない" % (jid, k))
        dec = t.get("revision_decision"); er = dims.get("economic_rationality") or {}
        if dec not in ("修正要", "修正不要", "判断保留"): err("%s: revision_decisionが不正" % jid)
        if dec == "修正不要":
            reason = t.get("no_revision_reason") or ""
            if er.get("status") != "評価済": err("%s: 経済的合理性が『%s』のまま修正不要と判断(任意設定/法令に禁止なしのみでは修正不要の根拠にならない)" % (jid, er.get("status")))
            if ONLY_VOLUNTARY.search(reason) and len((er.get("assessment") or "")) < 30: err("%s: 修正不要の理由が任意設定/禁止なし等のみで、経済的合理性の実質的な評価がない" % jid)
        if dec == "判断保留" and any(r.get("judgment_id") == jid and r.get("apply_to_word") for r in rv.get("revisions", [])): err("%s: 判断保留の項目に断定的修正" % jid)
        lv = (dims.get("legal_validity") or {}).get("assessment", "") + (t.get("legal_conclusion") or "")
        if re.search(r"(違法|無効|公序良俗違反)", lv) and not j.get("claims") and "(無効とは判断しない)" not in lv: err("%s: 法令根拠(claims)なしに違法/無効と記載" % jid)
        if NUMBER_BIG_ONLY.search(lv + (t.get("no_revision_reason") or "") + " ".join((r.get("reason") or "") for r in rv.get("revisions", []) if r.get("judgment_id") == jid)): err("%s: 数値が大きいことのみを理由に違法/無効としている" % jid)
    # ---- 数値条件の重点審査
    nr = {n.get("judgment_id"): n for n in rv.get("numeric_reviews", [])}
    for j in rv.get("judgments", []):
        for n in j.get("numbers", []):
            if j.get("id") not in nr and tier != "light": err("%s: 数値『%s』を含むが数値条件の重点審査(numeric_reviews)がない" % (j.get("id"), n.get("label")))
    for n in rv.get("numeric_reviews", []):
        lab = n.get("term_label"); chk = n.get("checks") or {}
        for k in NUMS:
            v = chk.get(k)
            if not v: err("数値審査『%s』: 検証項目%sが欠落" % (lab, k)); continue
            if v.get("status") not in ST: err("数値審査『%s』: %sのstatusが不正" % (lab, k))
            if v.get("status") == "評価済" and len((v.get("text") or "").strip()) < 15: err("数値審査『%s』: %sが評価済だが内容が実質的でない" % (lab, k))
        if ctext is not None and not (L.norm(n.get("value_text", "")) and L.norm(n["value_text"]) in ctext): err("数値審査『%s』: 数値『%s』が契約書原文に見つからない(誤読/捏造の疑い)" % (lab, n.get("value_text")))
        for ex in n.get("calc_examples", []):
            if not ex.get("assumed"): err("数値審査『%s』: 計算例の仮定値がassumed=trueで明示されていない(実際の契約条件との区別)" % lab)
            r = recompute(ex)
            if r is None: err("数値審査『%s』: 計算例を再計算できない(type/assumptions不備)" % lab)
            elif r != ex.get("result_yen"): err("数値審査『%s』: 計算例の結果%sが再計算%sと不一致" % (lab, ex.get("result_yen"), r))
        if n.get("burden_on") not in ("当社", "相手方"): err("数値審査『%s』: 負担者(当社/相手方)が不明" % lab)
        else:
            lbl = (rv.get("our_role") or {}).get("label")
            if not lbl: err("当社の契約上の立場(our_role.label)が未記載")
            elif n.get("payer") and ((n["payer"] == lbl) != (n["burden_on"] == "当社")): err("数値審査『%s』: 支払者%sと当社(%s)の対応から負担者は『%s』のはずだが『%s』と記載(当事者の立場の誤認)" % (lab, n["payer"], lbl, "当社" if n["payer"] == lbl else "相手方", n["burden_on"]))
        for sv, kd, ms in R5.penalty_findings(n, tier): F.append({"severity": sv, "kind": kd, "message": ms})
        F.append({"severity": "info", "kind": "要人間判断", "message": "数値審査『%s』: 設定根拠・経済的合理性・損害との関係の妥当性は機械判定不能(記載の有無と整合のみ検査)" % lab})
    for sv, kd, ms in R5.issue_group_findings(rv, contract_text): F.append({"severity": sv, "kind": kd, "message": ms})
    for r in rv.get("revisions", []):   # 事実確認の分類を『コメントのみ』出力のために流用しない(出力形式はoutput_formで指定)
        if r.get("finding_type") == "fact_check" and not (r.get("required_facts") or []): err("%s: finding_type=fact_check だが確認すべき事実(required_facts)がない。コメントのみにしたいだけなら output_form=comment_only を使う" % r.get("revision_id"))
        if r.get("output_form") not in (None, "tracked", "comment_only"): err("%s: output_formが不正" % r.get("revision_id"))
    for sv in R5.scan_unverified_legal({"review": rv}): err("未確認の法的判断の断定(一次資料で確認できない場合は断定しない): %s『%s』" % (sv["where"], sv["sentence"]))
    if contract_text is not None:   # 条項カバレッジ(再現性のための判断単位の固定): 契約書の各「第N条」に判断が1件以上あること
        arts = re.findall(r"^(第[0-9０-９一二三四五六七八九十]+条)", contract_text, flags=re.M)
        have = " ".join((j.get("clause") or "") for j in rv.get("judgments", []))
        miss = [a_ for a_ in arts if a_ not in have]
        if miss: err("契約書の条項%sに対する判断(judgment.clause)がない(判断単位の欠落)" % miss)
    if contract_text is not None and (rv.get("our_role") or {}).get("label") and L.norm(rv["our_role"]["label"]) not in ctext: err("our_role.label『%s』が契約書原文に存在しない" % rv["our_role"]["label"])
    return F, eng
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("review"); ap.add_argument("--cache-dir"); ap.add_argument("--today"); ap.add_argument("--contract"); a = ap.parse_args()
    ct = open(a.contract, encoding="utf-8").read() if a.contract else None
    F, eng = gate(json.load(open(a.review, encoding="utf-8")), a.cache_dir, a.today, ct)
    for f in F: print("[%s/%s] %s" % (f["severity"], f["kind"], f["message"]))
    errs = [f for f in F if f["severity"] == "error"]; print("RESULT:", "FAIL" if errs else "PASS", "errors=%d human_review_items=%d" % (len(errs), len(F) - len(errs)), "※合格は手続上の不備が検出されなかったことのみを意味し、法的判断の正確性を保証しない"); sys.exit(1 if errs else 0)
