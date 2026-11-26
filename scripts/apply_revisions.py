#!/usr/bin/env python3
"""修正指示JSONに基づき、正式な変更履歴(w:ins/w:del)とWordコメントを決定論的に挿入する。
原本は上書きしない。1件でも対象を一意に特定できなければ、出力ファイルを作らず終了コード2で終了する。
使い方: apply_revisions.py 原本.docx revisions.json 出力.docx [--author 名前]
"""
import sys, json, copy, argparse, datetime
from lxml import etree
import os, sys as _s; _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx_common import *

CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
COMMENT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENT_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"

class RevisionError(Exception): pass

def split_run(run, offset):
    """w:r を offset 文字目で2分割し、後半 run を返す。単純な w:t のみの run を対象とする。"""
    ts = [c for c in run if c.tag == q("t")]
    others = [c for c in run if c.tag not in (q("t"), q("rPr"))]
    if others or len(ts) != 1:
        raise RevisionError("対象箇所に単純でないrun(tab/改行/画像等)が含まれるため自動編集不可")
    t = ts[0]; txt = t.text or ""
    if offset <= 0 or offset >= len(txt): return None
    new = copy.deepcopy(run)
    t.text = txt[:offset]; t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    nt = [c for c in new if c.tag == q("t")][0]
    nt.text = txt[offset:]; nt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    run.addnext(new)
    return new

def direct_runs(p):
    return [c for c in p if c.tag == q("r")]

def locate(p, start, end):
    """段落直下のrun列で [start,end) に対応するrun群を返す(必要なら分割)。"""
    pos = 0
    for r in direct_runs(p):
        ts = [c for c in r if c.tag == q("t")]
        if not ts: continue
        L = len(ts[0].text or "")
        if pos < start < pos + L:
            split_run(r, start - pos); return locate(p, start, end)
        if pos < end < pos + L:
            split_run(r, end - pos); return locate(p, start, end)
        pos += L
    sel, pos = [], 0
    for r in direct_runs(p):
        ts = [c for c in r if c.tag == q("t")]
        if not ts: continue
        L = len(ts[0].text or "")
        if pos >= start and pos + L <= end and L > 0: sel.append(r)
        pos += L
    return sel

def simple_text(p):
    return "".join((c.find(q("t")).text or "") for c in direct_runs(p) if c.find(q("t")) is not None)

class Ctx:
    def __init__(self, author):
        self.author = author; self.date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.next_id = 9000; self.comments = []; self.next_cid = 0
    def nid(self): self.next_id += 1; return str(self.next_id)

def apply_one(body, rev, ctx):
    orig, new = rev["original_text"], rev["revised_text"]
    if not orig: raise RevisionError("%s: original_text が空" % rev["revision_id"])
    cands = []
    for p in body.iter(q("p")):
        # 既存の変更履歴内にある段落は対象外
        if p.getparent().tag in (q("ins"), q("del")): continue
        if orig in simple_text(p) and orig in para_text(p):
            cands.append(p)
    if rev.get("paragraph_id"):
        cands = [p for p in cands if p.get("{http://schemas.microsoft.com/office/word/2010/wordml}paraId") == rev["paragraph_id"]]
    if len(cands) == 0: raise RevisionError("%s: 修正対象原文が見つからない" % rev["revision_id"])
    if len(cands) > 1 or simple_text(cands[0]).count(orig) != 1:
        raise RevisionError("%s: 修正対象箇所を一意に特定できない(該当%d段落)" % (rev["revision_id"], len(cands)))
    p = cands[0]; full = simple_text(p)
    if rev.get("comment_only"):   # 確認事項: 文言は変更せず、該当箇所にコメントのみを付す
        if not rev.get("comment"): raise RevisionError("%s: comment_only だがcommentが空" % rev["revision_id"])
        base0 = full.index(orig); runs0 = locate(p, base0, base0 + len(orig))
        if not runs0: raise RevisionError("%s: コメント対象runを特定できない" % rev["revision_id"])
        cid = str(ctx.next_cid); ctx.next_cid += 1; ctx.comments.append((cid, rev["comment"], rev["revision_id"]))
        runs0[0].addprevious(etree.Element(q("commentRangeStart"), {q("id"): cid}))
        end = etree.Element(q("commentRangeEnd"), {q("id"): cid}); runs0[-1].addnext(end)
        ref = etree.Element(q("r")); etree.SubElement(ref, q("commentReference"), {q("id"): cid}); end.addnext(ref); return
    # 共通接頭辞・接尾辞を除いた最小差分
    a = 0
    while a < min(len(orig), len(new)) and orig[a] == new[a]: a += 1
    b = 0
    while b < min(len(orig), len(new)) - a and orig[-1-b] == new[-1-b]: b += 1
    del_txt = orig[a:len(orig)-b]; ins_txt = new[a:len(new)-b]
    if not del_txt and not ins_txt: raise RevisionError("%s: 原文と修正文が同一" % rev["revision_id"])
    base = full.index(orig); s, e = base + a, base + len(orig) - b
    runs = locate(p, s, e) if del_txt else []
    anchor_first = anchor_last = None
    ins_el = None
    if ins_txt:
        if del_txt and not runs: raise RevisionError("%s: 削除対象runを特定できない" % rev["revision_id"])
        if runs: tmpl = runs[0]
        else:
            # 純挿入: 挿入位置の直前runを複製元とする
            before = locate(p, s - 1, s) if s > 0 else locate(p, s, s + 1)
            if not before: raise RevisionError("%s: 挿入位置を特定できない" % rev["revision_id"])
            tmpl = before[0]
        r = etree.Element(q("r"))
        rpr = tmpl.find(q("rPr"))
        if rpr is not None: r.append(copy.deepcopy(rpr))
        t = etree.SubElement(r, q("t")); t.text = ins_txt
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        ins_el = etree.Element(q("ins"), {q("id"): ctx.nid(), q("author"): ctx.author, q("date"): ctx.date})
        ins_el.append(r)
    del_els = []
    for r in runs:
        d = etree.Element(q("del"), {q("id"): ctx.nid(), q("author"): ctx.author, q("date"): ctx.date})
        r.addprevious(d); d.append(r)
        for t in r.findall(q("t")): t.tag = q("delText")
        del_els.append(d)
    if del_els and ins_el is not None: del_els[-1].addnext(ins_el)
    elif ins_el is not None:
        if s == 0:
            first = direct_runs(p)[0]; first.addprevious(ins_el)
        else:
            prev = locate(p, s - 1, s)[0]; prev.addnext(ins_el)
    first_el = (del_els[0] if del_els else ins_el); last_el = (ins_el if ins_el is not None else del_els[-1])
    if rev.get("comment"):
        cid = str(ctx.next_cid); ctx.next_cid += 1
        ctx.comments.append((cid, rev["comment"], rev["revision_id"]))
        first_el.addprevious(etree.Element(q("commentRangeStart"), {q("id"): cid}))
        end = etree.Element(q("commentRangeEnd"), {q("id"): cid}); last_el.addnext(end)
        ref = etree.Element(q("r")); etree.SubElement(ref, q("commentReference"), {q("id"): cid}); end.addnext(ref)

def build_comments_xml(existing, ctx):
    root = etree.fromstring(existing) if existing else etree.Element(q("comments"), nsmap={"w": W})
    for cid, text, rid in ctx.comments:
        c = etree.SubElement(root, q("comment"), {q("id"): cid, q("author"): ctx.author, q("date"): ctx.date, q("initials"): "AI"})
        for i, line in enumerate(text.split("\n")):
            pe = etree.SubElement(c, q("p")); r = etree.SubElement(pe, q("r")); t = etree.SubElement(r, q("t")); t.text = line
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("revs"); ap.add_argument("out")
    ap.add_argument("--author", default="Claude"); a = ap.parse_args()
    parts, order = read_parts(a.src)
    revs = json.load(open(a.revs, encoding="utf-8"))
    root = etree.fromstring(parts["word/document.xml"]); body = root.find(q("body"))
    # 既存コメントIDの最大値の次から採番
    ctx = Ctx(a.author)
    if "word/comments.xml" in parts:
        ids = [int(c.get(q("id"))) for c in etree.fromstring(parts["word/comments.xml"]) if c.get(q("id")).isdigit()]
        ctx.next_cid = (max(ids) + 1) if ids else 0
    # 既存の変更履歴IDとの衝突回避
    ex = [int(e.get(q("id"))) for e in root.iter(q("ins"), q("del")) if (e.get(q("id")) or "").isdigit()]
    if ex: ctx.next_id = max(ctx.next_id, max(ex))
    try:
        for rev in revs: apply_one(body, rev, ctx)
    except RevisionError as e:
        print("FAIL: " + str(e), file=sys.stderr); sys.exit(2)
    parts["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    if ctx.comments:
        parts["word/comments.xml"] = build_comments_xml(parts.get("word/comments.xml"), ctx)
        rels = etree.fromstring(parts["word/_rels/document.xml.rels"])
        if not any(r.get("Type") == COMMENT_REL for r in rels):
            ids = [r.get("Id") for r in rels]; n = 1
            while "rId%d" % n in ids: n += 1
            etree.SubElement(rels, "{%s}Relationship" % REL, {"Id": "rId%d" % n, "Type": COMMENT_REL, "Target": "comments.xml"})
            parts["word/_rels/document.xml.rels"] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)
        ct = etree.fromstring(parts["[Content_Types].xml"])
        if not any(o.get("PartName") == "/word/comments.xml" for o in ct):
            etree.SubElement(ct, "{%s}Override" % CT, {"PartName": "/word/comments.xml", "ContentType": COMMENT_CT})
            parts["[Content_Types].xml"] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)
    write_parts(a.out, parts, order)
    print("OK: %d件の修正, %d件のコメントを適用 -> %s" % (len(revs), len(ctx.comments), a.out))

if __name__ == "__main__": main()
