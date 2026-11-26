#!/usr/bin/env python3
"""引用検証・整合性検証。機械的な一致確認(実在・書誌・原文ファイル・ハッシュ・ページ・段落・引用文言)と、法律上の関連性・判例の適用可能性の評価を区別する。
前者が全て合格しても後者は保証されない(結果の legal_relevance に常に『未評価』と明記)。未確認資料は確定的に引用できない(firm_citation=false)。"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lk_common import *
REL = "機械的な一致確認の対象外。法律上の関連性・判例の適用可能性(事案の共通点と相違点・適用時期・射程・後続判例/法改正の影響)は人間又は別の評価工程で確認する。"
TEXT_KINDS = ("original_text", "extracted_text", "ocr")
def _passages(parent_type, parent_id):
    p = P("cases" if parent_type == "case" else "knowledge", "passages", parent_id + ".jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.isfile(p) else []
def _quote_check(parent_type, parent_id, passage_id, quote, page, out):
    ps = _passages(parent_type, parent_id)
    if not (passage_id or page is not None or quote): return
    cand = [p for p in ps if (not passage_id or p["passage_id"] == passage_id)]
    if passage_id and not cand: out["errors"].append("引用段落%sが存在しない/当該資料の段落でない" % passage_id); return
    if page is not None:
        cand = [p for p in cand if str(p.get("page")) == str(page)]
        if not cand: out["errors"].append("引用ページ%sに該当する段落がない" % page); return
    if quote:
        hit = [p for p in cand if norm(quote) in norm(p["text"])]
        if not hit: out["errors"].append("引用文言が原文(段落)に見つからない"); out["quote_match"] = False; return
        kinds = {p["kind"] for p in hit}
        if not (kinds & set(TEXT_KINDS)): out["errors"].append("引用文言の一致先が原文でない(%s)。AI要約・訂正案は原文として引用できない" % sorted(kinds)); out["quote_match"] = False; return
        out["quote_match"] = True; out["matched_passage_ids"] = [p["passage_id"] for p in hit]
        if "ocr" in kinds and not (kinds & {"original_text", "extracted_text"}): out["warnings"].append("一致先はOCR結果。条文番号・年月日・事件番号・否定表現の誤読の可能性があるため原本で確認すること")
def verify_case_citation(c):
    """c: {case_id | court+decision_date+case_number, quote?, passage_id?, page?}"""
    out = {"kind": "case", "errors": [], "warnings": [], "legal_relevance": REL, "firm_citation": False, "quote_match": None}
    cid = c.get("case_id")
    if not cid:
        for x in list_ids("cases/metadata"):
            m = load_json(P("cases", "metadata", x + ".json"))
            if re.sub(r"\s", "", m["case_number"]) == re.sub(r"\s", "", c.get("case_number", "")) and m["court"] == c.get("court") and m["decision_date"] == c.get("decision_date"): cid = x
    mp = P("cases", "metadata", str(cid) + ".json") if cid else None
    if not cid or not os.path.isfile(mp): out["errors"].append("判例が未登録(架空/未確認の判例を引用として扱わない)"); out["status"] = "not_registered"; return out
    m = load_json(mp); out["case_id"] = cid
    for k in ("court", "decision_date", "case_number"):
        if c.get(k) and re.sub(r"\s", "", str(c[k])) != re.sub(r"\s", "", str(m[k])): out["errors"].append("%sが登録内容と不一致(引用=%s / 登録=%s)" % (k, c[k], m[k]))
    if m["existence_status"] != "confirmed": out["warnings"].append("判例の実在・事件番号・裁判年月日が未確認")
    if m["fulltext_status"] != "available": out["warnings"].append("判決全文が未登録(全文未確認)")
    else:
        ref = m.get("fulltext_ref") or {}; fp = P(*ref["path"].split("/")) if ref.get("path") else None
        if not fp or not os.path.isfile(fp): out["errors"].append("判決原本ファイルが存在しない")
        elif sha256_file(fp) != ref.get("sha256"): out["errors"].append("判決原本のハッシュ不一致(原本の改変・破損の疑い)")
        if m["original_verification"] != "verified": out["warnings"].append("判決全文の原文照合が未実施")
    _quote_check("case", cid, c.get("passage_id"), c.get("quote"), c.get("page"), out)
    if c.get("quote") and out["quote_match"] is None: out["errors"].append("引用文言の照合ができない(段落データなし)")
    if not m.get("subsequent_cases") and not m.get("appeal_relation"): out["warnings"].append("上級審・後続判例・法令改正の影響が未確認")
    if m["structure_verification"] != "human_checked": out["warnings"].append("構造化結果は人の確認前(判断理由・判示事項は判決全文で確認する)")
    mech = not out["errors"] and (not c.get("quote") or out["quote_match"] is True)
    out["mechanical_match"] = mech
    out["firm_citation"] = bool(mech and m["existence_status"] == "confirmed" and m["fulltext_status"] == "available" and m["original_verification"] == "verified" and c.get("quote"))
    out["status"] = "ok" if mech else "failed"; return out
def verify_knowledge_citation(c):
    """c: {knowledge_id, quote?, passage_id?, page?, as_type?}  as_type='legal_principle'等で引用の性質を主張した場合は登録内容と照合"""
    out = {"kind": "knowledge", "errors": [], "warnings": [], "legal_relevance": REL, "firm_citation": False, "quote_match": None}
    kp = P("knowledge", "structured", str(c.get("knowledge_id")) + ".json")
    if not os.path.isfile(kp): out["errors"].append("知識IDが未登録"); out["status"] = "not_registered"; return out
    k = load_json(kp); sid = k["source_id"]; sp = P("knowledge", "sources", sid + ".json")
    if not os.path.isfile(sp): out["errors"].append("出典資料が未登録"); out["status"] = "failed"; return out
    s = load_json(sp)
    if s["bibliographic_status"] != "confirmed": out["warnings"].append("書誌情報が未確認")
    if s.get("original_path"):
        op = P(*s["original_path"].split("/"))
        if not os.path.isfile(op): out["errors"].append("原資料ファイルが存在しない")
        elif sha256_file(op) != s.get("sha256"): out["errors"].append("原資料のハッシュ不一致")
    else: out["warnings"].append("原資料ファイルが未登録(原文未確認)")
    if c.get("as_type") and c["as_type"] != k["knowledge_type"]: out["errors"].append("引用の性質(%s)が登録内容(%s)と異なる。著者の見解・学説・裁判所の判断・実務上の留意点を混同しない" % (c["as_type"], k["knowledge_type"]))
    if k["knowledge_type"] in ("author_view", "scholarly_dispute"): out["warnings"].append("著者の見解/学説。確立した判例法理・法令上の義務として引用できない")
    if k["knowledge_type"] == "court_holding_as_described": out["warnings"].append("文献が紹介する裁判所の判断。判決全文で確認するまで確定的に引用できない")
    if k["ocr_status"] not in ("checked", "correction_confirmed"): out["warnings"].append("OCR確認状態が未確認/訂正未確定")
    if k["structure_status"] != "human_checked": out["warnings"].append("構造化結果は人の確認前(AI生成)")
    pid = c.get("passage_id") or ((k.get("source_refs") or [{}])[0].get("passage_id") if c.get("quote") else None)
    _quote_check("source", sid, pid, c.get("quote"), c.get("page"), out)
    if c.get("quote") and out["quote_match"] is None: out["errors"].append("引用文言の照合ができない")
    mech = not out["errors"] and (not c.get("quote") or out["quote_match"] is True); out["mechanical_match"] = mech
    out["firm_citation"] = bool(mech and c.get("quote") and s["bibliographic_status"] == "confirmed" and k["ocr_status"] in ("checked", "correction_confirmed") and k["structure_status"] == "human_checked" and k["knowledge_type"] in ("legal_principle", "practice_note"))
    out["status"] = "ok" if mech else "failed"; return out
def verify_store():
    """保存データの整合性(原本ハッシュ・manifest・段落ハッシュ・未解決参照・履歴の連鎖)。インデックスは対象外(派生物)"""
    E, W = [], []
    for sid in list_ids("knowledge/sources"):
        s = load_json(P("knowledge", "sources", sid + ".json"))
        if s.get("original_path"):
            p = P(*s["original_path"].split("/"))
            if not os.path.isfile(p): E.append("%s: 原資料ファイルなし" % sid)
            elif sha256_file(p) != s.get("sha256"): E.append("%s: 原資料ハッシュ不一致" % sid)
    for cid in list_ids("cases/metadata"):
        m = load_json(P("cases", "metadata", cid + ".json"))
        if m.get("fulltext_ref"):
            p = P(*m["fulltext_ref"]["path"].split("/"))
            if not os.path.isfile(p) or sha256_file(p) != m["fulltext_ref"]["sha256"]: E.append("%s: 判決原本の欠落又はハッシュ不一致" % cid)
        mf = P("cases", "manifests", cid + ".json")
        if os.path.isfile(mf):
            for rel, h in load_json(mf)["files"].items():
                p = P(*rel.split("/"))
                if os.path.isfile(p) and rel.endswith(".json") is False and sha256_file(p) != h: E.append("%s: manifest不一致 %s" % (cid, rel))
    for d in ("knowledge/passages", "cases/passages"):
        dd = P(*d.split("/"))
        for f in (os.listdir(dd) if os.path.isdir(dd) else []):
            if f.endswith(".jsonl"):
                for l in open(os.path.join(dd, f), encoding="utf-8"):
                    if l.strip():
                        r = json.loads(l)
                        if sha256_text(r["text"]) != r.get("text_sha256"): E.append("%s: 段落ハッシュ不一致" % r["passage_id"])
    for kid in list_ids("knowledge/structured"):
        k = load_json(P("knowledge", "structured", kid + ".json"))
        for ref in k.get("related_cases", []) + k.get("related_knowledge", []):
            if isinstance(ref, dict) and not ref.get("resolved"): W.append("%s: 未解決の参照 %s(後日の登録で解決可能)" % (kid, ref["ref"]))
            elif isinstance(ref, str) and not (os.path.isfile(P("cases", "metadata", ref + ".json")) or os.path.isfile(P("knowledge", "structured", ref + ".json"))): W.append("%s: 参照先%sが未登録" % (kid, ref))
    ok, n = ledger_ok()
    if not ok: E.append("登録履歴(ledger)のハッシュ連鎖が壊れている(改ざんの疑い)")
    return {"errors": E, "warnings": W, "ledger_entries": n, "status": "ok" if not E else "failed"}
def resolve_pending():
    """未解決参照(後日登録された資料)を解決候補として列挙する"""
    out = []
    for kid in list_ids("knowledge/structured"):
        k = load_json(P("knowledge", "structured", kid + ".json"))
        for ref in k.get("related_cases", []) + k.get("related_knowledge", []):
            if isinstance(ref, dict) and not ref.get("resolved"):
                for cid in list_ids("cases/metadata"):
                    m = load_json(P("cases", "metadata", cid + ".json"))
                    if re.sub(r"\s", "", ref["ref"]) in re.sub(r"\s", "", m["case_number"]): out.append({"knowledge_id": kid, "ref": ref["ref"], "candidate_case_id": cid})
    return out
if __name__ == "__main__":
    fn = sys.argv[1]
    if fn == "store": print(json.dumps(verify_store(), ensure_ascii=False, indent=1))
    else: print(json.dumps({"case": verify_case_citation, "knowledge": verify_knowledge_citation}[fn](json.loads(sys.argv[2])), ensure_ascii=False, indent=1))
