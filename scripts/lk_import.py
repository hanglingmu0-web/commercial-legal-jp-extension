#!/usr/bin/env python3
"""法知識・判例・出典・段落・関連付けの取込。検証(スキーマ/型/重複ID/参照先/原文との対応/ハッシュ/出典/版/不正パス/上書き/重複)に1件でも失敗した取込は全体を拒否し、
入力を import/rejected へ隔離する(既存の正常データは一切変更しない)。取り込んだ内容は『データ』であり実行命令として扱わない。
  lk_import.py source|knowledge|passages|links <file.json|jsonl> [--incoming DIR] [--update]
  lk_import.py case <案件ディレクトリ(metadata.json structured.json judgment.txt|pdf passages.jsonl manifest.json)> [--update]
  lk_import.py text <file.txt|pdf> --source-id ID --title T [--doc-type ..]   # 原本登録+テキスト抽出+段落分割(構造化はしない)
  lk_import.py rebuild   # 検索インデックスを保存データから再構築"""
import sys, os, re, json, shutil, argparse, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lk_common import *
FORBID_AI_REL = {"overrules_case", "criticizes_case", "adopts_view"}   # AI推定のみでは登録できない(判例変更・否定・学説採用)
class Reject(Exception): pass
def exists(kind, id_):
    sub = {"source": "knowledge/sources", "knowledge": "knowledge/structured", "case": "cases/metadata", "link": "knowledge/links"}[kind]; return os.path.isfile(P(*sub.split("/"), id_ + ".json"))
def passage_ids():
    out = {}
    for sub in ("knowledge/passages", "cases/passages"):
        d = P(*sub.split("/"))
        for f in (os.listdir(d) if os.path.isdir(d) else []):
            if f.endswith(".jsonl"):
                for l in open(os.path.join(d, f), encoding="utf-8"):
                    if l.strip(): r = json.loads(l); out[r["passage_id"]] = r
    return out
def quarantine(src, errors, kind):
    os.makedirs(P("import", "rejected"), exist_ok=True); d = P("import", "rejected", time.strftime("%Y%m%d%H%M%S") + "_" + re.sub(r"\W", "_", os.path.basename(src))[:40])
    os.makedirs(d, exist_ok=True)
    if os.path.isdir(src): shutil.copytree(src, os.path.join(d, "input"), dirs_exist_ok=True)
    else: shutil.copy(src, d)
    json.dump({"kind": kind, "errors": errors}, open(os.path.join(d, "reasons.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1); ledger("import", kind, [], "rejected", errors[:5]); return d
def write_atomic(items, update=False):
    """items: [(dest_path, bytes_or_json_obj|('copy',src))]。全件書込に成功しなければロールバック。上書きは update 時のみ(旧版は .history に保存)。"""
    done = []; hist = []
    try:
        for dest, data in items:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.exists(dest):
                if not update: raise Reject("既存ファイルの上書きは許可されない(--update かつ版の増加が必要): " + os.path.relpath(dest, root()))
                h = os.path.join(os.path.dirname(dest), ".history"); os.makedirs(h, exist_ok=True); hp = os.path.join(h, "%d_%s" % (time.time_ns(), os.path.basename(dest))); shutil.copy2(dest, hp); hist.append((dest, hp))
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest)); os.close(fd)
            if isinstance(data, tuple): shutil.copy2(data[1], tmp)
            elif isinstance(data, bytes): open(tmp, "wb").write(data)
            else: open(tmp, "w", encoding="utf-8").write(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=1))
            os.replace(tmp, dest); done.append(dest)
    except Exception:
        for d in done:
            h = [x for x in hist if x[0] == d]
            if h: shutil.copy2(h[0][1], d)
            else:
                try: os.remove(d)
                except OSError: pass
        raise
def check_version(kind, rec, id_field, update):
    id_ = rec[id_field]
    if exists(kind, id_):
        if not update: raise Reject("%s: 固有識別子が既に登録済み(重複登録)" % id_)
        sub = {"source": "knowledge/sources", "knowledge": "knowledge/structured", "case": "cases/metadata"}[kind]; old = load_json(P(*sub.split("/"), id_ + ".json"))
        if rec.get("version", 1) <= old.get("version", 1): raise Reject("%s: 更新は版(version)の増加が必要(現行%s)" % (id_, old.get("version")))
def import_sources(recs, inc, update):
    errs, items, seen = [], [], set()
    for r in recs:
        e = validate(r, "legal_source"); errs += ["[%s] %s" % (r.get("source_id"), x) for x in e]
        if e: continue
        sid = r["source_id"]
        if sid in seen: errs.append("%s: 同一取込内でIDが重複" % sid); continue
        seen.add(sid)
        try: check_version("source", r, "source_id", update)
        except Reject as x: errs.append(str(x)); continue
        rec = dict(r); op = r.get("original_path")
        if op:
            sp = safe_rel(inc, op)
            if not sp: errs.append("%s: original_path が不正(絶対パス/..を含む/取込ディレクトリ外)" % sid); continue
            if not os.path.isfile(sp): errs.append("%s: 原資料ファイルが存在しない(%s)" % (sid, op)); continue
            h = sha256_file(sp)
            if not r.get("sha256"): errs.append("%s: 原資料があるのに sha256 が未記載" % sid); continue
            if h != r["sha256"]: errs.append("%s: 原資料のハッシュ不一致(記載%s… 実際%s…)" % (sid, r["sha256"][:8], h[:8])); continue
            ext = os.path.splitext(sp)[1].lower() or ".bin"; rec["original_path"] = "knowledge/sources/originals/%s%s" % (sid, ext); items.append((P(*rec["original_path"].split("/")), ("copy", sp)))
        tp = r.get("ocr_text_path")
        if tp:
            sp = safe_rel(inc, tp)
            if not sp or not os.path.isfile(sp): errs.append("%s: OCRテキストが不正又は存在しない" % sid); continue
            if r.get("ocr_sha256") and sha256_file(sp) != r["ocr_sha256"]: errs.append("%s: OCRテキストのハッシュ不一致" % sid); continue
            rec["ocr_text_path"] = "knowledge/ocr/%s.txt" % sid; rec["ocr_sha256"] = sha256_file(sp); items.append((P("knowledge", "ocr", sid + ".txt"), ("copy", sp)))
        items.append((P("knowledge", "sources", sid + ".json"), rec))
    return errs, items
def import_knowledge(recs, update):
    errs, items, seen = [], [], set(); pids = passage_ids()
    for r in recs:
        e = validate(r, "legal_knowledge"); errs += ["[%s] %s" % (r.get("knowledge_id"), x) for x in e]
        if e: continue
        kid = r["knowledge_id"]
        if kid in seen: errs.append("%s: 同一取込内でIDが重複" % kid); continue
        seen.add(kid)
        try: check_version("knowledge", r, "knowledge_id", update)
        except Reject as x: errs.append(str(x)); continue
        if not exists("source", r["source_id"]): errs.append("%s: 出典資料%sが未登録(参照先が存在しない)" % (kid, r["source_id"])); continue
        for sr in r.get("source_refs", []):
            p = pids.get(sr["passage_id"])
            if not p: errs.append("%s: 原文の参照先(passage %s)が存在しない" % (kid, sr["passage_id"]))
            elif p["parent_type"] != "source" or p["parent_id"] != r["source_id"]: errs.append("%s: passage %sは出典資料%sの原文ではない" % (kid, sr["passage_id"], r["source_id"]))
        if r["knowledge_type"] == "author_view" and r["authority_class"] in ("statute_text", "court_decision"): errs.append("%s: 著者の見解(author_view)を法令条文/裁判所の判断(authority_class)として登録できない" % kid)
        if r["knowledge_type"] == "legal_principle" and r["authority_class"] in ("scholarly_view", "ai_inference") and not r.get("source_refs"): errs.append("%s: 学説/AI推論を根拠なく『法律上の原則』として登録できない" % kid)
        rec = dict(r); rec["_suspicious_instruction"] = suspicious(json.dumps(r, ensure_ascii=False)); items.append((P("knowledge", "structured", kid + ".json"), rec))
    return errs, items
def import_passages(recs, update):
    errs, items, seen, by = [], [], set(), {}
    for r in recs:
        e = validate(r, "passage"); errs += ["[%s] %s" % (r.get("passage_id"), x) for x in e]
        if e: continue
        if r["passage_id"] in seen or r["passage_id"] in passage_ids(): errs.append("%s: passage IDが重複" % r["passage_id"]); continue
        seen.add(r["passage_id"]); k = "source" if r["parent_type"] == "source" else "case"
        if not exists(k, r["parent_id"]): errs.append("%s: 親(%s %s)が未登録" % (r["passage_id"], r["parent_type"], r["parent_id"])); continue
        if r["kind"] == "correction_proposal" and not r.get("correction_of"): errs.append("%s: 訂正案(correction_proposal)は訂正対象の原文(correction_of)が必要" % r["passage_id"]); continue
        if r.get("text_sha256") and sha256_text(r["text"]) != r["text_sha256"]: errs.append("%s: text_sha256 と本文が不一致" % r["passage_id"]); continue
        r = dict(r, text_sha256=sha256_text(r["text"]), _suspicious_instruction=suspicious(r["text"])); by.setdefault((r["parent_type"], r["parent_id"]), []).append(r)
    for (pt, pid), lst in by.items():
        dest = P("knowledge" if pt == "source" else "cases", "passages", pid + ".jsonl")
        old = open(dest, encoding="utf-8").read() if os.path.isfile(dest) else ""
        items.append((dest, old + "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lst))) if not old else items.append((dest, old + "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lst)))
    return errs, items, True
def import_links(recs):
    errs, items = [], []; seen = set()
    for r in recs:
        e = validate(r, "link"); errs += ["[%s] %s" % (r.get("link_id"), x) for x in e]
        if e: continue
        if r["link_id"] in seen or os.path.isfile(P("knowledge", "links", r["link_id"] + ".json")): errs.append("%s: link IDが重複" % r["link_id"]); continue
        seen.add(r["link_id"])
        if r["basis"] == "ai_inferred" and r["relation"] in FORBID_AI_REL: errs.append("%s: AI推定のみで『%s』(判例変更・否定・学説採用)を登録できない。原資料に明示された根拠(basis=explicit_in_source+basis_passage_id)が必要" % (r["link_id"], r["relation"])); continue
        if r["basis"] == "explicit_in_source" and not r.get("basis_passage_id"): errs.append("%s: 原資料に明示とするには basis_passage_id が必要" % r["link_id"]); continue
        if not (r.get("to_id") or r.get("unresolved_ref")): errs.append("%s: 関連先(to_id)も未解決の参照(unresolved_ref)もない" % r["link_id"]); continue
        items.append((P("knowledge", "links", r["link_id"] + ".json"), r))
    return errs, items
def split_paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n|(?<=\n)(?=第[0-9０-９]+[条項])", text) if p.strip()]
def import_case(d, update):
    errs, items = [], []
    def rd(n): p = os.path.join(d, n); return load_json(p) if os.path.isfile(p) else None
    md = rd("metadata.json"); st = rd("structured.json"); mf = rd("manifest.json")
    if md is None: return ["metadata.json がない"], []
    e = validate(md, "case"); errs += ["[metadata] " + x for x in e]
    if e: return errs, []
    cid = md["case_id"]
    try: check_version("case", md, "case_id", update)
    except Reject as x: return [str(x)], []
    if st is not None:
        e = validate(st, "case"); errs += ["[structured] " + x for x in e]
        if not e and st["case_id"] != cid: errs.append("structured.json の case_id がmetadataと一致しない")
        if not e:
            for k in ("court", "decision_date", "case_number"):
                if st[k] != md[k]: errs.append("structured.json の%sがmetadata.jsonと矛盾(%s≠%s)" % (k, st[k], md[k]))
    fulltext = None
    for nm in ("judgment.pdf", "judgment.txt"):
        if os.path.isfile(os.path.join(d, nm)): fulltext = fulltext or []; fulltext.append(nm)
    if md["fulltext_status"] == "available":
        if not fulltext: errs.append("fulltext_status=available だが判決全文(judgment.pdf/judgment.txt)がない")
        else:
            if not md.get("original_sha256"): errs.append("判決全文があるのに original_sha256 が未記載")
            else:
                pdf_or_txt = os.path.join(d, "judgment.pdf") if "judgment.pdf" in fulltext else os.path.join(d, "judgment.txt")
                if sha256_file(pdf_or_txt) != md["original_sha256"]: errs.append("判決原本のハッシュ不一致(original_sha256)")
            if md["original_verification"] == "verified" and not md.get("official_url"): errs.append("original_verification=verified には official_url(公式資料の出典)が必要")
    else:
        if fulltext: errs.append("fulltext_status=unavailable だが全文ファイルが存在する(矛盾)")
        if md["original_verification"] == "verified": errs.append("判決全文が無いのに original_verification=verified にできない")
    if md["existence_status"] == "unconfirmed" and md["original_verification"] == "verified": errs.append("存在未確認の判例を原文照合済みにできない")
    for k in ("holdings",):   # 当事者の主張を裁判所の判断として登録させない(スキーマでkindを固定+文言検査)
        for h in (st or {}).get(k, []): pass
    pas = []
    pp = os.path.join(d, "passages.jsonl")
    if os.path.isfile(pp):
        existing = passage_ids()
        for r in read_records(pp):
            e = validate(r, "passage"); errs += ["[passage %s] %s" % (r.get("passage_id"), x) for x in e]
            if e: continue
            if r["parent_type"] != "case" or r["parent_id"] != cid: errs.append("passage %s の親が当該判例(%s)でない" % (r["passage_id"], cid)); continue
            if r["passage_id"] in existing and not update: errs.append("passage %s が重複" % r["passage_id"]); continue
            r = dict(r, text_sha256=sha256_text(r["text"]), _suspicious_instruction=suspicious(r["text"])); pas.append(r)
        pids = {r["passage_id"] for r in pas}
        for sect in ("holdings", "court_reasoning", "key_facts", "party_arguments", "lower_court_judgments", "supplementary_opinions", "dissenting_opinions", "ai_summaries"):
            for s in (st or {}).get(sect, []):
                for pid in s.get("passage_ids", []):
                    if pid not in pids: errs.append("structured.%s の passage_ids %s が passages.jsonl に存在しない" % (sect, pid))
        if fulltext and any(x["kind"] in ("original_text", "extracted_text") for x in pas):   # 段落が判決全文に実在するか
            ft = ""
            if "judgment.txt" in fulltext: ft = open(os.path.join(d, "judgment.txt"), encoding="utf-8").read()
            else: ft = pdf_text(os.path.join(d, "judgment.pdf"))
            for x in pas:
                if x["kind"] in ("original_text", "extracted_text") and norm(x["text"]) not in norm(ft): errs.append("passage %s の本文が判決全文に見つからない(原文との対応不良)" % x["passage_id"])
    elif md["fulltext_status"] == "available" and (st or {}).get("holdings"): errs.append("判決全文があり判示事項を登録しているが passages.jsonl(原文段落への関連付け)がない")
    if mf:
        for nm, h in (mf.get("files") or {}).items():
            sp = safe_rel(d, nm)
            if not sp or not os.path.isfile(sp): errs.append("manifest記載のファイル%sが不正又は存在しない" % nm)
            elif sha256_file(sp) != h: errs.append("manifest記載のハッシュと%sが不一致" % nm)
    if errs: return errs, []
    rec = dict(md); rec["_suspicious_instruction"] = suspicious(json.dumps(st or {}, ensure_ascii=False))
    if fulltext:
        ext = ".pdf" if "judgment.pdf" in fulltext else ".txt"; rec["fulltext_ref"] = {"path": "cases/%s/%s%s" % ("originals" if ext == ".pdf" else "fulltext", cid, ext), "sha256": md["original_sha256"]}
        if "judgment.pdf" in fulltext: items.append((P("cases", "originals", cid + ".pdf"), ("copy", os.path.join(d, "judgment.pdf")))); items.append((P("cases", "fulltext", cid + ".txt"), pdf_text(os.path.join(d, "judgment.pdf")) if "judgment.txt" not in fulltext else ("copy", os.path.join(d, "judgment.txt"))))
        else: items.append((P("cases", "fulltext", cid + ".txt"), ("copy", os.path.join(d, "judgment.txt"))))
    items.append((P("cases", "metadata", cid + ".json"), rec))
    if st is not None: items.append((P("cases", "structured", cid + ".json"), st))
    if pas: items.append((P("cases", "passages", cid + ".jsonl"), "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in pas)))
    items.append((P("cases", "manifests", cid + ".json"), {"case_id": cid, "files": {os.path.relpath(dest, root()).replace(os.sep, "/"): (sha256_file(dt[1]) if isinstance(dt, tuple) else sha256_text(dt if isinstance(dt, str) else json.dumps(dt, ensure_ascii=False, indent=1))) for dest, dt in items if True}}))
    return errs, items
def pdf_pages(path):
    import pdfplumber
    with pdfplumber.open(path) as pdf: return [(i + 1, p.extract_text() or "") for i, p in enumerate(pdf.pages)]
def pdf_text(path): return "\n\n".join(t for _, t in pdf_pages(path))
def import_text(path, sid, title, doc_type):
    """UTF-8テキスト/PDFを原本として登録し、ページ・段落単位に分割した抽出テキストを保存する。生成AIによる構造化や訂正は行わない。"""
    if exists("source", sid): return ["%s: 登録済み" % sid], []
    ext = os.path.splitext(path)[1].lower(); errs = []; items = []
    if ext == ".pdf":
        pages = pdf_pages(path); kind = "extracted_text"
        if not any(t.strip() for _, t in pages): return ["PDFにテキスト層がない(OCRが必要。OCR結果は kind=ocr / ocr_status=unchecked で別途取り込む)"], []
    elif ext == ".txt": pages = [(None, open(path, encoding="utf-8").read())]; kind = "original_text"
    else: return ["未対応の形式(%s)。JSON/JSONL/UTF-8テキスト/PDFに対応" % ext], []
    h = sha256_file(path); rec = {"source_id": sid, "version": 1, "title": title, "doc_type": doc_type, "bibliographic_status": "unconfirmed", "original_path": "knowledge/sources/originals/%s%s" % (sid, ext), "sha256": h, "ocr_text_path": "knowledge/ocr/%s.txt" % sid, "ocr_sha256": None, "authors": [], "editors": [], "publisher": None, "edition": None, "published_date": None, "license_terms": None}
    full = "\n\n".join(t for _, t in pages); rec["ocr_sha256"] = sha256_text(full)
    items += [(P(*rec["original_path"].split("/")), ("copy", path)), (P("knowledge", "ocr", sid + ".txt"), full), (P("knowledge", "sources", sid + ".json"), rec)]
    pas = []; n = 0
    for pg, t in pages:
        for k, para in enumerate(split_paragraphs(t), 1):
            n += 1; pas.append({"passage_id": "%s_p%s_%03d" % (sid, pg or 0, n), "parent_type": "source", "parent_id": sid, "page": pg, "paragraph": k, "kind": kind, "text": para, "text_sha256": sha256_text(para), "ocr_status": "not_applicable", "_suspicious_instruction": suspicious(para)})
    items.append((P("knowledge", "passages", sid + ".jsonl"), "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in pas)))
    return errs, items
def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("kind", choices=["source", "knowledge", "passages", "links", "case", "text", "rebuild"]); ap.add_argument("path", nargs="?"); ap.add_argument("--incoming"); ap.add_argument("--update", action="store_true")
    ap.add_argument("--source-id"); ap.add_argument("--title", default=""); ap.add_argument("--doc-type", default="other"); a = ap.parse_args(argv)
    if a.kind == "rebuild":
        import lk_index; n = lk_index.rebuild(); print("rebuilt", n); return 0
    if not a.path or not os.path.exists(a.path): print("入力がない"); return 2
    inc = a.incoming or (os.path.dirname(os.path.abspath(a.path)) if os.path.isfile(a.path) else a.path)
    try:
        if a.kind == "case": errs, items = import_case(a.path, a.update); upd = a.update
        elif a.kind == "text": errs, items = import_text(a.path, a.source_id or "", a.title, a.doc_type); upd = False
        else:
            recs = read_records(a.path)
            if a.kind == "source": errs, items = import_sources(recs, inc, a.update)
            elif a.kind == "knowledge": errs, items = import_knowledge(recs, a.update)
            elif a.kind == "links": errs, items = import_links(recs)
            else: errs, items, _ = import_passages(recs, a.update)
            upd = a.update or a.kind == "passages"
    except Exception as e:
        errs, items, upd = ["入力を読めない/処理中の例外: %s: %s" % (type(e).__name__, str(e)[:160])], [], False
    if errs:
        d = quarantine(a.path, errs, a.kind); print("REJECTED(既存データは変更していない) -> %s" % os.path.relpath(d, root()))
        for e in errs[:30]: print(" -", e)
        return 1
    try: write_atomic(items, upd)
    except Reject as x:
        d = quarantine(a.path, [str(x)], a.kind); print("REJECTED:", x); return 1
    ids = sorted({os.path.basename(p).split(".")[0] for p, _ in items if p.endswith(".json")}); ledger("import", a.kind, ids, "accepted")
    try:
        import lk_index; lk_index.rebuild()
    except Exception as e: print("(索引の再構築に失敗: %s。保存データは正常。`lk_import.py rebuild` で再構築可能)" % e)
    print("ACCEPTED:", a.kind, ids); return 0
if __name__ == "__main__": sys.exit(main())
