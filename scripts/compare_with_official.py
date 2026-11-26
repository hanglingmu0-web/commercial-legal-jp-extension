#!/usr/bin/env python3
"""AI転記キャッシュ(transcribed_backup)と、機械取得した公式原文(取り込み済みキャッシュ)の条文を突き合わせ、差異と影響を出力する。
  compare_with_official.py <転記JSON> <公式取得JSON> [--out diff.json]
差異の種別: 一致 / 文言差(正規化後も不一致) / 転記にのみ存在 / 公式にのみ存在(転記に無い条) 。
影響: 転記にのみ存在する条文、文言差のある条文を根拠にした引用照合・適用判定は無効として再確認が必要(キャッシュ参照: spec/legal_cache の claims)。"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import legal_sources as L
ap = argparse.ArgumentParser(); ap.add_argument("transcript"); ap.add_argument("official"); ap.add_argument("--out"); a = ap.parse_args()
T = json.load(open(a.transcript, encoding="utf-8")); O = json.load(open(a.official, encoding="utf-8")); tp, op = T.get("provisions", {}), O.get("provisions", {}); rows = []
for k in sorted(set(tp) | set(op)):
    if k in tp and k in op: rows.append((k, "一致" if L.norm(tp[k]) == L.norm(op[k]) else "文言差", tp[k], op[k]))
    elif k in tp: rows.append((k, "転記にのみ存在", tp[k], None))
    else: rows.append((k, "公式にのみ存在(転記に無い条)", None, op[k]))
diff = [r for r in rows if r[1] != "一致" and not r[1].startswith("公式にのみ")]; only_o = [r for r in rows if r[1].startswith("公式にのみ")]
meta = {x: (T.get(x), O.get(x)) for x in ("law_title", "law_num", "enforcement_date", "revision_id", "current_revision_status")}
meta_diff = {k: v for k, v in meta.items() if v[0] != v[1]}
out = {"transcript": a.transcript, "official": a.official, "counts": {"一致": sum(r[1] == "一致" for r in rows), "文言差": sum(r[1] == "文言差" for r in rows), "転記にのみ存在": sum(r[1] == "転記にのみ存在" for r in rows), "公式にのみ存在": len(only_o)},
       "meta_diff(転記,公式)": meta_diff, "diffs": [{"ref": r[0], "kind": r[1], "transcript": r[2], "official": r[3]} for r in diff],
       "impact": "差異のある条文(文言差/転記にのみ存在)を根拠にした引用照合・適用要件判定は無効。公式原文に合わせて再実行すること。" if diff or meta_diff else "転記済みの条文は公式原文と一致(正規化後)。ただし公式にのみ存在する条(%d件)は未カバーで、必要な論点は追加確認が必要。" % len(only_o)}
print(json.dumps(out, ensure_ascii=False, indent=1)); 
if a.out: json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.exit(1 if (diff or meta_diff) else 0)
