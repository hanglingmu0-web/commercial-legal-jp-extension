#!/usr/bin/env python3
"""e-Gov法令API v2 の law_data 応答(JSON)をキャッシュ形式へ取り込む。
  ingest_egov.py raw.json <source_id> --route "取得経路" --retrieved-at ISO --alias 略称 --former 旧名称
raw.json は ブラウザのget_page_text等で取得した「応答そのまま」であること(転記・要約は verbatim=false)。
"""
import sys, json, argparse, os, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legal_sources as L
def texts(n):
    if isinstance(n, str): return n
    if n.get("tag") in ("Item", "Subitem1", "Paragraph") : pass
    return "".join(texts(c) for c in n.get("children", []))
def sent(node):   # ParagraphSentence/ItemSentence のみ
    return "".join(texts(c) for c in node.get("children", []) if c.get("tag") in ("ParagraphSentence", "ItemSentence"))
def walk_para(prov, ref, p):
    n = p["attr"].get("Num"); r = "%s-%s" % (ref, n)
    prov[r] = sent(p)
    for it in p["children"]:
        if it.get("tag") == "Item": prov["%s-%s" % (r, it["attr"]["Num"])] = sent(it)
def flatten(root):
    prov = {}
    def rec(node, ctx):
        if isinstance(node, str): return
        t = node.get("tag")
        if t == "EnactStatement": prov["enact"] = texts(node)
        elif t == "Article":
            for c in node["children"]:
                if c.get("tag") == "Paragraph": walk_para(prov, node["attr"]["Num"], c)
            return
        elif t in ("MainProvision", "SupplProvision"):
            ctxn = "MP" if t == "MainProvision" else "SP"
            for c in node["children"]:
                if c.get("tag") == "Paragraph": walk_para(prov, ctxn, c)
                elif c.get("tag") == "Article": rec(c, ctxn)
        for c in node.get("children", []): rec(c, ctx)
    rec(root, None); return prov
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("raw"); ap.add_argument("source_id"); ap.add_argument("--route", required=True)
    ap.add_argument("--retrieved-at", required=True); ap.add_argument("--alias", action="append", default=[]); ap.add_argument("--former", action="append", default=[]); ap.add_argument("--transcribed", action="store_true", help="応答をモデルが貼付転記した場合(機械取得ではない=一次資料として扱われない)"); ap.add_argument("--url", default=None); ap.add_argument("--test-fixture", action="store_true"); ap.add_argument("--cross-checked-by", action="append", default=[])
    a = ap.parse_args(); raw = open(a.raw, encoding="utf-8").read(); j = json.loads(raw)
    li, ri = j["law_info"], j["revision_info"]
    out = {"source_id": a.source_id, "kind": li["law_type"], "source_type": "一次", "verbatim": True, "law_id": li["law_id"], "law_num": li["law_num"],
           "law_title": ri["law_title"], "abbrev": [x for x in ri.get("abbrev", "").split(",") if x] + a.alias, "former_titles": a.former,
           "revision_id": ri["law_revision_id"], "enforcement_date": ri["amendment_enforcement_date"], "current_revision_status": ri["current_revision_status"],
           "repeal_status": ri["repeal_status"], "repeal_date": ri["repeal_date"], "api_updated": ri["updated"], "retrieved_at": a.retrieved_at,
           "retrieval_route": a.route, "transcribed_by_model": a.transcribed, "acquisition": ("model_transcription" if a.transcribed else "machine_fetch"), "raw_path": os.path.relpath(os.path.abspath(a.raw), os.path.dirname(L.CACHE_DIR)), "promulgation_date": li.get("promulgation_date"), "scheduled_enforcement_date": ri.get("amendment_scheduled_enforcement_date"), "amendment_history_retrieved": False, "last_verified_at": a.retrieved_at, "test_fixture": a.test_fixture, "cross_checked_by": a.cross_checked_by, "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "transitional_provisions_retrieved": False,
           "provisions": flatten(j["law_full_text"])}
    json.dump(out, open(os.path.join(L.CACHE_DIR, a.source_id + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mp = os.path.join(L.CACHE_DIR, "raw", "manifest.json"); man = json.load(open(mp, encoding="utf-8")) if os.path.isfile(mp) else {}
    man[a.source_id] = {"url": a.url, "retrieved_at": a.retrieved_at, "format": "application/json (e-Gov law_data v2)", "bytes": len(raw.encode("utf-8")), "sha256": out["raw_sha256"], "acquisition": out["acquisition"], "route": a.route}
    os.makedirs(os.path.dirname(mp), exist_ok=True); json.dump(man, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("OK", a.source_id, len(out["provisions"]), "provisions", out["acquisition"])
