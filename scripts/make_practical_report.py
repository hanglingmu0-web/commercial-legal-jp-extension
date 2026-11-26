#!/usr/bin/env python3
"""実務用レビュー報告書(法務担当者が日常の審査で読む版)。重大な問題→推奨修正→確認事項→残存リスクの順。
同じ論点は1回だけ(条項ごとに集約)提示し、分類差・不一致の詳細は技術検証記録(technical_record.md)に分離する。
  make_practical_report.py <案件dir> --contract-name 名称 [--out report_practical.md]
入力: first/review.json, revision_states.json, option_groups.json, disagreements.json, resolutions.json, integrated_gate*.json, docx_report.json, external_check.json。新たな結論は作らない。"""
import sys, os, re, json, argparse
ap = argparse.ArgumentParser(); ap.add_argument("dir"); ap.add_argument("--contract-name", default=""); ap.add_argument("--out"); a = ap.parse_args()
def J(n, d=None):
    p = os.path.join(a.dir, n); return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else d
fr = J("first/review.json"); st = J("revision_states.json", []); dis = J("disagreements.json", {"items": []}); res = J("resolutions.json", {}); ig = J("integrated_gate_v5.json") or J("integrated_gate_v4.json") or {}
dx = J("docx_report.json") or {}; wr = J("word_revisions.json", []); ex = J("external_check.json", {}); adv = J("adversarial/adversarial.json", {"findings": []})
def first_sentence(s, n=140):
    s = (s or "").replace("\n", " "); m = re.match(r"^(.+?。)", s); t = m.group(1) if m else s
    return t if len(t) <= n else t[: n - 1] + "…"   # 表示用の要約(コメント・修正文では使わない)
def nk(k):
    m = re.match(r"^(第[0-9０-９]+条)", k or ""); return m.group(1) if m else k
jl = {nk(j["clause"]): j for j in fr["judgments"] if j.get("clause")}
bycl = {}
for s_ in st:
    if s_.get("revision_id"): bycl.setdefault(s_["clause"], []).append(s_)
rev = {r["revision_id"]: r for r in fr.get("revisions", [])}
cnt = {}
for j in jl.values(): cnt[j.get("judgment_label")] = cnt.get(j.get("judgment_label"), 0) + 1
o = ["社内検討用・秘密 — AI支援による契約レビュー(最終判断・署名・送信は人間が行います)", "", "# 実務用レビュー報告書: %s" % a.contract_name, ""]
o += ["## 1. 総合評価", "- 条項判定: " + " / ".join("%s %d件" % (k, v) for k, v in cnt.items()),
      "- 処理状態: %s(判断事項が残ることは異常ではありません)" % (ig.get("status") or "-"),
      "- Word成果物(変更履歴+コメント): %s" % ("機械検証 合格" if dx.get("ok") else "未検証又は不合格"), "- Microsoft Word実機での確認: 未実施", ""]
heavy = [k for k, j in jl.items() if j.get("judgment_label") == "修正が必要"]
o += ["## 2. 重大な問題(優先して対応)"]
if not heavy: o.append("- 該当なし")
for k in heavy:
    j = jl[k]; o.append("- **%s**: %s" % (k, first_sentence(j.get("summary"))))
o += ["", "## 3. 推奨修正(Word反映の区分つき)", "| 条 | 区分 | 修正の要旨 | 検証状況(文言/法的効果/条項全体/論点全体) |", "|---|---|---|---|"]
for k, lst in bycl.items():
    for s_ in lst:
        if s_["word_class"] in ("反映禁止", "複数案の一部(別案を参照)"): continue
        r = rev.get(s_["revision_id"], {}); ly = s_.get("layers") or {}
        o.append("| %s | %s(%s) | %s | %s |" % (k, s_["word_class"], s_["revision_id"], first_sentence(r.get("reason"), 90), "/".join(ly.get(x, "-") for x in ("修正文言", "修正文案の法的効果", "条項全体", "関連条項を含む論点全体"))))
o += ["", "- 検証済みの修正=変更履歴+コメント(採否は人間) / 交渉上の提案=必須ではない提案 / 確認事項=コメントのみ。修正文の全文はWordファイルを参照。",
      "- 文言の検証が済んでも、数値の合理性・関連条項・論点全体が未確認なら『条項全体』『論点全体』は検証済みとしない。", ""]
o += ["## 4. 確認事項・判断が必要な事項(重複を除いて集約)"]; seen = set()
def add(t):
    key = re.sub(r"\W", "", t)[:40]
    if key not in seen: seen.add(key); o.append("- " + t)
for k, j in jl.items():
    if j.get("judgment_label") in ("事実関係の確認が必要", "法令資料の確認が必要", "交渉上の選択肢あり"): add("**%s**(%s): %s" % (k, j["judgment_label"], first_sentence(j.get("summary"))))
for s_ in st:
    if s_.get("word_class") == "確認事項" and s_.get("revision_id"): add("**%s**(%s): %s" % (s_["clause"], s_["revision_id"], first_sentence(rev.get(s_["revision_id"], {}).get("reason"), 110)))
for d in ig.get("decision_items", []): add(d)
for i in dis.get("items", []):
    if i["result"].startswith("判断事項"): add("**%s**: 解釈・取引判断が必要(%s)" % (i["clause"], i["cause_hint"]))
for gid, r_ in res.items():
    if isinstance(r_, dict) and r_.get("decision") == "要人間判断": add("%s: %s(選択肢: %s)" % (gid, first_sentence(r_.get("why_human"), 120), " / ".join(map(str, r_.get("options", [])))[:160]))
o += ["", "## 5. 残存リスク"]
for g in fr.get("issue_groups", []):
    if g.get("applicable") is False: continue
    if g.get("issue_status") != "検証済": o.append("- 論点『%s』(%s): 論点全体=%s。修正後の確認=%s" % (g.get("title") or g.get("topic_key"), "・".join(g.get("related_clauses", [])), g.get("issue_status"), (g.get("post_revision_check") or {}).get("status")))
for u in ig.get("unverifiable", []): o.append("- 未検証: " + u)
for n_ in fr.get("numeric_reviews", []):
    if n_.get("rationality_status") and n_["rationality_status"] != "確認済": o.append("- 数値『%s』の合理性: %s" % (n_.get("term_label"), n_["rationality_status"]))
o.append("- 法令の条文は公式原文との照合が未了の場合があります(取得状況は技術検証記録)。")
o += ["", "## 6. 全条項の判定(一覧)", "| 条 | 判定 | 要点 |", "|---|---|---|"]
for k, j in jl.items(): o.append("| %s | %s | %s |" % (k, j.get("judgment_label"), first_sentence(j.get("summary"), 80)))
o += ["", "## 7. 成果物の区分", "- 社内審査用Word: 詳細理由・代替案・根拠を含む。外部へ送らないこと。", "- 相手方提示用Word: 修正文案と必要最小限の理由・相手方への確認事項のみ。内部情報の混入検査: %s。外部送信は利用者の承認後に人間が行う。" % ("検出なし" if ex and not ex.get("leaks") else ("要確認 %s" % ex.get("leaks") if ex else "未実施")),
      "- 相手方提示用で理由未作成の修正: %s" % (ex.get("external_reason未作成") or "なし"), "", "詳細な検証経過・不一致・反証レビューは technical_record.md を参照。"]
t = "\n".join(o) + "\n"
if a.out: open(a.out, "w", encoding="utf-8").write(t)
else: print(t)
