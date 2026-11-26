#!/usr/bin/env python3
"""Commercial Legal / jp-contract-verification からの法律知識基盤の利用口。
  lk_review_bridge.py issues contract.txt                 # 契約書から法律上の論点(条項単位)を抽出
  lk_review_bridge.py search contract.txt [--out FILE]    # 抽出した論点ごとに法令・法知識・判例を横断検索(登録が無くても動作)
  lk_review_bridge.py gate review.json                    # review.json の authorities(引用した法知識・判例)を検証し、確定的引用・混同・『該当なし=不存在』を検出
検索の一致・類似度は根拠ではない。検索結果なしは存在しないことの証明ではない。法知識・判例が未登録でも既存の契約レビューは動く(status=no_data)。"""
import sys, os, re, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lk_search as S, lk_verify as V
NOHIT_ASSERT = re.compile(r"(関連(する)?(判例|裁判例|文献)(は|が)(存在しない|ない|見当たらない)|先例(は|が)(存在しない|ない)|判例(は|が)(存在しない|ない)|学説上(の)?争い(は|が)ない)")
SCOPE_OK = re.compile(r"(未登録|登録されていない|検索範囲|確認できていない|未確認|検索の限り)")
def search(ct):
    issues = S.extract_issues(ct); out = []
    for it in issues:
        q = re.sub(r"[・]", " ", it["topic"]).split()[0]
        a = S.search_legal_authorities(q, limit=3); out.append({"clause": it["clause"], "topic": it["topic"], "query": q, "knowledge": {k: a["knowledge"].get(k) for k in ("status", "count", "items")}, "cases": {k: a["cases"].get(k) for k in ("status", "count", "items")}, "statutes": a["statutes"][:2]})
    st = {r["knowledge"]["status"] for r in out} | {r["cases"]["status"] for r in out}
    return {"issues": issues, "results": out, "status": "no_data" if st <= {"no_data"} else "ok", "caveats": [S.NO_APPLY, S.NO_PROOF, "取得結果は初回レビューの参考資料。独立再検証担当は初回の選択に依らず独自に検索すること。"]}
def gate(rv):
    E, I = [], []
    for a in rv.get("authorities", []):
        kind = a.get("kind"); ref = a.get("ref") or {}; used = a.get("used_for", "reference")
        v = V.verify_case_citation(ref) if kind == "case" else V.verify_knowledge_citation(ref)
        if v["errors"]: E.append("%s: 引用の機械検証に失敗: %s" % (a.get("judgment_id"), "; ".join(v["errors"])))
        if used == "firm" and not v["firm_citation"]: E.append("%s: 確定的な根拠として引用しているが、未確認の資料(警告: %s)は確定的に引用できない" % (a.get("judgment_id"), "; ".join(v["warnings"]) or "検証条件未達"))
        ra = a.get("relevance_assessment") or {}
        if kind == "case" and not (ra.get("common_points") and ra.get("differences") and ra.get("scope") and ra.get("timing")): E.append("%s: 判例を引用しているが、審査中の契約との共通点・相違点・援用できる範囲・適用時期の評価がない(類似語の一致のみで直接適用しない)" % a.get("judgment_id"))
        if a.get("beyond_scope") and not a.get("analogy_declared"): E.append("%s: 判例の射程を超える適用なのに推論・類推である旨が明示されていない" % a.get("judgment_id"))
        I.append("%s: 機械的一致は法律上の関連性を保証しない" % a.get("judgment_id")) if v["mechanical_match"] else None
    def walk(o, p=""):
        if isinstance(o, dict):
            for k, x in o.items(): yield from walk(x, p + "/" + k)
        elif isinstance(o, list):
            for n, x in enumerate(o): yield from walk(x, "%s[%d]" % (p, n))
        elif isinstance(o, str): yield p, o
    for p, s in walk({k: v for k, v in rv.items() if k != "authorities"}):
        for sen in re.split(r"(?<=[。\n])", s):
            if NOHIT_ASSERT.search(sen) and not SCOPE_OK.search(sen): E.append("%s: 検索結果なしを関連判例・文献の不存在の根拠にしている(『%s』)" % (p, sen.strip()[:60]))
    return {"errors": E, "info": I, "status": "FAIL" if E else "PASS"}
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["issues", "search", "gate"]); ap.add_argument("path"); ap.add_argument("--out"); a = ap.parse_args()
    if a.cmd == "gate": r = gate(json.load(open(a.path, encoding="utf-8")))
    else:
        ct = open(a.path, encoding="utf-8").read(); r = {"issues": S.extract_issues(ct)} if a.cmd == "issues" else search(ct)
    t = json.dumps(r, ensure_ascii=False, indent=1)
    if a.out: open(a.out, "w", encoding="utf-8").write(t)
    print(t if not a.out else "written " + a.out); sys.exit(1 if r.get("status") == "FAIL" else 0)
