#!/usr/bin/env python3
"""初回レビューと独立再検証の判断を条項単位で突き合わせ、不一致を明示する。不一致は『判断保留+一次資料再確認』扱い。
比較項目: 修正の要否 / 結論区分(確定・条件付き・判断保留) / 分類 / 法令適用の断定 / 数値の根拠区分。
注意: 一致は『独立した2回の判断が一致した』ことを示すに過ぎず、法的正確性の証明ではない(同一モデルの一致は特に)。
使い方: compare_judgments.py first.json verifier.json   不一致があれば終了コード1
"""
import sys, json
def summarize(rv):
    out = {}; revs = rv.get("revisions", [])
    for j in rv.get("judgments", []):
        key = j.get("clause") or j.get("id")
        out[key] = {"needs_revision": any(r.get("judgment_id") == j.get("id") for r in revs), "status": j.get("conclusion_status"), "category": j.get("category"),
                    "asserted_applicable": any(s.get("asserted_applicable") for s in j.get("statutes", [])),
                    "number_kinds": sorted({n.get("kind") for n in j.get("numbers", [])}), "revisions_applied_to_word": any(r.get("apply_to_word") for r in revs if r.get("judgment_id") == j.get("id"))}
    return out
def compare(a, b):
    A, B = summarize(a), summarize(b); diffs = []
    for k in sorted(set(A) | set(B)):
        if k not in A or k not in B: diffs.append((k, "条項の判断が片方のみ", A.get(k), B.get(k))); continue
        for f in A[k]:
            if A[k][f] != B[k][f]: diffs.append((k, f, A[k][f], B[k][f]))
    return A, B, diffs
if __name__ == "__main__":
    A, B, diffs = compare(json.load(open(sys.argv[1], encoding="utf-8")), json.load(open(sys.argv[2], encoding="utf-8")))
    for k in sorted(set(A) | set(B)): print(k, "初回:", A.get(k), "\n    再検証:", B.get(k))
    hard = [x for x in diffs if x[1] != "category"]; soft = [x for x in diffs if x[1] == "category"]
    for d in hard: print("[不一致/実質] 条項%s 項目%s 初回=%s 再検証=%s → 判断保留とし一次資料・契約原文から再確認" % d)
    for d in soft: print("[不一致/分類] 条項%s 初回=%s 再検証=%s → 分類基準(A-G)の適用が不統一。分類理由を確認" % (d[0], d[2], d[3]))
    print("RESULT:", ("DISAGREE(実質%d件・分類%d件)" % (len(hard), len(soft))) if diffs else "AGREE(独立判断の一致。正確性の証明ではない)"); sys.exit(1 if hard else (3 if soft else 0))
