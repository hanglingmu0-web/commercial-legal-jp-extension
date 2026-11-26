#!/usr/bin/env python3
"""法務担当者向けのレビュー結果(判断できる形式)を1枚のMarkdownにまとめる。  make_review_report.py <案件dir> --contract-name 名称 [--out report.md]
入力: first/review.json, revision_states.json, disagreements.json, integrated_gate_v4.json, adversarial/adversarial.json(あれば)。AIの結論を新たに作らず、既存の出力を整理するのみ。"""
import sys, os, json, argparse
ap = argparse.ArgumentParser(); ap.add_argument("dir"); ap.add_argument("--contract-name", default=""); ap.add_argument("--out"); a = ap.parse_args(); L = lambda n: json.load(open(os.path.join(a.dir, n), encoding="utf-8")) if os.path.isfile(os.path.join(a.dir, n)) else None
fr, st, dis, ig, adv = L("first/review.json"), L("revision_states.json"), L("disagreements.json"), L("integrated_gate_v4.json"), L("adversarial/adversarial.json")
o = ["社内検討用・秘密 — AI支援による契約レビュー(法務担当者の判断に資する資料。最終判断・署名・送信は人間が行う)", "", "# 契約レビュー結果: %s" % a.contract_name, "",
     "**処理状態: %s**(判断事項が残ることはシステムの異常ではありません。客観的な誤りがある場合は『重大な不一致あり』になります)" % (ig or {}).get("status", "未算出"), "",
     "## 1. 条項別の判断(初回レビュー)", "| 条項 | 分類 | 指摘の種別 | 結論区分 | 要旨 |", "|---|---|---|---|---|"]
for j in fr["judgments"]: o.append("| %s | %s | %s | %s | %s |" % (j.get("clause"), j.get("category"), j.get("finding_type", "-"), j.get("conclusion_status"), (j.get("summary") or "").replace("\n", " ").replace("|", "/")[:140]))
o += ["", "## 2. Wordへの反映区分(修正案ごと)", "| 修正案 | 条項 | 区分 | 状態 | 理由 |", "|---|---|---|---|---|"]
for s in st:
    if s.get("revision_id"): o.append("| %s | %s | %s | %s | %s |" % (s["revision_id"], s["clause"], s["word_class"], s["state"], s["reason"][:90]))
o += ["", "- 検証済みの修正=変更履歴+コメント(承認は人間) / 交渉上の提案=必須修正ではない選択肢 / 確認事項=コメントのみ / 反映禁止=反映しない", "", "## 3. 判断事項(法務担当者の判断が必要。AI同士の相違を単一の結論に統合していません)"]
for i in (dis or {}).get("items", []):
    if i["result"].startswith("判断事項"):
        o.append("### [%s型] %s / %s: %s" % (i["kind"], i["clause"], i["field"], i["cause_hint"]))
        for p in i.get("positions") or []: o.append("- **%s**(結論区分=%s 分類=%s): %s" % (p["source"], p["結論区分"], p["分類"], (p.get("要旨") or "")[:160]))
for x in (adv or {}).get("findings", []): o.append("- 反証レビュー %s(%s): %s 採否は未決(法務担当者が判断)" % (x.get("id"), x.get("severity"), (x.get("summary") or x.get("issue") or "")[:140]))
o += ["", "## 4. 検証できていない事項"]; o += ["- " + x for x in (ig or {}).get("unverifiable", [])]
o += ["- 法令の条文は公式原文との照合未実施(AI転記)。取適法等の適用は、資本金・従業員数が不明のため断定していない。", "- 当社の審査基準・承認マトリクスは未提供のため適用していない。", "- Word実機(Microsoft Word)での確認は未実施。"]
t = "\n".join(o) + "\n"; print(t) if not a.out else open(a.out, "w", encoding="utf-8").write(t)
