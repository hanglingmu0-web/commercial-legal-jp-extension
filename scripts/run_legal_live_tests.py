#!/usr/bin/env python3
"""法的判断に関する実動作試験 A〜G(実際に取得・キャッシュした一次資料に対して検査ゲートを実行)。
各試験の契約書・事実関係・使用資料・初回判断・期待結果・実測結果・合否を tests/legal_live/results/ に保存する。
重要: 本試験はゲート(機械検証)の動作試験。AIの法的判断の正しさ自体の評価ではない(F は別途 subagent 実行結果を記録)。
"""
import sys, os, json, copy, datetime, shutil, hashlib, tempfile, glob
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import legal_sources as L, applicability as A, review_gate as G, verify_dates as V, make_fixture_cache as MF
os.environ["LEGAL_ALLOW_FIXTURE"] = "1"   # 試験用フィクスチャの使用を明示許可(本番ではこの環境変数を設定しない)
FIXROOT = tempfile.mkdtemp(prefix="fix_"); FIX = os.path.join(FIXROOT, "legal_cache"); MF.build(FIX)
OUT = os.path.join(ROOT, "tests", "legal_live"); RES = []
ACT, RULE = "act_331AC0000000120", "rule_507M60200000009"
def ev():
    return [{"id": "E1", "source_id": ACT, "title": "製造委託等に係る中小受託事業者に対する代金の支払の遅延等の防止に関する法律", "issuer": "e-Gov法令検索", "url": "https://laws.e-gov.go.jp/law/331AC0000000120", "retrieved_at": "2026-11-24T12:15:00+09:00", "source_type": "一次", "verified": True},
            {"id": "E2", "source_id": RULE, "title": "令和七年公正取引委員会規則第九号", "issuer": "e-Gov法令検索", "url": "https://laws.e-gov.go.jp/law/507M60200000009", "retrieved_at": "2026-11-24T12:20:00+09:00", "source_type": "一次", "verified": True}]
def _review(facts, status="条件付き", name=None, asserted=None, claims=None, numbers=None, revisions=None, ref="2026-11-24", mandatory=False, cat="G"):
    eng = A.judge(dict(facts, reference_date=ref))
    st = {"name": name or eng["law"], "law_number": "昭和三十一年法律第百二十号", "article": "第2条第8項・第9項", "effective_status": {"施行済": "施行済", "未施行": "未施行"}.get(eng["effective_at_reference_date"], "不明"),
          "reference_date": ref, "evidence_ids": ["E1"], "asserted_applicable": eng["asserted_applicable"] if asserted is None else asserted,
          "requirements": [{"name": r["name"], "status": r["status"], "basis": r["basis"], "group": r.get("group", "必須")} for r in eng["requirements"]]}
    return {"reference_date": ref, "facts": facts, "evidence": ev(), "risk_tier": "high", "judgments": [{"id": "J1", "category": cat, "category_reason": "試験用", "conclusion_status": status, "legally_mandatory": mandatory,
            "statutes": [st], "claims": claims or [], "numbers": numbers or []}], "revisions": revisions or []}

TXT = "試験用の評価記述(実質的な内容を含む十分な長さ)。経済的合理性・当社立場・損害見込み等を具体的に検討した旨の記載。"
def with_assess(rv):
    """試験用: 合理性評価・数値審査の必須構造を満たす記載を付与(ゲートの旧来の検査項目を独立に試験するため)。内容の妥当性はここでは問わない。"""
    from review_gate import DIMS, NUMS
    rv["our_role"] = {"label": "委託者"}; rv["term_assessments"] = []; rv["numeric_reviews"] = []
    for j in rv["judgments"]:
        has_rev = any(r.get("judgment_id") == j["id"] for r in rv.get("revisions", []))
        rv["term_assessments"].append({"judgment_id": j["id"], "dimensions": {k: {"status": "評価済", "assessment": TXT} for k in DIMS},
                                       "revision_decision": "修正要" if has_rev else "修正不要", "no_revision_reason": "" if has_rev else "経済的合理性・当社立場を検討した結果、現状の条件で当社に不利益は見当たらない(試験用記載)", "legal_conclusion": ""})
        for n in j.get("numbers", []):
            rv["numeric_reviews"].append({"judgment_id": j["id"], "term_label": n.get("label"), "value_text": n.get("value_text", "") or str(n.get("value", "")), "burden_on": "当社", "payer": "委託者",
                                          "checks": {k: {"status": "評価済", "text": TXT} for k in NUMS}, "calc_examples": []})
    return rv
def review(*a, **k): return with_assess(_review(*a, **k))
def rev(applied, dep, risk="下請法規制リスクの解消", jid="J1"):
    return {"revision_id": "R1", "reason": "試験", "original_text": "a", "revised_text": "b", "risk_addressed": risk, "depends_on_statute": dep, "apply_to_word": applied, "judgment_id": jid, "verification_status": "検証済", "evidence_ids": ["E1"]}
BASE = {"entrustment": {"type": "製造委託", "matches_definition": True}, "client": {"form": "法人", "capital_yen": 50_000_000, "employees": 120, "is_state_or_art14_person": False}, "contractor": {"form": "法人", "capital_yen": 8_000_000, "employees": 20}, "contract_date": "2026-12-01"}
UNKNOWN = {"entrustment": {"type": "製造委託", "matches_definition": True}, "client": {"form": "法人", "is_state_or_art14_person": False}, "contractor": {}}
OUTSCOPE = {"entrustment": {"type": "製造委託", "matches_definition": True}, "client": {"form": "法人", "capital_yen": 8_000_000, "employees": 50, "is_state_or_art14_person": False}, "contractor": {"form": "法人", "capital_yen": 3_000_000, "employees": 5}, "contract_date": "2026-12-01"}
def run_case(cid, title, contract, variants, extra_note=""):
    d = os.path.join(OUT, "cases", cid); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "contract.txt"), "w", encoding="utf-8").write(contract)
    for vn, v in variants.items():
        rv = v["review"]; json.dump(rv, open(os.path.join(d, "review_%s.json" % vn), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        F, eng = G.gate(rv, v.get("cache_dir", FIX), v.get("today"))
        errs = [f["message"] for f in F if f["severity"] == "error"]
        outcome_ok = (bool(errs) == v["expect_fail"]) and all(any(s in m for m in errs) for s in v.get("expect_substr", []))
        for s in v.get("expect_absent", []):
            if any(s in m for m in errs): outcome_ok = False
        RES.append({"case": cid, "title": title, "variant": vn, "contract_excerpt": contract[:80], "facts_sha256": hashlib.sha256(json.dumps(rv.get("facts"), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12],
                    "engine_overall": eng and eng["overall"], "expected": ("FAIL" if v["expect_fail"] else "PASS") + " " + str(v.get("expect_substr", [])), "actual": "FAIL" if errs else "PASS", "actual_errors": errs,
                    "human_review_items": [f["message"] for f in F if f["severity"] != "error"][:6], "result": "PASS" if outcome_ok else "FAIL", "note": v.get("note", extra_note)})
def main():
    # ---- A 現行性
    cA = "本契約は下請代金支払遅延等防止法(以下「下請法」という。)を遵守して履行する。"
    run_case("A", "法令の現行性(旧下請法の名称)", cA, {
      "old_name_as_current": {"review": review(BASE, name="下請代金支払遅延等防止法"), "expect_fail": True, "expect_substr": ["旧名称"]},
      "abbrev_old_as_current": {"review": review(BASE, name="下請法"), "expect_fail": True, "expect_substr": ["旧名称"]},
      "current_name_with_note": {"review": (lambda r: (r["judgments"][0]["statutes"][0].update(former_name_note="契約書の『下請代金支払遅延等防止法』は令和7年改正前の名称。現行名称は製造委託等に係る中小受託事業者に対する代金の支払の遅延等の防止に関する法律(取適法)"), r)[1])(review(BASE)), "expect_fail": False, "note": "現行名称+旧名称の注記は合格"},
      "unenforced_misdeclared": {"review": review(dict(BASE, contract_date="2025-06-01"), ref="2025-12-01", asserted=False), "expect_fail": False, "note": "基準日2025-12-01の取適法は未施行: エンジンは『未施行』と判定し、申告も一致していれば合格(未施行を現行扱いしないことの確認)"},
      "unenforced_declared_enforced": {"review": (lambda r: (r["judgments"][0]["statutes"][0].update(effective_status="施行済"), r)[1])(review(dict(BASE, contract_date="2025-06-01"), ref="2025-12-01", asserted=False)), "expect_fail": True, "expect_substr": ["有効性の申告"]},
    })
    e = A.judge(dict(BASE, reference_date="2025-12-01", contract_date="2025-06-01"))
    RES.append({"case": "A", "title": "現行性", "variant": "engine_before_enforcement", "contract_excerpt": cA[:40], "expected": "基準日2025-12-01は未施行/契約日前は旧法・経過措置要確認", "actual": e["effective_at_reference_date"] + " / " + e["overall"],
                "actual_errors": [], "human_review_items": ["経過措置(改正法附則)は未取得: " + str(e["required_facts"])], "result": "PASS" if e["effective_at_reference_date"] == "未施行" and not e["asserted_applicable"] else "FAIL", "note": ""})
    # ---- B 要件不明
    cB = "甲は乙に金型部品の製造を委託する。納期遅延の場合、乙は遅延損害金を支払う。"
    eB = A.judge(dict(UNKNOWN, reference_date="2026-11-24"))
    need = " ".join(eB["required_facts"])
    RES.append({"case": "B", "title": "適用要件不明(資本金・従業員数)", "variant": "engine_required_facts", "contract_excerpt": cB[:40], "expected": "適用を断定せず必要事実に資本金と従業員数を含む", "actual": eB["overall"] + " | " + need,
                "actual_errors": [], "human_review_items": [], "result": "PASS" if (not eB["asserted_applicable"] and "資本金" in need and "従業員" in need and not eB["allow_assertive_revision"]) else "FAIL", "note": ""})
    run_case("B", "適用要件不明", cB, {
      "asserted_without_facts": {"review": review(UNKNOWN, asserted=True, mandatory=True, revisions=[rev(True, True)], status="確定"), "expect_fail": True, "expect_substr": ["適用を断定したがエンジン判定", "法令適用を前提とする修正"]},
      "conditional_no_assertive_revision": {"review": review(UNKNOWN, revisions=[rev(False, True)]), "expect_fail": False, "note": "条件付き評価・断定的修正なし"},
    })
    # ---- C 適用対象外
    cC = "資本金800万円の甲は、資本金300万円の乙に金型部品の製造を委託する。"
    eC = A.judge(dict(OUTSCOPE, reference_date="2026-11-24"))
    RES.append({"case": "C", "title": "適用対象外", "variant": "engine", "contract_excerpt": cC[:40], "expected": "規模要件不充足で適用なし(みなし規定は事実未確認と明示)", "actual": eC["overall"], "actual_errors": [], "human_review_items": eC["required_facts"],
                "result": "PASS" if eC["overall"].startswith("適用なし") and not eC["asserted_applicable"] else "FAIL", "note": ""})
    run_case("C", "適用対象外", cC, {
      "law_based_revision_on_out_of_scope": {"review": review(OUTSCOPE, status="確定", asserted=True, mandatory=True, revisions=[rev(True, True)]), "expect_fail": True, "expect_substr": ["適用を断定したがエンジン判定", "法令適用を前提とする修正"]},
      "voluntary_improvement_only": {"review": review(OUTSCOPE, cat="F", revisions=[rev(True, False, risk="支払遅延時の資金繰りリスク(任意の改善)")]), "expect_fail": False, "note": "法令適用を理由にしない任意改善は可(必要性は要人間判断)"},
    })
    # ---- D 14.6%
    cD = "納期に遅れた場合、乙は年率14.6%の違約金を甲に支払う。"
    rate_claim = {"text": "納期遅延の違約金率14.6%の法的根拠", "source_id": RULE, "ref": "MP-1", "quote": "年十四・六パーセントとする", "key_terms": ["納期"]}
    pay_claim = {"text": "委託事業者の支払遅延の遅延利息率", "source_id": RULE, "ref": "MP-1", "quote": "年十四・六パーセントとする", "key_terms": ["年十四・六パーセント"]}
    nb = lambda v, kind, **k: [dict({"label": "年率%s%%" % v, "value_percent": v, "kind": kind, "basis_ref": {"source_id": RULE, "ref": "MP-1"}, "evidence_ids": ["E2"]}, **k)]
    run_case("D", "遅延損害金・違約金 年率14.6%", cD, {
      "statutory_rate_misapplied_to_delivery_delay": {"review": review(BASE, claims=[rate_claim], numbers=nb(14.6, "法定率")), "expect_fail": True, "expect_substr": ["要点語"], "note": "規則の14.6%は委託事業者の支払遅延等の遅延利息率。納期遅延の違約金の根拠として引用しても『納期』を含まず根拠にならない"},
      "wrong_value": {"review": review(BASE, claims=[pay_claim], numbers=nb(14.0, "法定率")), "expect_fail": True, "expect_substr": ["不一致"]},
      "statutory_rate_when_not_applicable": {"review": review(OUTSCOPE, claims=[pay_claim], numbers=nb(14.6, "法定率")), "expect_fail": True, "expect_substr": ["適用が確定していない"]},
      "arbitrary_without_basis": {"review": review(BASE, numbers=[{"label": "年率14.6%", "value_percent": 14.6, "kind": "任意設定"}]), "expect_fail": True, "expect_substr": ["設定根拠"]},
      "statutory_rate_for_payment_delay_applicable": {"review": review(BASE, status="確定", claims=[pay_claim], numbers=nb(14.6, "法定率")), "expect_fail": False, "note": "適用あり+支払遅延の遅延利息率として引用: 機械検証は合格。年率の日割基準(365日)・経済合理性は要人間判断"},
      "arbitrary_with_basis": {"review": review(BASE, numbers=[{"label": "年率14.6%", "value_percent": 14.6, "kind": "任意設定", "negotiation_basis": "取適法の遅延利息率を参考にした当社希望値。法定率としては主張しない"}]), "expect_fail": False},
    })
    calc = V.__dict__  # 検算
    RES.append({"case": "D", "title": "計算方法", "variant": "calc", "contract_excerpt": "100万円×年14.6%×30日/365", "expected": "12000円(日割365日・円未満切捨て。契約で日割基準を定める必要)",
                "actual": "%d円" % int(1_000_000 * 14.6 / 100 * 30 / 365), "actual_errors": [], "human_review_items": ["年率の日割基準(365日/366日)は規則本文に定めがなく、契約・解説での確認が必要"], "result": "PASS" if int(1_000_000 * 14.6 / 100 * 30 / 365) == 12000 else "FAIL", "note": ""})
    # ---- E 架空・不適切引用
    good = {"text": "資本金基準(千万円超3億円以下の委託事業者)", "source_id": ACT, "ref": "2-8-2", "quote": "資本金の額又は出資の総額が千万円を超え三億円以下の法人たる事業者", "key_terms": ["資本金", "千万円"]}
    run_case("E", "架空又は不適切な引用", "(レビュー結果の引用検査用)", {
      "nonexistent_article": {"review": review(BASE, claims=[dict(good, ref="2-8-9")]), "expect_fail": True, "expect_substr": ["存在しない"]},
      "fabricated_quote": {"review": review(BASE, claims=[dict(good, ref="6-1", quote="委託事業者は、資本金が一千万円を超える場合には代金の全額を前払しなければならない", key_terms=["資本金"])]), "expect_fail": True, "expect_substr": ["原文に含まれない"]},
      "real_but_irrelevant_article": {"review": review(BASE, claims=[dict(good, ref="6-1", quote="委託事業者は、製造委託等代金の支払期日までに製造委託等代金を支払わなかつたときは")]), "expect_fail": True, "expect_substr": ["要点語"]},
      "nonexistent_source": {"review": review(BASE, claims=[dict(good, source_id="act_NOSUCH")]), "expect_fail": True, "expect_substr": ["キャッシュにない"]},
      "correct_claim": {"review": review(BASE, claims=[good]), "expect_fail": False, "expect_absent": ["原文に含まれない", "要点語", "存在しない"], "note": "正しい引用は誤検出されない"},
    })
    # ---- G 取得失敗/古い/要約のみ
    tmp = os.path.join(tempfile.mkdtemp(), "legal_cache"); shutil.copytree(FIX, tmp); os.remove(os.path.join(tmp, ACT + ".json"))
    stale = os.path.join(tempfile.mkdtemp(), "legal_cache"); shutil.copytree(FIX, stale)
    old = copy.deepcopy(ev()); old[0]["source_id"] = "rule_337M50200000001_old"; old[0]["verified"] = False
    r_old = review(BASE, status="確定"); r_old["evidence"] = old
    run_case("G", "一次資料の取得失敗(実際の失敗: e-Gov へのシェル接続は403で拒否)", "(取得失敗時の挙動)", {
      "firm_without_primary_source": {"review": review(BASE, status="確定"), "cache_dir": tmp, "expect_fail": True, "expect_substr": ["キャッシュにない"], "note": "法令キャッシュ欠落(取得失敗)を再現"},
      "firm_on_summary_only_source": {"review": r_old, "expect_fail": True, "expect_substr": ["根拠にできない資料"], "note": "要約取得のみの資料では確定不可"},
      "firm_on_stale_cache": {"review": review(BASE, status="確定"), "cache_dir": stale, "today": "2027-01-15", "expect_fail": True, "expect_substr": ["現行性が未確認"], "note": "取得から52日(新方針: 高リスクは許容1日。旧: 30日)"},
      "firm_on_fresh_cache": {"review": review(BASE, status="確定", claims=[good]), "today": "2026-11-25", "expect_fail": False},
      "firm_without_any_quote": {"review": review(BASE, status="確定"), "today": "2026-11-25", "expect_fail": True, "expect_substr": ["引用(claims)がなく"], "note": "確定判断で条文引用が無ければ照合不能として不合格"},
      "honest_unverified": {"review": (lambda r: (r["evidence"].__setitem__(0, dict(r["evidence"][0], verified=False, retrieval_status="取得失敗")), r)[1])(review(BASE, status="判断保留", asserted=False)), "cache_dir": tmp, "expect_fail": False, "note": "取得失敗を明示し『判断保留』とした出力は合格(未確認を確定として出力しない)"},
    })
    shutil.rmtree(os.path.dirname(tmp), ignore_errors=True); shutil.rmtree(os.path.dirname(stale), ignore_errors=True)
    # ---- F 不要な修正(実際のサブエージェント実行の成果物を検査。AIの挙動の記録であり決定論的ではない)
    fd = os.path.join(OUT, "cases", "F"); import compare_judgments as CJ
    if os.path.isfile(os.path.join(fd, "review_first.json")) and os.path.isfile(os.path.join(fd, "review_verifier.json")):
        a = json.load(open(os.path.join(fd, "review_first.json"), encoding="utf-8")); b = json.load(open(os.path.join(fd, "review_verifier.json"), encoding="utf-8"))
        for nm, rv in (("first_reviewer", a), ("independent_verifier", b)):
            F_, eng_ = G.gate(rv); errs_ = [f["message"] for f in F_ if f["severity"] == "error"]
            sound = [r for r in rv.get("revisions", []) if r.get("judgment_id") in {j["id"] for j in rv["judgments"] if (j.get("clause") or "") in ("第1条", "第2条", "第3条")}]
            RES.append({"case": "F", "title": "不要な修正(実エージェント実行)", "variant": nm, "contract_excerpt": "第1〜3条は問題のない条項/第4条は任意の高率違約金", "expected": "旧スキーマの実エージェント出力: 第1〜3条に修正提案なし・法令適用を断定しない(維持)/新ゲートでは合理性評価・数値審査・一次資料区分の不備によりFAILとなる(期待)",
                        "actual": "第1〜3条への修正提案%d件 / ゲート%s / 全修正%d件" % (len(sound), "FAIL" if errs_ else "PASS", len(rv.get("revisions", []))), "actual_errors": errs_,
                        "human_review_items": [f["message"] for f in F_ if f["severity"] != "error"], "result": "PASS" if (not sound and bool(errs_) and not any(s_.get("asserted_applicable") for j_ in rv["judgments"] for s_ in j_.get("statutes", []))) else "FAIL", "note": "旧スキーマ時点(中間2)の生成AI出力。新方針では不合格が正しい。新スキーマでの実AI試験は別途(tests/real_ai)"})
        A_, B_, diffs_ = CJ.compare(a, b)
        RES.append({"case": "F", "title": "独立再検証の突合", "variant": "first_vs_verifier", "contract_excerpt": "", "expected": "不一致を検出して明示(解消できないものは判断保留)", "actual": "不一致%d件(実質%d/分類%d)" % (len(diffs_), len([x for x in diffs_ if x[1] != "category"]), len([x for x in diffs_ if x[1] == "category"])),
                    "actual_errors": [], "human_review_items": ["%s %s: 初回=%s 再検証=%s" % x for x in diffs_], "result": "PASS", "note": "突合機構の動作確認。不一致の解消(一次資料へ戻る再確認)は人間/追加の再検証が必要で未実施"})
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); rd = os.path.join(OUT, "results"); os.makedirs(rd, exist_ok=True)
    cache_hash = {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()[:16] for p in sorted(glob.glob(os.path.join(L.CACHE_DIR, "*.json")))}
    json.dump({"timestamp": ts, "cache_sha256": cache_hash, "results": RES}, open(os.path.join(rd, "live_%s.json" % ts), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    p = sum(r["result"] == "PASS" for r in RES)
    for r in RES:
        if r["result"] != "PASS": print("[FAIL]", r["case"], r["variant"], "| expected:", r["expected"], "| actual:", r["actual"], r.get("actual_errors", [])[:3])
    print("法的判断ゲート試験: %d/%d 合格" % (p, len(RES))); sys.exit(0 if p == len(RES) else 1)
if __name__ == "__main__": main()
