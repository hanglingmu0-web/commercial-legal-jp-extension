#!/usr/bin/env python3
"""レビュー結果JSON(judgments/evidence/revisions)の機械的な品質検査。
AIの法的判断の「正しさ」は検査できないが、根拠欠落・要件未確認の断定・根拠なき数値・未確認資料の引用など、
手続上の違反を確実に検出する。違反があれば終了コード1。
"""
import sys, json
REQ_OK = {"充足", "不充足", "事実関係不明", "法的解釈未確定", "該当なし"}
CONC = {"確定", "条件付き", "判断保留"}
CATS = set("ABCDEFG")
def check(d):
    e = []
    ev = {x["id"]: x for x in d.get("evidence", [])}
    for x in ev.values():
        for k in ("title", "issuer", "url", "retrieved_at", "source_type", "verified"):
            if k not in x: e.append("evidence %s: 必須項目欠落 %s" % (x.get("id"), k))
    for j in d.get("judgments", []):
        jid = j.get("id", "?")
        if j.get("category") not in CATS: e.append("%s: 分類(A-G)が不正" % jid)
        if j.get("conclusion_status") not in CONC: e.append("%s: conclusion_statusが不正" % jid)
        if not j.get("category_reason"): e.append("%s: 分類理由なし" % jid)
        firm = j.get("conclusion_status") == "確定"
        for s in j.get("statutes", []):
            sid = "%s/%s" % (jid, s.get("name", "?"))
            for k in ("name", "law_number", "article", "effective_status", "reference_date"):
                if not s.get(k): e.append("%s: 法令情報欠落 %s" % (sid, k))
            ids = s.get("evidence_ids", [])
            if not ids: e.append("%s: 根拠資料なし" % sid)
            for i in ids:
                if i not in ev: e.append("%s: 存在しない資料ID %s" % (sid, i))
                elif firm and not ev[i].get("verified"): e.append("%s: 未確認資料を根拠に『確定』" % sid)
            if firm and not any(ev.get(i, {}).get("source_type") == "一次" for i in ids): e.append("%s: 一次資料なしで『確定』" % sid)
            reqs = s.get("requirements", [])
            for r in reqs:
                if r.get("status") not in REQ_OK: e.append("%s: 要件判定が不正 %r" % (sid, r.get("status")))
                if not r.get("basis"): e.append("%s: 要件『%s』に判定理由なし" % (sid, r.get("name")))
            must = [r for r in reqs if r.get("group", "必須") != "選択肢" and r.get("status") != "該当なし"]
            alts = [r for r in reqs if r.get("group") == "選択肢"]
            bad = (not reqs) or any(r.get("status") != "充足" for r in must) or (alts and not any(r.get("status") == "充足" for r in alts))
            if s.get("asserted_applicable") and bad:
                e.append("%s: 適用要件が全て充足でないのに適用を断定" % sid)
            if s.get("effective_status") in ("未施行", "廃止") and s.get("asserted_applicable"):
                e.append("%s: %sの法令を現行法として適用" % (sid, s["effective_status"]))
            if j.get("legally_mandatory") and not s.get("asserted_applicable"):
                e.append("%s: 適用未確定なのに法令上必須と表示" % sid)
        for n in j.get("numbers", []):
            if not (n.get("evidence_ids") or n.get("internal_standard_id") or n.get("negotiation_basis")):
                e.append("%s: 数値『%s』に根拠なし" % (jid, n.get("label")))
    for r in d.get("revisions", []):
        rid = r.get("revision_id", "?")
        if not r.get("reason"): e.append("%s: 修正理由なし" % rid)
        if r.get("verification_status") == "判断保留" and r.get("apply_to_word"): e.append("%s: 判断保留の修正をWord反映対象にしている" % rid)
        if r.get("original_text") == r.get("revised_text"): e.append("%s: 原文と同一の修正" % rid)
        for i in r.get("evidence_ids", []):
            if i not in ev: e.append("%s: 存在しない資料ID %s" % (rid, i))
    return e
if __name__ == "__main__":
    errs = check(json.load(open(sys.argv[1], encoding="utf-8")))
    for x in errs: print("NG:", x)
    print("RESULT:", "FAIL" if errs else "PASS"); sys.exit(1 if errs else 0)
