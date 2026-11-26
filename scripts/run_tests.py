#!/usr/bin/env python3
"""回帰テスト一括実行。結果は ../logs/test_results_<日時>.json に保存し、直前の結果と比較する。
使い方: python3 run_tests.py   (終了コード 0=全合格, 1=不合格あり)
"""
import sys, os, json, subprocess, tempfile, shutil, datetime, glob, zipfile, copy, re, platform
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lxml import etree
from docx_common import *
import validate_docx, compare_documents, check_review_output, check_config, verify_dates
import docx as pydocx
from docx.shared import Pt, Cm

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="cltest_")
RESULTS = []
def record(cat, name, expect, passed, detail=""):
    RESULTS.append({"category": cat, "name": name, "expected": expect, "result": "PASS" if passed else "FAIL", "detail": detail})

def run(args):
    p = subprocess.run([sys.executable, "-I"] + args, capture_output=True, text=True, cwd=HERE)
    return p.returncode, p.stdout + p.stderr

# ---------- テスト用DOCX ----------
def make_base(path):
    d = pydocx.Document()
    d.add_paragraph("売買基本契約書", style="Title")
    d.add_paragraph("第1条（納期）受託者は、前条の物品を令和8年12月1日までに納入する。")
    p = d.add_paragraph(); r = p.add_run("第2条（遅延損害金）"); r.bold = True
    p.add_run("納期に遅れた場合、受託者は年率14.6％の遅延損害金を支払う。")
    p.paragraph_format.left_indent = Cm(1.0); p.paragraph_format.first_line_indent = Cm(-0.5)
    d.add_paragraph("支払条件は月末締め翌月末払いとする。", style="List Number")
    d.add_paragraph("支払条件は月末締め翌月末払いとする。", style="List Number")   # 同一文言(曖昧性テスト用)
    t = d.add_table(rows=2, cols=2); t.cell(0, 0).text = "品名"; t.cell(0, 1).text = "金型A"; t.cell(1, 0).text = "数量"; t.cell(1, 1).text = "1式"
    d.add_paragraph("管轄裁判所は東京地方裁判所とする。")
    d.save(path)
REVS = [
 {"revision_id": "REV-001", "clause": "第2条", "paragraph_id": "", "original_text": "年率14.6％の遅延損害金", "revised_text": "年率3.0％の遅延損害金", "reason": "テスト", "comment": "根拠確認要\n(テスト用コメント)", "risk_category": "D", "evidence_ids": [], "verification_status": "検証済"},
 {"revision_id": "REV-002", "clause": "第1条", "paragraph_id": "", "original_text": "令和8年12月1日までに", "revised_text": "令和8年12月15日までに", "reason": "テスト", "comment": "納期変更", "risk_category": "D", "evidence_ids": [], "verification_status": "検証済"},
 {"revision_id": "REV-003", "clause": "管轄", "paragraph_id": "", "original_text": "東京地方裁判所とする", "revised_text": "東京地方裁判所を第一審の専属的合意管轄裁判所とする", "reason": "テスト(純挿入を含む)", "comment": "合意管轄", "risk_category": "E", "evidence_ids": [], "verification_status": "検証済"},
]
def W_(name): return os.path.join(TMP, name)
def dump(revs, name):
    p = W_(name); json.dump(revs, open(p, "w", encoding="utf-8"), ensure_ascii=False); return p
def mutate(src, dst, fn):
    parts, order = read_parts(src); fn(parts); write_parts(dst, parts, order)
def edit_doc(parts, fn):
    root = etree.fromstring(parts["word/document.xml"]); fn(root)
    parts["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

def docx_tests():
    base = W_("base.docx"); make_base(base)
    rp = dump(REVS, "revs.json"); out = W_("out1.docx")
    rc, o = run([os.path.join(HERE, "apply_revisions.py"), base, rp, out])
    record("docx", "正常系: 修正指示の適用", "終了コード0で出力生成", rc == 0 and os.path.exists(out), o.strip())
    if rc != 0: return
    v, st = validate_docx.validate(out, expect_ins=3, expect_del=1, expect_comments=3)
    record("docx", "正常系: 構造検証(ins3/del1/コメント3: 純挿入2件を含む)", "検証合格", not v, "; ".join(v) + str(st))
    c = compare_documents.compare(base, out, REVS)
    record("docx", "正常系: 却下で原本同等/承認で期待文面", "差分なし", not c, "; ".join(c))
    # 2回目適用: 既存の変更履歴・コメントの保持
    out2 = W_("out2.docx"); r2 = [{"revision_id": "REV-101", "clause": "x", "paragraph_id": "", "original_text": "月末締め翌月末払いとする。", "revised_text": "月末締め翌々月5日払いとする。", "reason": "t", "comment": "c", "risk_category": "D", "evidence_ids": [], "verification_status": "検証済"}]
    rc2, o2 = run([os.path.join(HERE, "apply_revisions.py"), out, dump(r2, "revs2.json"), out2])
    record("docx", "異常系: 同一文言が複数箇所 → 曖昧なまま編集しない", "終了コード2かつ出力なし", rc2 == 2 and not os.path.exists(out2), o2.strip())
    r2[0]["original_text"] = "年率3.0％の遅延損害金"   # 既存の挿入内にしか存在しない文言
    rc3, o3 = run([os.path.join(HERE, "apply_revisions.py"), out, dump(r2, "revs2b.json"), out2])
    record("docx", "異常系: 既存変更履歴内のみに存在する文言は編集拒否", "終了コード2", rc3 == 2, o3.strip())
    r2[0]["original_text"] = "存在しない文言"
    rc4, o4 = run([os.path.join(HERE, "apply_revisions.py"), out, dump(r2, "revs2c.json"), out2])
    record("docx", "異常系: 対象原文なし → 失敗を成功と報告しない", "終了コード2、FAIL出力", rc4 == 2 and "FAIL" in o4, o4.strip())
    r2[0]["original_text"] = "金型A"   # 表内の段落(適用可能)
    r2[0]["revised_text"] = "金型B"
    rc5, o5 = run([os.path.join(HERE, "apply_revisions.py"), out, dump(r2, "revs2d.json"), out2])
    ok = rc5 == 0 and not validate_docx.validate(out2)[0] and not compare_documents.compare(out, out2, r2)
    record("docx", "正常系: 2回目適用(表内)で既存の履歴/コメント/書式を保持", "検証・差分とも合格", ok, o5.strip())

    # ---- 故障注入: 全て検出されること ----
    def inject(name, fn, tool, expect):
        d = W_(name + ".docx"); mutate(out, d, fn)
        if tool == "validate": errs = validate_docx.validate(d, expect_ins=3, expect_del=1, expect_comments=3)[0]
        else: errs = compare_documents.compare(base, d, REVS)
        record("docx", "故障注入: " + name, expect, bool(errs), "; ".join(errs)[:200])
    def rm_comment_marks(p): edit_doc(p, lambda r: [e.getparent().remove(e) for e in list(r.iter(q("commentRangeStart")))[:1]])
    inject("コメント範囲の欠落", rm_comment_marks, "validate", "異常検出")
    def rm_comments_part(p): del p["word/comments.xml"]
    inject("comments.xml欠落(コメント挿入失敗の偽装)", rm_comments_part, "validate", "異常検出")
    def drop_comment_body(p):
        r = etree.fromstring(p["word/comments.xml"]); r.remove(r[0]); p["word/comments.xml"] = etree.tostring(r, xml_declaration=True, encoding="UTF-8", standalone=True)
    inject("コメント本体の欠落", drop_comment_body, "validate", "異常検出")
    def ns_break(p): p["word/document.xml"] = p["word/document.xml"].replace(b"<w:body>", b"<w:body><zz:bogus/>", 1)
    inject("名前空間宣言漏れ", ns_break, "validate", "異常検出")
    def xml_break(p): p["word/document.xml"] = p["word/document.xml"].replace(b"</w:body>", b"", 1)
    inject("XML破損", xml_break, "validate", "異常検出")
    def dup_id(p):
        def f(r):
            es = list(r.iter(q("ins"), q("del"))); es[1].set(q("id"), es[0].get(q("id")))
        edit_doc(p, f)
    inject("変更履歴ID重複", dup_id, "validate", "異常検出")
    def no_track(p):   # 変更履歴を使わず直接上書き(ins/delを承認済みの形で埋め込む)
        def f(r):
            for e in list(r.iter(q("del"))): e.getparent().remove(e)
            for e in list(r.iter(q("ins"))):
                par = e.getparent(); i = par.index(e)
                for ch in list(e): par.insert(i, ch); i += 1
                par.remove(e)
        edit_doc(p, f)
    inject("変更履歴なしの直接上書き", no_track, "validate", "件数不一致を検出")
    def lose_indent(p):
        def f(r):
            for i in list(r.iter(q("ind"))): i.getparent().remove(i)
        edit_doc(p, f)
    inject("インデント消失", lose_indent, "compare", "異常検出")
    def lose_numpr(p):
        def f(r):
            hit = [e for e in r.iter(q("pStyle")) if "ListNumber" in (e.get(q("val")) or "")]
            assert hit, "試験用の番号付き段落が見つからない(故障注入が無効)"
            hit[0].getparent().remove(hit[0])
        edit_doc(p, f)
    inject("自動番号の破損", lose_numpr, "compare", "異常検出")
    def other_edit(p):
        def f(r):
            for t in r.iter(q("t")):
                if t.text and "支払条件" in t.text: t.text = t.text.replace("月末払い", "15日払い"); break
        edit_doc(p, f)
    inject("修正対象外の本文変更", other_edit, "compare", "異常検出")
    def fmt_loss(p):
        def f(r):
            for b in list(r.iter(q("b")))[:1]: b.getparent().remove(b)
        edit_doc(p, f)
    inject("修正対象外の文字書式(太字)消失", fmt_loss, "compare", "異常検出")
    def table_loss(p):
        def f(r):
            for t in list(r.iter(q("tr")))[:1]: t.getparent().remove(t)
        edit_doc(p, f)
    inject("表構造の破損", table_loss, "compare", "異常検出")
    def style_change(p):
        n = [k for k in p if k.endswith("styles.xml")][0]; p[n] = p[n].replace(b"<w:name ", b"<w:name  ", 1) if False else p[n] + b"<!--x-->"
    def styles_edit(p):
        n = "word/styles.xml"; r = etree.fromstring(p[n]); etree.SubElement(r, q("style"), {q("styleId"): "Injected", q("type"): "paragraph"}); p[n] = etree.tostring(r, xml_declaration=True, encoding="UTF-8", standalone=True)
    inject("スタイル定義の変更", styles_edit, "compare", "異常検出")
    def lose_rev(p):   # 修正漏れ: 1件分のins/delを取り除き原文へ戻す
        def f(r):
            e = list(r.iter(q("ins")))[0]; e.getparent().remove(e)
        edit_doc(p, f)
    inject("修正漏れ(挿入欠落)", lose_rev, "compare", "異常検出")
    # 既存コメント/履歴の消失(out を原本とみなし out2 から欠落させる)
    def lose_existing_comment(p):
        r = etree.fromstring(p["word/comments.xml"]); r.remove(r[0]); p["word/comments.xml"] = etree.tostring(r, xml_declaration=True, encoding="UTF-8", standalone=True)
    d = W_("lostcomment.docx"); mutate(out2, d, lose_existing_comment)
    errs = compare_documents.compare(out, d)
    record("docx", "故障注入: 既存コメント消失", "異常検出", bool(errs), "; ".join(errs)[:200])
    def lose_existing_rev(p):
        def f(r):
            e = list(r.iter(q("ins")))[0]; e.getparent().remove(e)
        edit_doc(p, f)
    d = W_("lostrev.docx"); mutate(out2, d, lose_existing_rev)
    errs = compare_documents.compare(out, d)
    record("docx", "故障注入: 既存変更履歴消失", "異常検出", bool(errs), "; ".join(errs)[:200])
    # LibreOfficeでの実開封(Word実機の代替ではない)
    if shutil.which("soffice"):
        try:
            p = subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", TMP, out], capture_output=True, text=True, timeout=120)
            record("docx", "参考: LibreOfficeでの開封・PDF変換(Word実機検証の代替ではない)", "変換成功", os.path.exists(W_("out1.pdf")), p.stderr[-150:])
        except Exception as e: record("docx", "参考: LibreOffice開封", "変換成功", False, str(e))

# ---------- 法的判断の手続検査 ----------
GOOD = {
 "evidence": [{"id": "E1", "title": "中小受託取引適正化法", "issuer": "e-Gov法令検索", "url": "https://laws.e-gov.go.jp/", "retrieved_at": "2026-11-24T12:00:00+09:00", "source_type": "一次", "verified": True}],
 "judgments": [{"id": "J1", "category": "G", "category_reason": "資本金等の事実関係が不明のため確認事項", "conclusion_status": "条件付き", "legally_mandatory": False,
   "statutes": [{"name": "中小受託取引適正化法", "law_number": "(要確認)", "article": "第2条", "effective_status": "施行済", "reference_date": "2026-11-24", "evidence_ids": ["E1"], "asserted_applicable": False,
     "requirements": [{"name": "資本金区分", "status": "事実関係不明", "basis": "契約書に資本金の記載なし"}]}],
   "numbers": [{"label": "遅延損害金率", "evidence_ids": ["E1"]}]}],
 "revisions": [{"revision_id": "R1", "reason": "確認事項", "original_text": "a", "revised_text": "b", "evidence_ids": ["E1"], "verification_status": "検証済", "apply_to_word": True}]}
def legal_tests():
    errs = check_review_output.check(GOOD)
    record("legal", "手続検査: 正常な出力", "違反なし", not errs, "; ".join(errs))
    def case(name, fn, expect_substr):
        d = copy.deepcopy(GOOD); fn(d); errs = check_review_output.check(d)
        record("legal", "手続検査: " + name, "違反を検出", any(expect_substr in e for e in errs), "; ".join(errs)[:200])
    s = lambda d: d["judgments"][0]["statutes"][0]
    case("適用要件未確認のまま適用を断定", lambda d: s(d).update(asserted_applicable=True), "適用を断定")
    case("未施行法令を現行法として適用", lambda d: s(d).update(effective_status="未施行", asserted_applicable=True, requirements=[{"name": "x", "status": "充足", "basis": "x"}]), "現行法として適用")
    case("根拠資料なし", lambda d: s(d).update(evidence_ids=[]), "根拠資料なし")
    case("存在しない資料ID(架空引用)", lambda d: s(d).update(evidence_ids=["E9"]), "存在しない資料ID")
    case("未確認資料を根拠に確定", lambda d: (d["evidence"][0].update(verified=False), d["judgments"][0].update(conclusion_status="確定")), "未確認資料")
    case("一次資料なしで確定", lambda d: (d["evidence"][0].update(source_type="二次"), d["judgments"][0].update(conclusion_status="確定")), "一次資料なし")
    case("根拠なき数値(年率14.6%転用)", lambda d: d["judgments"][0].update(numbers=[{"label": "年率14.6%"}]), "根拠なし")
    case("適用未確定なのに法令上必須と表示", lambda d: d["judgments"][0].update(legally_mandatory=True), "法令上必須")
    case("要件判定理由なし", lambda d: s(d)["requirements"][0].pop("basis"), "判定理由なし")
    case("分類理由なし", lambda d: d["judgments"][0].pop("category_reason"), "分類理由なし")
    case("判断保留の修正をWord反映", lambda d: d["revisions"][0].update(verification_status="判断保留"), "判断保留")
    case("原文と同一の修正(不要な修正)", lambda d: d["revisions"][0].update(revised_text="a"), "同一の修正")
    case("法令の現行性情報欠落", lambda d: s(d).pop("effective_status"), "法令情報欠落")
    # 日付
    n, bad = verify_dates.scan("令和8年12月1日(火)に納入。2026年11月24日（火）に締結。")
    record("date", "曜日検算: 正しい曜日", "誤りなし(2件検査)", n == 2 and not bad, str(bad))
    n, bad = verify_dates.scan("2026年11月24日（水）に締結。")
    record("date", "曜日検算: 誤った曜日", "不一致を検出", len(bad) == 1, str(bad))
    import datetime
    record("date", "月加算: 1/31+1か月=2/28(閏年外)", "2027-02-28", str(verify_dates.addmonths(datetime.date(2027, 1, 31), 1)) == "2027-02-28")

# ---------- 設定の永続化 ----------
def persistence_tests():
    d = os.path.join(TMP, "cfg"); os.makedirs(d)
    ok = os.path.join(d, "CLAUDE.md"); open(ok, "w", encoding="utf-8").write("# 実務プロファイル\n当社は製造業者。\n")
    ph = os.path.join(d, "ph.md"); open(ph, "w", encoding="utf-8").write("[PLACEHOLDER — x]")
    other = os.path.join(d, "other.md"); open(other, "w", encoding="utf-8").write("別内容")
    record("persistence", "正常な設定ファイル", "合格", not check_config.check([ok]))
    record("persistence", "設定ファイル不存在 → 異常検出(一般基準への無断切替防止)", "検出", any("設定未読込" in e for e in check_config.check([os.path.join(d, "none.md")])))
    record("persistence", "空ファイル", "検出", bool(check_config.check([os.path.join(d, "empty.md")])) or (open(os.path.join(d, "empty.md"), "w").close() or bool(check_config.check([os.path.join(d, "empty.md")]))))
    record("persistence", "プレースホルダ残存", "検出", any("プレースホルダ" in e for e in check_config.check([ph])))
    record("persistence", "内容の異なる複数設定(競合)", "検出", any("複数" in e for e in check_config.check([ok, other])))
    record("persistence", "新規Coworkセッションからの参照・再起動後保持・customize永続化", "利用者手動試験(docs/操作手順書.md 試験P-1〜P-4)", False, "自動実行不可: 未実施。合格として扱わない")

def main():
    docx_tests(); legal_tests(); persistence_tests()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    logs = os.path.join(ROOT, "logs"); os.makedirs(logs, exist_ok=True)
    prev = sorted(glob.glob(os.path.join(logs, "test_results_*.json")))
    summary = {"timestamp": ts, "python": platform.python_version(), "scripts_sha256": {os.path.basename(f): sha256(f) for f in glob.glob(os.path.join(HERE, "*.py"))}, "results": RESULTS}
    path = os.path.join(logs, "test_results_%s.json" % ts); json.dump(summary, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    auto = [r for r in RESULTS if not r["expected"].startswith("利用者手動")]
    p = sum(r["result"] == "PASS" for r in auto)
    for r in RESULTS:
        if r["result"] != "PASS": print("[FAIL]", r["category"], r["name"], "|", r["detail"][:160])
    print("自動テスト: %d/%d 合格 (手動試験 %d件は未実施)" % (p, len(auto), len(RESULTS) - len(auto)))
    if prev:
        old = {(r["category"], r["name"]): r["result"] for r in json.load(open(prev[-1], encoding="utf-8"))["results"]}
        reg = [k for k, v in old.items() if v == "PASS" and next((r["result"] for r in RESULTS if (r["category"], r["name"]) == k), None) == "FAIL"]
        print("前回比の退行: ", reg or "なし")
    print("結果保存:", path); shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(0 if p == len(auto) else 1)
if __name__ == "__main__": main()
