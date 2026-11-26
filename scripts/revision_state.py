#!/usr/bin/env python3
"""修正案ごとの『Word反映可否の状態』を独立した条件で判定する。AI同士の一致は『検証済み』の根拠にしない(条件の1つに過ぎない)。
  revision_state.py <案件dir> --contract contract.txt [--facts facts.json] [--profile-loaded] [--outdir D]
状態(6): 検証済み・反映可能 / 条件付き・要確認 / 根拠資料未確認 / 重大な不一致あり / 修正不要 / 判断保留
条件(独立評価): c1契約文整合 c2適用要件 c3一次資料の信頼度 c4根拠の整合(evidence verified) c5実務プロファイル整合 c6経済合理性の評価の存在 c7独立検証の実施 c8未解消の重大不一致 c9反証レビュー(高リスクのみ) c10機械的チェック
機械的修正(誤字・条番号・明白な計算誤り・明白な内部矛盾): revision.mechanical_kind を typo/clause_ref/contradiction で指定した場合、c1・c10と種別固有の機械検査のみで『検証済み・反映可能(機械的)』になり得る(法的判断を含まない修正に限る)。
Word成果物の区分(v0.4): 検証済みの修正(正式な変更履歴+コメント) / 交渉上の提案(提案と明示。必須修正として扱わない) / 確認事項(コメントのみ) / 反映禁止
指摘の種別 finding_type: law(法令の適用・解釈) contract_text(契約書原文) consistency(条項間整合) economic(経済的合理性) risk_allocation(契約条件・リスク配分) internal_standard(社内審査基準) format(文言・形式) fact_check(事実確認)
 ・contract_text/consistency/format は法令調査・実務プロファイルを要求しない(原文一致・独立検証・不一致なしで『検証済み』になり得る)。未指定の場合は推定(法令依存→law、それ以外→risk_allocation=提案止まり)し、推定である旨を記録する。
出力: revision_states.json / approved_revisions.json / proposed_revisions.json / confirmations.json / blocked_revisions.json / word_revisions.json(前3者の統合。apply_revisions.py用)"""
import sys, os, json, re, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import legal_sources as L, rules_v5 as R5
def nkey(k):
    m = re.match(r"^(第[0-9０-９]+条)", k or ""); return m.group(1) if m else ("契約全体" if (k or "").startswith("契約全体") else k)
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("dir"); ap.add_argument("--contract", required=True); ap.add_argument("--facts"); ap.add_argument("--profile-loaded", action="store_true"); ap.add_argument("--outdir"); a = ap.parse_args()
    fr = json.load(open(os.path.join(a.dir, "first", "review.json"), encoding="utf-8")); vr = json.load(open(os.path.join(a.dir, "verifier", "review_verifier.json"), encoding="utf-8"))
    text = open(a.contract, encoding="utf-8").read(); outdir = a.outdir or a.dir; os.makedirs(outdir, exist_ok=True)
    dis = json.load(open(os.path.join(a.dir, "disagreements.json"), encoding="utf-8"))["items"] if os.path.isfile(os.path.join(a.dir, "disagreements.json")) else []
    adv = os.path.isdir(os.path.join(a.dir, "adversarial")) and any(f.endswith(".json") for f in os.listdir(os.path.join(a.dir, "adversarial")))
    app = None
    if a.facts:
        import applicability as AP; app = AP.judge(json.load(open(a.facts, encoding="utf-8")))
    applied = bool(app and str(app.get("overall", "")).startswith("適用あり")); firm = any("一次・原文(機械取得" in L.reliability(L.load(s)) for s in L.all_sources())
    jmap = {j["id"]: j for j in fr["judgments"]}; vclause = {nkey(j.get("clause")): j for j in vr["judgments"]}; vrev = {nkey(next((j for j in vr["judgments"] if j["id"] == r.get("judgment_id")), {}).get("clause")) for r in vr.get("revisions", [])}
    cpath = os.path.join(a.dir, "revision_checks.json"); checks = {x["revision_id"]: x for x in json.load(open(cpath, encoding="utf-8")).get("checks", [])} if os.path.isfile(cpath) else {}
    ev = {e["id"]: e for e in fr.get("evidence", [])}; states = []; approved = []; proposed = []; confirms = []; blocked = []
    for r in fr.get("revisions", []):
        j = jmap.get(r.get("judgment_id"), {}); k = nkey(j.get("clause")); dep = bool(r.get("depends_on_statute")); mk = r.get("mechanical_kind"); c = {}
        oc = text.count(r.get("original_text", "")); c["c1契約文整合"] = (oc == 1, "原文に1件一致" if oc == 1 else "原文との一致%d件" % oc)
        refs = re.findall(r"第[0-9０-９]+条", r.get("revised_text", "")); bad = [x for x in refs if x not in text and x not in fr_text_clauses(fr)]
        bad += ["%s第%s項(項が存在しない)" % (cc, pp) for cc, pp in R5.ref_targets(r.get("revised_text", ""), k) if pp and R5.clause_block(text, cc) is not None and not R5.paragraph_exists(text, cc, pp)]
        c["c10機械的チェック"] = (r.get("revised_text") != r.get("original_text") and not bad, "文言変更あり・参照条番号%s" % ("不正" + str(bad) if bad else "OK"))
        c["c2適用要件"] = (not dep or applied, "法令非依存" if not dep else "適用判定=%s" % (app and app.get("overall")))
        c["c3一次資料の信頼度"] = (not dep or firm, "法令非依存" if not dep else "機械取得原文=%s" % firm)
        c["c4根拠の整合"] = (all(ev.get(i, {}).get("verified") for i in r.get("evidence_ids", [])) if r.get("evidence_ids") else (not dep), "evidence verified: %s" % [ev.get(i, {}).get("verified") for i in r.get("evidence_ids", [])])
        c["c5実務プロファイル整合"] = (a.profile_loaded, "照合済" if a.profile_loaded else "未読込のため未評価")
        c["c6経済合理性の評価"] = (any(t.get("judgment_id") == j.get("id") or nkey(t.get("clause")) == k for t in fr.get("term_assessments", [])) or bool(j.get("summary")), "評価欄の存在(内容の適否は別)")
        vo = [x.get("original_text", "") for x in vr.get("revisions", []) if nkey(next((j2 for j2 in vr["judgments"] if j2["id"] == x.get("judgment_id")), {}).get("clause")) == k]
        same_loc = any(o and (o in r.get("original_text", "") or r.get("original_text", "") in o) for o in vo)
        ck = checks.get(r["revision_id"])
        if ck is None:
            c["c7独立検証"] = (False, "修正文の独立検証記録(10観点)なし。同一箇所に独立再検証者の修正案が%s(位置の一致のみでは検証済みとしない)" % ("あり" if same_loc else "ない"))
        else:
            ok7, n7 = check_ok(ck); c["c7独立検証"] = (ok7, n7)
        ds = [d for d in dis if d["clause"] == k and (d["serious"] or d["result"].startswith("未解消") or d["result"] == "保守側で保留")]
        c["c8未解消の重大不一致"] = (not [d for d in ds if d["serious"]], "重大な不一致なし" if not [d for d in ds if d["serious"]] else "重大な不一致%d件" % len([d for d in ds if d["serious"]]))
        c["c9反証レビュー"] = (adv or fr.get("risk_tier") != "high", "実施済" if adv else ("不要(高リスク以外)" if fr.get("risk_tier") != "high" else "高リスク案件だが未実施"))
        det = {x: {"ok": v[0], "note": v[1]} for x, v in c.items()}
        ft = r.get("finding_type"); ft_src = "明示"
        if ft not in FT:
            ft_src = "推定(要確認)"; ft = "law" if dep else "risk_allocation"
        objective_ok = c["c1契約文整合"][0] and c["c10機械的チェック"][0]
        a_unres = [d for d in ds if d.get("kind") == "A" and d["result"].startswith("未解消")] if ds and "kind" in ds[0] else [d for d in ds if d["serious"]]
        if not c["c1契約文整合"][0]:
            wc, st, why = "反映禁止", "反映禁止", "修正対象文言が契約書原文と一致しない/特定できない(誤引用・新設条項は位置指定が必要)"
        elif not c["c10機械的チェック"][0]:
            wc, st, why = "反映禁止", "反映禁止", "機械チェック不合格(文言変更なし/参照条番号不正)"
        elif a_unres:
            wc, st, why = "反映禁止", "重大な不一致あり", "客観的に解消すべき不一致が未解消(原文・数値・事実等)"
        elif mk in ("typo", "clause_ref", "contradiction"):
            wc, st, why = "検証済みの修正", "検証済み・反映可能", "機械的修正(%s): 原文一致と機械チェックのみで判定" % mk
        elif ft == "law":
            if c["c2適用要件"][0] and c["c3一次資料の信頼度"][0] and c["c4根拠の整合"][0] and c["c7独立検証"][0] and c["c9反証レビュー"][0]:
                wc, st, why = "検証済みの修正", "検証済み・反映可能", "法令根拠(機械取得原文・適用あり)・独立検証あり"
            else:
                wc, st, why = "確認事項", "根拠資料未確認", "法令の適用/解釈が根拠だが、一次資料(機械取得)または適用要件が未確認。修正としては反映せず、確認事項として示す"
        elif ft in ("contract_text", "consistency", "format"):
            if c["c7独立検証"][0] and c["c9反証レビュー"][0]:
                wc, st, why = "検証済みの修正", "検証済み・反映可能", "契約書原文に基づく指摘(%s)。法令調査は不要。修正文の独立検証: %s。反証レビュー: %s。承認は人間" % (FT[ft], c["c7独立検証"][1], c["c9反証レビュー"][1])
            else:
                wc, st, why = "交渉上の提案", "条件付き・要確認", "契約書原文に基づくが、独立検証または反証レビューが未了: " + ", ".join(x for x in ("c7独立検証", "c9反証レビュー") if not c[x][0])
        elif ft == "internal_standard":
            if a.profile_loaded: wc, st, why = "検証済みの修正", "条件付き・要確認", "社内基準に基づく(プロファイル読込済。基準の確定状態は人間確認)"
            else: wc, st, why = "確認事項", "条件付き・要確認", "社内審査基準に基づく指摘だが、当社の確定した基準が未読込のため修正としては扱わない"
        elif ft == "fact_check":
            wc, st, why = "確認事項", "条件付き・要確認", "事実関係の確認を要する事項"
        else:  # economic / risk_allocation
            wc, st, why = "交渉上の提案", "条件付き・要確認", "経済合理性/契約条件・リスク配分に関する提案(複数の合理的選択肢があり得る。法令上必須の修正ではない)"
        if j.get("conclusion_status") == "判断保留" and wc == "検証済みの修正" and ft not in ("contract_text", "consistency", "format"): wc, st, why = "確認事項", "判断保留", "判断が保留されている"
        if r.get("output_form") == "comment_only" and wc in ("検証済みの修正", "交渉上の提案"):   # 出力形式の指定。指摘の種別(finding_type)は変えない
            wc = "確認事項"; why = "コメントのみで提示(output_form=comment_only)。" + why
        rec = {"revision_id": r["revision_id"], "clause": k, "state": st, "word_class": wc, "finding_type": ft, "finding_type_source": ft_src, "reason": why, "conditions": det, "apply_to_word_requested": bool(r.get("apply_to_word"))}; states.append(rec)
        ctitle = {"検証済みの修正": "【AI案・人間確認要】", "交渉上の提案": "【交渉上の提案(必須修正ではありません)】", "確認事項": "【確認事項】", "反映禁止": ""}[wc]
        item = {"revision_id": r["revision_id"], "clause": k, "revision_class": wc, "finding_type": ft, "original_text": r["original_text"], "revised_text": r["revised_text"], "comment": ctitle + (r.get("reason") or "") + ("\n[判断に必要な情報] " + why), "external_reason": r.get("external_reason"), "external_question": r.get("external_question"), "internal_only": bool(r.get("internal_only"))}
        if wc == "検証済みの修正" and (r.get("apply_to_word") or mk): approved.append(item)
        elif wc == "交渉上の提案": proposed.append(item)
        elif wc == "確認事項" and c["c1契約文整合"][0]: confirms.append(dict(item, revised_text=r["original_text"], comment_only=True))
        elif wc == "反映禁止": blocked.append(dict(item, reason=why))
    for j in fr["judgments"]:
        if not any(r.get("judgment_id") == j["id"] for r in fr.get("revisions", [])):
            states.append({"judgment_id": j["id"], "clause": nkey(j.get("clause")), "state": "判断保留" if j.get("conclusion_status") == "判断保留" else "修正不要", "reason": "初回判断に修正案なし(独立再検証は%s)" % ("修正案あり→不一致として別途扱う" if nkey(j.get("clause")) in vrev else "修正案なし")})
    # ---- v0.5 後処理: 参照先の健全性(準用で問題を他条項へ拡張しない)・4層の検証状況
    ref_notes = {}
    for _ in range(3):
        cu = R5.clause_unresolved_map(fr, states, nkey); changed = False
        for r in fr.get("revisions", []):
            rid = r["revision_id"]; k = nkey(next((j for j in fr["judgments"] if j["id"] == r.get("judgment_id")), {}).get("clause"))
            hard, soft = R5.ref_problems(r, text, k, cu)
            if r.get("mechanical_kind") == "clause_ref" and "準用" not in r.get("revised_text", ""): soft = []   # 誤った参照番号を改めるだけの修正は参照先の内容を取り込まない
            it = next((x for x in approved if x["revision_id"] == rid), None)
            if soft:
                ref_notes[rid] = soft
                if it is not None:
                    approved.remove(it); it["revision_class"] = "交渉上の提案"; it["comment"] = it["comment"].replace("【AI案・人間確認要】", "【交渉上の提案(必須修正ではありません)】", 1) + "\n[参照先の未解消事項] この修正は他の条項を引用・準用しており、参照先に未解消の問題があるため条件付きで提示する: " + " / ".join(soft)
                    proposed.append(it); changed = True
                    for st_ in states:
                        if st_.get("revision_id") == rid: st_["state"] = "条件付き・要確認"; st_["word_class"] = "交渉上の提案"; st_["reason"] = "参照先条項に未解消の問題(%s)。問題を準用により拡張しないため条件付き" % "; ".join(soft)
        if not changed: break
    ctk = {R5.z2h(k): v for k, v in cu.items()}
    nreview = {}
    for n_ in fr.get("numeric_reviews", []):
        if R5.is_penalty_like(n_):
            jj = next((j for j in fr["judgments"] if j["id"] == n_.get("judgment_id")), {}); nreview.setdefault(nkey(jj.get("clause")), []).append(n_)
    groups_ = fr.get("issue_groups") or []; rank = {"検証済": 3, "条件付き": 2, "未検証": 1, "問題あり": 0}; rev_ = {3: "検証済", 2: "条件付き", 1: "未検証", 0: "問題あり"}
    for st_ in states:
        if not st_.get("revision_id"): continue
        k = st_["clause"]; cnd = st_["conditions"]; rid = st_["revision_id"]
        wording = "検証済" if cnd["c1契約文整合"]["ok"] and cnd["c10機械的チェック"]["ok"] else "問題あり"
        if st_.get("word_class") == "反映禁止": effect = "問題あり"
        elif st_["state"] == "検証済み・反映可能": effect = "検証済"
        elif cnd["c7独立検証"]["ok"] and st_["state"] != "重大な不一致あり": effect = "条件付き"
        else: effect = "未検証"
        if rid in ref_notes and effect == "検証済": effect = "条件付き"
        num_un = [n_.get("term_label") for n_ in nreview.get(k, []) if n_.get("rationality_status") != "確認済"]
        own_un = [x for x in cu.get(k, []) if not x.startswith("修正%s=" % rid)]
        clause = effect if not (num_un or own_un) else ("条件付き" if rank[effect] >= 2 else effect)
        if num_un or own_un: clause = rev_[min(rank[effect], 2)]
        gs = [g for g in groups_ if g.get("applicable") is not False and k in (g.get("related_clauses") or [])]
        issue = rev_[min([rank[clause]] + [rank.get(g.get("issue_status"), 1) for g in gs])] if gs else "対象論点なし"
        st_["layers"] = {"修正文言": wording, "修正文案の法的効果": effect, "条項全体": clause, "関連条項を含む論点全体": issue}
        st_["layer_notes"] = {"数値の合理性が未確認の項目": num_un, "同一条項の未解消事項": own_un, "参照先の未解消事項": ref_notes.get(rid, []), "関連論点": [g.get("id") or g.get("topic_key") for g in gs]}
        for lst in (approved, proposed, confirms):
            for it in lst:
                if it["revision_id"] == rid and num_un and "数値そのものの合理性は未確認" not in it["comment"]:
                    it["comment"] += "\n[注意] 数値そのものの合理性(%s)は未確認のため、この修正で条項全体が検証済みになったわけではありません。" % "、".join(num_un)
    json.dump(states, open(os.path.join(outdir, "revision_states.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 同一箇所の複数案: 先頭案を機械的に採用しない。option_selection.json の選定記録(理由つき)がある場合のみ選定案を反映する
    opath = os.path.join(a.dir, "option_selection.json"); osel = json.load(open(opath, encoding="utf-8")).get("groups", []) if os.path.isfile(opath) else []
    allit = [("approved", i) for i in approved] + [("proposed", i) for i in proposed] + [("confirm", i) for i in confirms]
    groups = []; used = set()
    for idx, (_, it) in enumerate(allit):
        if idx in used: continue
        mem = [idx]; used.add(idx)
        for jdx, (_, jt) in enumerate(allit):
            if jdx not in used and jt["clause"] == it["clause"] and (jt["original_text"] in it["original_text"] or it["original_text"] in jt["original_text"]): mem.append(jdx); used.add(jdx)
        if len(mem) > 1: groups.append(mem)
    group_log = []; drop = set()
    for mem in groups:
        ids = [allit[m][1]["revision_id"] for m in mem]; rec = next((g for g in osel if set(g.get("options_ids", [])) == set(ids)), None)
        valid = bool(rec) and (rec.get("reason") or "").strip() and all(i in (rec.get("evaluations") or {}) for i in ids)
        lines = "\n".join("・%s: %s" % (i, allit[m][1]["revised_text"]) for i, m in zip(ids, mem))
        if valid and rec.get("selected") in ids:
            sel = rec["selected"]
            for i, m in zip(ids, mem):
                if i != sel:
                    drop.add(i); sm = next(x for x in allit if x[1]["revision_id"] == sel)[1]
                    sm["comment"] += "\n【同一箇所の他案(不採用)】%s: %s\n理由: %s" % (i, allit[m][1]["revised_text"], (rec["evaluations"][i] or {}).get("note", rec["reason"]))
            sm["comment"] += "\n【選定理由】" + rec["reason"]
            group_log.append({"ids": ids, "result": "選定案を反映", "selected": sel, "reason": rec["reason"]})
        elif valid and rec.get("needs_management_judgment"):
            first_m = mem[0]; it0 = allit[first_m][1]
            for i, m in zip(ids, mem):
                if m != first_m: drop.add(i)
            for st_ in states:
                if st_.get("revision_id") == it0["revision_id"]: st_["state"] = "複数案・要判断"; st_["word_class"] = "確認事項"
            it0["revision_class"] = "確認事項"; it0["comment_only"] = True; it0["revised_text"] = it0["original_text"]
            it0["comment"] = "【確認事項・複数案(経営判断/取引判断が必要)】\n" + lines + "\n判断が必要な理由: " + rec["reason"]
            for lst in (approved, proposed): 
                if it0 in lst: lst.remove(it0); confirms.append(it0)
            group_log.append({"ids": ids, "result": "複数案をコメントで提示(要判断)", "reason": rec["reason"]})
        else:
            first_m = mem[0]; it0 = allit[first_m][1]
            for i, m in zip(ids, mem):
                if m != first_m: drop.add(i)
            for st_ in states:
                if st_.get("revision_id") == it0["revision_id"]: st_["state"] = "複数案・選定記録なし"; st_["word_class"] = "確認事項"
            it0["revision_class"] = "確認事項"; it0["comment_only"] = True; it0["revised_text"] = it0["original_text"]
            it0["comment"] = "【確認事項・同一箇所に複数案(選定理由の記録なしのため反映せず)】\n" + lines
            for lst in (approved, proposed):
                if it0 in lst: lst.remove(it0); confirms.append(it0)
            group_log.append({"ids": ids, "result": "選定記録なし→反映せず(先頭案の機械的採用はしない)"})
    for lst in (approved, proposed, confirms): lst[:] = [x for x in lst if x["revision_id"] not in drop]
    for st_ in states:
        if st_.get("revision_id") in drop: st_["state"] = "複数案(他案)"; st_["word_class"] = "複数案の一部(別案を参照)"
    json.dump(group_log, open(os.path.join(outdir, "option_groups.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for nm, v in (("approved_revisions", approved), ("proposed_revisions", proposed), ("confirmations", confirms), ("blocked_revisions", blocked), ("word_revisions", approved + proposed + confirms)):
        json.dump(v, open(os.path.join(outdir, nm + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # ---- 相手方提示用: 修正文案+必要最小限の理由+相手方への確認事項のみ。内部判断・AI処理・未採用案は含めない。承認と送信は人間
    ext = []; ext_missing = []
    for it in approved + proposed + confirms:
        if it.get("internal_only"): continue
        er = (it.get("external_reason") or "").strip(); eq = (it.get("external_question") or "").strip()
        if it.get("comment_only") and not eq: continue
        if not er and not it.get("comment_only"): ext_missing.append(it["revision_id"]); er = "修正のご提案です。ご確認をお願いします。"
        c_ = er + (("\n確認事項: " + eq) if eq else "")
        ext.append({"revision_id": it["revision_id"], "clause": it["clause"], "revision_class": "相手方提示", "original_text": it["original_text"], "revised_text": it["revised_text"], "comment": c_, **({"comment_only": True} if it.get("comment_only") else {})})
    json.dump(ext, open(os.path.join(outdir, "word_revisions_external.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"external_reason未作成": ext_missing, "leaks": R5.external_leaks(ext)}, open(os.path.join(outdir, "external_check.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter; print(dict(Counter(s["state"] for s in states))); print("Word: 検証済み=%d / 交渉上の提案=%d / 確認事項=%d / 反映禁止=%d" % (len(approved), len(proposed), len(confirms), len(blocked)))
    for s_ in states: print(" ", s_.get("revision_id", s_.get("judgment_id")), s_["clause"], s_["state"], s_.get("word_class",""), s_.get("finding_type",""), "|", s_["reason"][:60])
FT = {"law": "法令の適用・解釈", "contract_text": "契約書原文", "consistency": "条項間の整合", "economic": "経済的合理性", "risk_allocation": "契約条件・リスク配分", "internal_standard": "社内審査基準", "format": "文言・形式", "fact_check": "事実確認"}
AX = ["1問題箇所", "2問題認識", "3修正の必要性", "4修正理由", "5修正方針", "6修正文案の意味", "7修正後の権利義務", "8修正後の法的経済的効果", "9他条項との整合", "10新たなリスク"]
def check_ok(ck):
    ag = ck.get("content_agreement"); ax = ck.get("axes") or {}; miss = [x for x in AX if x not in ax]
    if miss: return False, "10観点のうち記録なし: %s" % miss
    if not ck.get("adopted_text_verified"): return False, "最終採用文言そのものの検証記録なし"
    bad = [x for x in AX if ax[x] in ("相違", "問題あり", "未検証")]
    if ag not in ("一致", "文言差のみ"): return False, "内容の一致なし(%s): %s" % (ag, ck.get("difference_note", ""))
    if bad: return False, "観点に相違/問題/未検証: %s" % bad
    return True, "10観点検証済(内容=%s%s)。一致は正確性の証明ではない" % (ag, ("・差異: " + ck.get("difference_note", "")) if ck.get("difference_note") else "")
def fr_text_clauses(fr): return {nkey(j.get("clause")) for j in fr.get("judgments", [])}
if __name__ == "__main__": main()
