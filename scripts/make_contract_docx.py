#!/usr/bin/env python3
"""試験用: テキスト契約書から段落ごとのdocxを生成する(実契約書のWord原本の代替。実Word原本での試験とは別)。"""
import sys, docx
d = docx.Document()
for line in open(sys.argv[1], encoding="utf-8").read().splitlines():
    if line.strip(): d.add_paragraph(line)
d.save(sys.argv[2])
