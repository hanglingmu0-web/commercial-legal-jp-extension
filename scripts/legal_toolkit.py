#!/usr/bin/env python3
"""汎用 法令ツールキット(個別法の専用プログラムを前提としない共通機構)。取適法専用の applicability.py とは分離。
サブコマンド(出力はJSON):
  fetch-plan <法令名>            取得手順(e-Gov API v2のURL。実取得は fetch_egov.py をPCで実行)
  sources                        キャッシュ済み資料の一覧(取得区分・信頼区分・現行性軸)
  currency <source_id> --ref D [--event D] [--tier T]      多軸の現行性評価
  extract <source_id> <ref>      条文取得(refは provisions キー。例 6-1 / 2-8-1)
  suppl <source_id>              附則・経過措置の取得状況と影響の記述
  related <text>                 条文中の他法令・政省令・規則への参照を機械抽出(取得対象の候補)
  verify-quote <source_id> <ref> <quote>                   引用照合(取得原文基準)
  structure <source_id> <ref>    条文を要件候補に構造化(各号・列挙の抽出。要件の充足判定はAI/人間)
  hold add|list <register.json> ...                        保留事項台帳
  applicability-check <spec.json> <facts.json>             仕様駆動の適用要件評価(汎用エンジン)
一次資料の扱い: 『確定』の根拠にできるのは機械取得・追跡検証済の原文のみ。AI転記・要約・解説は補助。
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legal_sources as L
REF_PAT = re.compile(r"([^、。()（）\s]{2,40}?(?:法律|法|令|規則|条例|指針|ガイドライン))(?:（([^）]{3,40}号)）|\(([^)]{3,40}号)\))?")
def related(text):
    out = []
    for m in re.finditer(r"([^、。（）()\s]{2,45}?(?:法律|法(?!律)|令|規則))(?:（([^）]{3,30}号)）)?", text):
        nm = m.group(1)
        if re.search(r"(この|当該|前|次|同|その|本)(法律|法|令|規則)$", nm) or len(nm) < 3 or re.match(r"(昭和|平成|令和)", nm): continue
        out.append({"name": nm, "number": m.group(2)})
    seen = set(); res = []
    for o in out:
        k = (o["name"], o["number"])
        if k not in seen: seen.add(k); res.append(o)
    return res
def structure(src, ref):
    prov = src["provisions"]; base = prov.get(ref)
    if base is None: return None
    kids = {k: v for k, v in prov.items() if k.startswith(ref + "-") and k.count("-") == ref.count("-") + 1}
    return {"ref": ref, "lead": base, "enumerated": [{"ref": k, "text": v} for k, v in sorted(kids.items())], "note": "各号の構造のみ。充足判定・解釈は機械では行わない。"}
def suppl(src):
    sp = {k: v for k, v in src["provisions"].items() if k.startswith("SP")}
    return {"transitional_provisions_retrieved": bool(src.get("transitional_provisions_retrieved")), "suppl_in_cache": list(sp), "note": src.get("transitional_note") or ("附則の取得なし。契約日・取引日が施行日前後にまたがる場合は経過措置の確認が必要" if not src.get("transitional_provisions_retrieved") else "取得済"),
            "impact": "未取得の場合: 施行日前の取引・契約には旧規定が適用される可能性があり、本ツールは適用関係を判断しない(AIが補完しない)" if not src.get("transitional_provisions_retrieved") else None}
# ---- 仕様駆動の汎用適用要件エンジン(Kleene三値論理)
def ev_node(n, facts):
    """node: {"all":[..]} | {"any":[..]} | {"not":node} | {"fact":path,"op":"eq|gt|gte|lt|lte|in","value":v,"name":str}。戻り値 True/False/None(不明)"""
    if "all" in n:
        rs = [ev_node(c, facts)[0] for c in n["all"]]; v = False if any(r is False for r in rs) else (None if any(r is None for r in rs) else True); return v, n
    if "any" in n:
        rs = [ev_node(c, facts)[0] for c in n["any"]]; v = True if any(r is True for r in rs) else (None if any(r is None for r in rs) else False); return v, n
    if "not" in n:
        r = ev_node(n["not"], facts)[0]; return (None if r is None else (not r)), n
    cur = facts
    for p in n["fact"].split("."):
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None: return None, n
    op, val = n["op"], n["value"]
    f = {"eq": lambda: cur == val, "gt": lambda: cur > val, "gte": lambda: cur >= val, "lt": lambda: cur < val, "lte": lambda: cur <= val, "in": lambda: cur in val}.get(op)
    if f is None: return None, n
    try: r = f()
    except TypeError: return None, n
    return r, n
def trace_node(n, facts, depth=0):
    v, _ = ev_node(n, facts); label = n.get("name") or ("all" if "all" in n else "any" if "any" in n else "not" if "not" in n else n.get("fact"))
    out = [{"depth": depth, "name": label, "status": {True: "充足", False: "不充足", None: "事実関係不明"}[v]}]
    for k in ("all", "any"):
        for c in n.get(k, []): out += trace_node(c, facts, depth + 1)
    if "not" in n: out += trace_node(n["not"], facts, depth + 1)
    return out
def applicability(spec, facts):
    eff = spec.get("effective_from"); rd = facts.get("reference_date")
    if eff:   # 施行日ゲート(仕様のeffective_from。基準日が施行前=未施行、基準日欠落=判断保留)
        if not rd: return {"law": spec.get("law"), "overall": "判断保留(基準日不明)", "asserted_applicable": False, "required_facts": ["基準日(reference_date)"], "trace": [], "note": "基準日が不明で施行前後を確定できない"}
        if rd < eff: return {"law": spec.get("law"), "overall": "未施行(基準日%s < 施行日%s)" % (rd, eff), "asserted_applicable": False, "required_facts": [], "trace": [], "note": "基準日時点で未施行"}
    v, _ = ev_node(spec["tree"], facts)
    missing = sorted({x["fact"] for x in flat(spec["tree"]) if ev_node(x, facts)[0] is None})
    return {"law": spec.get("law"), "overall": {True: "適用あり", False: "適用なし", None: "判断保留(事実関係不明)"}[v], "asserted_applicable": v is True, "required_facts": missing, "trace": trace_node(spec["tree"], facts),
            "note": "仕様(spec)の正確性は条文との照合を人間/検証者が行う。エンジンは仕様に忠実に評価するのみ。"}
def flat(n):
    if "fact" in n: return [n]
    out = []
    for k in ("all", "any"):
        for c in n.get(k, []): out += flat(c)
    if "not" in n: out += flat(n["not"])
    return out
def main():
    a = sys.argv[1:]
    if not a: print(__doc__); return
    c = a[0]
    if c == "fetch-plan":
        print(json.dumps({"law_title": a[1], "search_url": "https://laws.e-gov.go.jp/api/2/laws?law_title=" + a[1], "law_data_url": "https://laws.e-gov.go.jp/api/2/law_data/<law_id>?response_format=json", "next": "PCで scripts/fetch_egov.py を実行して原文をrawで保存", "note": "出典: e-Gov法令検索 法令API Version 2(公式)。シェルからの取得がプロキシで拒否される環境では取得不能として扱う"}, ensure_ascii=False, indent=1))
    elif c == "sources":
        for sid in L.all_sources():
            s = L.load(sid); print(json.dumps({"source_id": sid, "title": s.get("law_title"), "acquisition": L.acquisition(s), "reliability": L.reliability(s), "can_support_firm": L.can_support_firm(s), "retrieved_at": s.get("retrieved_at"), "enforcement_date": s.get("enforcement_date"), "transitional_provisions_retrieved": bool(s.get("transitional_provisions_retrieved"))}, ensure_ascii=False))
    elif c == "currency":
        s = L.load(a[1]); kv = dict(zip(a[2::2], a[3::2])); print(json.dumps(L.currency(s, kv["--ref"], kv.get("--event"), kv.get("--today"), kv.get("--tier", "standard")), ensure_ascii=False, indent=1))
    elif c == "extract":
        s = L.load(a[1]); print(json.dumps({"ref": a[2], "text": s["provisions"].get(a[2]), "reliability": L.reliability(s)}, ensure_ascii=False))
    elif c == "suppl": print(json.dumps(suppl(L.load(a[1])), ensure_ascii=False, indent=1))
    elif c == "related": print(json.dumps(related(a[1]), ensure_ascii=False, indent=1))
    elif c == "verify-quote": print(L.verify_quote(L.load(a[1]), a[2], a[3]))
    elif c == "structure": print(json.dumps(structure(L.load(a[1]), a[2]), ensure_ascii=False, indent=1))
    elif c == "hold":
        sub, reg = a[1], a[2]; data = json.load(open(reg, encoding="utf-8")) if os.path.isfile(reg) else []
        if sub == "add":
            kv = dict(zip(a[3::2], a[4::2])); data.append({"id": "H%d" % (len(data) + 1), "item": kv.get("--item"), "reason": kv.get("--reason"), "needed": kv.get("--needed"), "status": "open"}); json.dump(data, open(reg, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps(data, ensure_ascii=False, indent=1))
    elif c == "applicability-check": print(json.dumps(applicability(json.load(open(a[1], encoding="utf-8")), json.load(open(a[2], encoding="utf-8"))), ensure_ascii=False, indent=1))
    else: print(__doc__); sys.exit(2)
if __name__ == "__main__": main()
