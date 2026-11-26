#!/usr/bin/env python3
"""Word反映する修正の選別。検証を経た修正のみを approved に出し、それ以外は held に理由つきで退避する。
条件(全て): apply_to_word=true / (AIの自己申告 verification_status は信用しない。独立再検証が同条項で修正要と判断したことをもって『検証済(独立再検証一致)』とする) / 判断が判断保留でない / 独立再検証が同条項で修正要と判断(または human_approved=true) /
統合ゲートのerrorが当該条項・修正に言及していない(--gate-result) / 反証指摘が当該条項に未処理で残っていない。
  select_revisions.py --first f.json [--verifier v.json] --gate-result r.json --out-dir D
"""
import sys, os, json, argparse
ap = argparse.ArgumentParser(); ap.add_argument("--first", required=True); ap.add_argument("--verifier"); ap.add_argument("--gate-result", required=True); ap.add_argument("--out-dir", required=True); ap.add_argument("--resolutions"); a = ap.parse_args()
first = json.load(open(a.first, encoding="utf-8")); ver = json.load(open(a.verifier, encoding="utf-8")) if a.verifier and os.path.isfile(a.verifier) else None
gr = json.load(open(a.gate_result, encoding="utf-8")); jmap = {j["id"]: j for j in first["judgments"]}
vneeds = set()
if ver:
    vj = {j["id"]: (j.get("clause") or j["id"]) for j in ver["judgments"]}
    vneeds = {vj.get(r.get("judgment_id")) for r in ver.get("revisions", [])}
res = json.load(open(a.resolutions, encoding="utf-8")) if a.resolutions else {}
adv_hold = {rid: k for k, v in res.items() if v.get("decision") == "採用" for rid in v.get("hold_revisions", [])}
approved, held = [], []
for r in first.get("revisions", []):
    why = []; j = jmap.get(r.get("judgment_id"), {}); clause = j.get("clause") or r.get("judgment_id")
    if not r.get("apply_to_word"): why.append("apply_to_word=false")
    if j.get("conclusion_status") == "判断保留": why.append("判断保留")
    if not (clause in vneeds or r.get("human_approved")): why.append("独立再検証で同条項の修正要の判断が確認できない(人間承認もなし)")
    for e in gr.get("errors", []):
        if r.get("revision_id") in e or (r.get("judgment_id") and r["judgment_id"] in e) or (clause and clause in e): why.append("統合ゲートerror: " + e[:80]); break
    if r.get("revision_id") in adv_hold: why.append("反証指摘%s(採用)により保留" % adv_hold[r["revision_id"]])
    if gr.get("tier") in ("standard", "high") and not gr.get("verifier_present"): why.append("独立再検証なし")
    (held if why else approved).append(dict(r, _hold_reasons=why) if why else dict(r, verification_status="検証済(独立再検証一致・統合ゲート)" if clause in vneeds else "検証済(人間承認)"))
os.makedirs(a.out_dir, exist_ok=True)
keys = ("revision_id", "clause", "paragraph_id", "original_text", "revised_text", "reason", "comment", "risk_category", "evidence_ids", "verification_status")
json.dump([dict({k: r.get(k, "") for k in keys}, clause=(jmap.get(r.get("judgment_id"), {}).get("clause") or ""), comment=(r.get("comment") or ("【AI案・人間確認要】" + (r.get("reason") or "")))) for r in approved], open(os.path.join(a.out_dir, "approved_revisions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(held, open(os.path.join(a.out_dir, "held_revisions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("approved=%d held=%d" % (len(approved), len(held)))
for h in held: print(" HOLD", h.get("revision_id"), h["_hold_reasons"])
