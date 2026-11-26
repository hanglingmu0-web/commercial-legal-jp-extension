#!/usr/bin/env python3
"""実務プロファイル/プレイブックの存在・プレースホルダ残存・複数候補の競合を検査する。
読込失敗時に一般基準へ黙って切り替えないための番兵。異常があれば終了コード1。
使い方: check_config.py <config.md> [<config2.md> ...]  (先頭が最優先)
"""
import sys, re, os, hashlib
PH = re.compile(r"\[(PLACEHOLDER|Your Company Name|N|GC name|CLM system)[^\]]*\]")
def check(paths):
    errs, found = [], []
    for p in paths:
        if os.path.isfile(p) and os.path.getsize(p) > 0: found.append(p)
    if not found: return ["設定ファイルが1つも存在しない/空: " + ", ".join(paths) + " → 設定未読込。一般基準でレビューせず、利用者に通知すること"]
    txt = open(found[0], encoding="utf-8").read()
    ph = PH.findall(txt)
    if ph: errs.append("プレースホルダ残存(%d箇所): %s" % (len(ph), found[0]))
    if len(found) > 1:
        hs = {hashlib.sha256(open(f, "rb").read()).hexdigest() for f in found}
        if len(hs) > 1: errs.append("内容の異なる設定ファイルが複数存在(優先: %s): %s" % (found[0], ", ".join(found[1:])))
    return errs
if __name__ == "__main__":
    errs = check(sys.argv[1:])
    for e in errs: print("NG:", e)
    print("RESULT:", "FAIL" if errs else "PASS"); sys.exit(1 if errs else 0)
