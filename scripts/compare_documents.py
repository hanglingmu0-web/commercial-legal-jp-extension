#!/usr/bin/env python3
"""原本と編集後DOCXの差分検証。
 (1) 今回追加した変更履歴・コメントを全て「却下」した状態が原本と同等か(段落属性・run書式・本文)
 (2) document.xml以外のパート(styles/numbering/settings/header/footer等)が不変か
 (3) --revisions 指定時: 全て「承認」した状態が期待文面と一致するか
使い方: compare_documents.py 原本.docx 編集後.docx [--revisions revs.json]
"""
import sys, json, argparse, copy
from lxml import etree
import os, sys as _s; _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx_common import *

ALLOWED_CHANGED = {"word/document.xml", "word/comments.xml", "word/_rels/document.xml.rels", "[Content_Types].xml"}

def c14n(el):
    return etree.tostring(el, method="c14n") if el is not None else b""

def ids_of(root, tags):
    return {e.get(q("id")) for e in root.iter(*[q(t) for t in tags])}

def reject_new(root, orig_rev_ids, orig_cmt_ids):
    """原本に無かった変更履歴・コメント標識を除去/巻き戻す。"""
    root = copy.deepcopy(root)
    for e in list(root.iter(q("ins"))):
        if e.get(q("id")) not in orig_rev_ids: e.getparent().remove(e)
    for e in list(root.iter(q("del"))):
        if e.get(q("id")) not in orig_rev_ids:
            par = e.getparent(); idx = par.index(e)
            for ch in list(e):
                for t in ch.iter(q("delText")): t.tag = q("t")
                par.insert(idx, ch); idx += 1
            par.remove(e)
    for e in list(root.iter(q("commentRangeStart"), q("commentRangeEnd"))):
        if e.get(q("id")) not in orig_cmt_ids: e.getparent().remove(e)
    for e in list(root.iter(q("commentReference"))):
        if e.get(q("id")) not in orig_cmt_ids:
            r = e.getparent(); r.getparent().remove(r)
    return root

def accept_all(root):
    root = copy.deepcopy(root)
    for e in list(root.iter(q("del"))): e.getparent().remove(e)
    for e in list(root.iter(q("ins"))):
        par = e.getparent(); idx = par.index(e)
        for ch in list(e): par.insert(idx, ch); idx += 1
        par.remove(e)
    return root

def canon_paragraphs(root):
    out = []
    for p in root.iter(q("p")):
        ppr = c14n(p.find(q("pPr")))
        # pPr内のrPr(段落記号の書式)は変更履歴情報(w:ins/w:del)を含み得るため除外せず保持
        toks = []
        for r in p.iter(q("r")):
            rpr = c14n(r.find(q("rPr")))
            for ch in r:
                if ch.tag == q("rPr"): continue
                if ch.tag in (q("t"), q("delText")): key = ("T", ch.text or "")
                elif ch.tag == q("tab"): key = ("T", "\t")
                else: key = ("X", c14n(ch))
                if toks and key[0] == "T" and toks[-1][0] == rpr and toks[-1][1][0] == "T":
                    toks[-1] = (rpr, ("T", toks[-1][1][1] + key[1]))
                else: toks.append((rpr, key))
        out.append((ppr, toks))
    return out

def text_of(root):
    return ["".join(t.text or "" for t in p.iter(q("t"))) for p in root.iter(q("p"))]

def compare(orig_path, new_path, revisions=None):
    errs = []
    po, _ = read_parts(orig_path); pn, _ = read_parts(new_path)
    for n in sorted(set(po) | set(pn)):
        if n in ALLOWED_CHANGED: continue
        if po.get(n) != pn.get(n):
            # XMLは正規化して再比較
            try:
                if c14n(etree.fromstring(po[n])) == c14n(etree.fromstring(pn[n])): continue
            except Exception: pass
            errs.append("document.xml以外のパートが変更/欠落: " + n)
    ro, rn = etree.fromstring(po["word/document.xml"]), etree.fromstring(pn["word/document.xml"])
    orig_rev = ids_of(ro, ["ins", "del"])
    orig_cm = ids_of(ro, ["commentRangeStart"])
    # 既存コメント本体が残っているか
    if "word/comments.xml" in po:
        co = {c.get(q("id")): c14n(c) for c in etree.fromstring(po["word/comments.xml"])}
        cn = {c.get(q("id")): c14n(c) for c in etree.fromstring(pn.get("word/comments.xml", b"<x/>"))} if "word/comments.xml" in pn else {}
        for k, v in co.items():
            if k not in cn: errs.append("既存コメント消失: id=%s" % k)
            elif cn[k] != v: errs.append("既存コメント内容変更: id=%s" % k)
    for i in orig_rev:
        if i not in ids_of(rn, ["ins", "del"]): errs.append("既存の変更履歴が消失: id=%s" % i)
    rej = reject_new(rn, orig_rev, orig_cm)
    A, B = canon_paragraphs(ro), canon_paragraphs(rej)
    if len(A) != len(B): errs.append("段落数が不一致(却下状態): 原本%d / 編集後%d" % (len(A), len(B)))
    for i, (a, b) in enumerate(zip(A, B)):
        if a[0] != b[0]: errs.append("段落%d: 段落属性(インデント/番号等)が変化" % i)
        if a[1] != b[1]: errs.append("段落%d: 本文またはrun書式が、今回の変更履歴を除いても原本と相違" % i)
    # 表・セクション等の構造
    for tag in ("tbl", "tr", "tc", "sectPr", "drawing", "footnoteReference", "fldChar", "fldSimple"):
        if len(list(ro.iter(q(tag)))) != len(list(rn.iter(q(tag)))): errs.append("構造要素の数が変化: w:" + tag)
    if revisions is not None:
        exp = text_of(ro)
        for rev in revisions:
            hit = [i for i, t in enumerate(exp) if rev["original_text"] in t]
            if len(hit) == 1: exp[hit[0]] = exp[hit[0]].replace(rev["original_text"], rev["revised_text"], 1)
            else: errs.append("%s: 期待文面の算出不可(該当%d)" % (rev["revision_id"], len(hit)))
        got = text_of(accept_all(rn))
        if exp != got:
            for i, (e, g) in enumerate(zip(exp, got)):
                if e != g: errs.append("段落%d: 承認後の文面が期待と不一致 期待=%r 実際=%r" % (i, e, g))
            if len(exp) != len(got): errs.append("承認後の段落数が期待と不一致")
    return errs

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("orig"); ap.add_argument("new"); ap.add_argument("--revisions")
    a = ap.parse_args()
    revs = json.load(open(a.revisions, encoding="utf-8")) if a.revisions else None
    errs = compare(a.orig, a.new, revs)
    for e in errs: print("NG:", e)
    print("RESULT:", "FAIL" if errs else "PASS"); sys.exit(1 if errs else 0)
