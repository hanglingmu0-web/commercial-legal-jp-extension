#!/usr/bin/env python3
"""DOCXの構造検証。異常があれば終了コード1。
使い方: validate_docx.py file.docx [--expect-ins N] [--expect-del N] [--expect-comments N]
"""
import sys, os, zipfile, argparse, posixpath
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lxml import etree
import os, sys as _s; _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx_common import *

def validate(path, expect_ins=None, expect_del=None, expect_comments=None):
    errs = []; stats = {}
    try: z = zipfile.ZipFile(path)
    except Exception as e: return ["ZIP展開不可: %s" % e], stats
    if z.testzip(): errs.append("ZIP内部CRC異常")
    names = set(z.namelist()); trees = {}
    for n in names:
        if n.endswith(".xml") or n.endswith(".rels"):
            try: trees[n] = etree.fromstring(z.read(n))   # 未宣言の名前空間接頭辞もここで検出される
            except etree.XMLSyntaxError as e: errs.append("XML構文/名前空間エラー %s: %s" % (n, e))
    for need in ("[Content_Types].xml", "word/document.xml", "_rels/.rels"):
        if need not in names: errs.append("必須パート欠落: " + need)
    # 関係参照先の存在確認
    for n, t in trees.items():
        if n.endswith(".rels"):
            base = posixpath.dirname(posixpath.dirname(n))
            for r in t:
                if r.get("TargetMode") == "External": continue
                tgt = r.get("Target"); full = tgt.lstrip("/") if tgt.startswith("/") else posixpath.normpath(posixpath.join(base, tgt))
                if full not in names: errs.append("関係参照先なし %s -> %s" % (n, tgt))
    ct = trees.get("[Content_Types].xml")
    if ct is not None:
        ov = {o.get("PartName") for o in ct if o.tag.endswith("Override")}
        if "word/comments.xml" in names and "/word/comments.xml" not in ov: errs.append("comments.xmlのContent-Types宣言なし")
    doc = trees.get("word/document.xml")
    if doc is not None:
        ins = list(doc.iter(q("ins"))); dels = list(doc.iter(q("del")))
        ids = [e.get(q("id")) for e in ins + dels]
        if len(ids) != len(set(ids)): errs.append("変更履歴IDの重複")
        cs = {e.get(q("id")) for e in doc.iter(q("commentRangeStart"))}
        ce = {e.get(q("id")) for e in doc.iter(q("commentRangeEnd"))}
        cr = {e.get(q("id")) for e in doc.iter(q("commentReference"))}
        cx = trees.get("word/comments.xml")
        cids = {c.get(q("id")) for c in cx} if cx is not None else set()
        if cs != ce or cs != cr: errs.append("コメント範囲の開始/終了/参照が不一致")
        if cs - cids: errs.append("comments.xmlに存在しないコメント参照: %s" % sorted(cs - cids))
        if cids - cs: errs.append("本文に紐付かない孤立コメント: %s" % sorted(cids - cs))
        for d in dels:
            if any(t.tag == q("t") for t in d.iter()): errs.append("w:del内にw:t(delTextであるべき)")
        for i in ins:
            if any(t.tag == q("delText") for t in i.iter()): errs.append("w:ins内にw:delText")
        stats = {"ins": len(ins), "del": len(dels), "comments": len(cids)}
        for k, v, nm in (("ins", expect_ins, "挿入"), ("del", expect_del, "削除"), ("comments", expect_comments, "コメント")):
            if v is not None and stats[k] != v: errs.append("%s件数が期待値と不一致: 実際%d / 期待%d" % (nm, stats[k], v))
    return errs, stats

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("file")
    ap.add_argument("--expect-ins", type=int); ap.add_argument("--expect-del", type=int); ap.add_argument("--expect-comments", type=int)
    ap.add_argument("--comments-expected", help="word_revisions.json(予定したコメント全文との完全一致を検証)"); ap.add_argument("--audience", choices=["internal", "external"], default="internal")
    a = ap.parse_args(); errs, st = validate(a.file, a.expect_ins, a.expect_del, a.expect_comments)
    if a.comments_expected:
        import rules_v5 as R5, json
        e2, det = R5.verify_comments(a.file, json.load(open(a.comments_expected, encoding="utf-8"))); errs += e2; st["comment_full_match"] = "%d/%d" % (sum(d["match"] for d in det), len(det))
    if a.audience == "external":
        import rules_v5 as R5
        errs += R5.external_leaks(R5.docx_comments(a.file))
    for e in errs: print("NG:", e)
    print("stats:", st); print("RESULT:", "FAIL" if errs else "PASS"); sys.exit(1 if errs else 0)
