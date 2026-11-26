#!/usr/bin/env python3
"""独立再検証用の『盲検パケット』を作る。初回レビューの結論・判断・修正案は一切含めない(契約書原文・事実関係・資料の所在のみ)。
  blind_packet.py <case_dir> > packet.md
"""
import sys, os, json
d = sys.argv[1]
print("# 独立再検証パケット(初回レビューの結論は含まれていない)\n")
print("## 契約書原文\n" + open(os.path.join(d, "contract.txt"), encoding="utf-8").read())
print("\n## 事実関係(null/欠落は不明。推測で補完しないこと)\n```json\n" + open(os.path.join(d, "facts.json"), encoding="utf-8").read() + "\n```")
print("\n## 利用可能な一次資料: legal_cache/*.json (verbatim/transcribed/retrieval_route/cross_checked_by/transitional_provisions_retrieved を必ず確認)")
