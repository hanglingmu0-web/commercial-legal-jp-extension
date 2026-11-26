#!/usr/bin/env python3
"""v0.5 一般規則集(特定の契約書の正解を持たない。契約の類型・条項名に依存しない検査のみ)。
 1. scan_unverified_legal: 一次資料で確認していない法的有効性・適法性の断定を、全記録(初回/再検証/反証/採否/Wordコメント/報告書)から検出
 2. ref_targets / ref_problems: 修正案が引用・準用する条項の実在と、参照先の未解消問題(問題を他条項へ拡張しない)
 3. penalty 系数値(違約金・遅延損害金・利率等)の合理性評価項目(PEN)と『有利だからのみ』の排除
 4. issue_groups: 複数条項にまたがる論点の管理と4層の検証状況(文言/法的効果/条項全体/論点全体)
 5. comments: Wordコメント全文の完全一致検証 / 相手方提示用コメントの漏えい検査
合格は手続上の不備が検出されなかったことのみを意味し、法的判断の正確性を保証しない。"""
import re, json, os, zipfile
from lxml import etree

# ---------- 1. 未確認の法的判断の断定 ----------
LEGAL_ASSERT = re.compile(
    r"(法的に(は)?(無効|有効)|無効(では|で)ない|無効とは(ならない|言えない|いえない)|有効(である|だ|と解|と考え|と判断|に成立|に指定|とされる)|適法(である|だ|と)|違法(では|で)ない|"
    r"強行法規(に)?(違反|抵触)(しない|する)|公序良俗(に)?(違反|反)(しない|する)|法令上(の)?問題(は)?(ない|ありません)|差し支えない|支障(は)?ない|"
    r"(管轄|合意管轄|専属的合意管轄).{0,20}(有効|無効|問題な|差し支え|認められ|許容)|(無効|違法)(である|となる|と解される|となり得る)|制限(されない|はない)|"
    r"(裁判例|判例)(上|でも|において)?.{0,12}(認め|許容|有効))")
HEDGE = re.compile(
    r"(未確認|確認でき(て)?(い)?(ない|ません)|断定(は)?(しない|できない|せず|を避け)|要確認|判断保留|不明|可能性|おそれ|とは限らない|確認(が|を)(必要|要する)|未検証|"
    r"判断しない|検討(を要する|が必要)|別途(の)?(法的)?(検討|確認)|条件付き|余地|前提とせず|前提としない|未調査|一次資料(を)?(取得|確認)(して|し)?(い)?(ない|できない|未了)|"
    r"確認済(み)?の?一次資料|機械取得原文(と|で)(照合|確認)済)")
SKIP_KEYS = {"original_text", "revised_text", "quote", "contract_quote", "key_terms", "value_text", "text_quote", "source_text"}
def _sentences(s): return [x for x in re.split(r"(?<=[。\n；;])", s) if x.strip()]
def walk_strings(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS: continue
            yield from walk_strings(v, path + "/" + str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj): yield from walk_strings(v, "%s[%d]" % (path, i))
    elif isinstance(obj, str): yield path, obj
def scan_text(name, text):
    out = []
    for sen in _sentences(text):
        m = LEGAL_ASSERT.search(sen)
        if m and not HEDGE.search(sen): out.append({"where": name, "match": m.group(0), "sentence": sen.strip()[:160]})
    return out
def scan_unverified_legal(records):
    """records: {名称: JSONオブジェクト|文字列}。一次資料(機械取得原文)で未確認の法的有効性等の断定文を検出する。"""
    F = []
    for nm, rec in records.items():
        if isinstance(rec, str): F += scan_text(nm, rec)
        else:
            for p, s in walk_strings(rec): F += scan_text(nm + p, s)
    return F
def collect_records(d, extra=None):
    """案件ディレクトリ内の全記録(最終結論だけでなく中間記録・コメント・報告書)を集める。"""
    rec = {}
    for rel in ("first/review.json", "verifier/review_verifier.json", "adversarial/adversarial.json", "resolutions.json", "disagreements.json", "option_selection.json", "revision_checks.json", "issue_groups.json"):
        p = os.path.join(d, rel)
        if os.path.isfile(p):
            try: rec[rel] = json.load(open(p, encoding="utf-8"))
            except Exception: pass
    for rel in ("word_revisions.json", "word_revisions_external.json"):
        p = os.path.join(d, rel)
        if os.path.isfile(p):
            try: rec[rel] = [{"comment": x.get("comment", "")} for x in json.load(open(p, encoding="utf-8"))]
            except Exception: pass
    for rel in ("report_practical.md", "technical_record.md"):
        p = os.path.join(d, rel)
        if os.path.isfile(p): rec[rel] = open(p, encoding="utf-8").read()
    rec.update(extra or {}); return rec

# ---------- 2. 準用・参照 ----------
REF = re.compile(r"第([0-9０-９]+)条(?:第([0-9０-９]+)項)?")
def z2h(s): return s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
def ref_targets(revised_text, own_clause):
    out = []
    for m in REF.finditer(revised_text or ""):
        c = "第%s条" % z2h(m.group(1)); p = z2h(m.group(2)) if m.group(2) else None
        if c != own_clause: out.append((c, p))
    return out
def clause_block(contract_text, clause):
    m = re.search(r"^%s.*$" % re.escape(clause), contract_text, flags=re.M)
    if not m: return None
    rest = contract_text[m.end():]; n = re.search(r"^第[0-9０-９]+条", rest, flags=re.M)
    return rest[: n.start()] if n else rest
def paragraph_exists(contract_text, clause, para):
    b = clause_block(contract_text, clause)
    if b is None: return False
    nums = {z2h(x) for x in re.findall(r"^\s*([0-9０-９]+)[\.．]", b, flags=re.M)}
    if not nums: return para == "1"
    return para in nums
def ref_problems(rev, contract_text, own_clause, clause_unresolved):
    """戻り値: (hard=実在しない参照[反映禁止], soft=参照先に未解消の問題[条件付き])"""
    hard, soft = [], []
    for c, p in ref_targets(rev.get("revised_text", ""), own_clause):
        if clause_block(contract_text, c) is None: hard.append("%s(条が存在しない)" % c); continue
        if p and not paragraph_exists(contract_text, c, p): hard.append("%s第%s項(項が存在しない)" % (c, p))
        if clause_unresolved.get(c): soft.append("%s: %s" % (c, "; ".join(clause_unresolved[c])[:200]))
    return hard, soft
def clause_unresolved_map(review, states, nkey):
    """条ごとの未解消事項: 判断保留/open_issues(未解消)/検証済み以外の修正状態。参照先の問題を他条項へ拡張しないために使う。"""
    m = {}
    def add(k, t): m.setdefault(k, []).append(t)
    for j in review.get("judgments", []):
        k = nkey(j.get("clause"))
        if j.get("conclusion_status") == "判断保留": add(k, "判断保留(%s)" % j.get("id"))
        for oi in j.get("open_issues", []) or []:
            if (oi.get("status") or "未解消") != "解消": add(k, "未解消の論点: %s" % (oi.get("text") or "")[:80])
        for s in j.get("statutes", []) or []:
            if s.get("asserted_applicable") is False and j.get("legally_mandatory"): add(k, "法令適合性が未確認")
    for s in states:
        if s.get("revision_id") and s.get("state") not in ("検証済み・反映可能", "修正不要", "複数案(他案)"):
            add(s["clause"], "修正%s=%s" % (s["revision_id"], s["state"]))
    return m

# ---------- 3. 違約金・遅延損害金・利率等(任意設定の数値)の合理性評価 ----------
PEN_RE = re.compile(r"(違約金|遅延|損害金|延滞|利息|利率|年率|ペナルティ|賠償額の予定|無償譲渡|日割)")
PEN = ["p1_basis", "p2_expected_loss", "p3_vs_contract_amount", "p4_delayed_part_vs_whole", "p5_cap", "p6_vs_damages", "p7_overlap_other_penalty", "p8_burden", "p9_performability", "p10_negotiation", "p11_base_alternatives"]
PEN_JA = {"p1_basis": "数値の設定根拠", "p2_expected_loss": "想定損害との関係", "p3_vs_contract_amount": "契約金額との関係", "p4_delayed_part_vs_whole": "遅延部分と契約全体の関係", "p5_cap": "違約金の上限", "p6_vs_damages": "別途の損害賠償請求との関係",
          "p7_overlap_other_penalty": "他の違約金との重複", "p8_burden": "契約当事者の負担", "p9_performability": "履行可能性", "p10_negotiation": "交渉上の合理性", "p11_base_alternatives": "算定基礎の代替案(遅延した部分の代金額を基礎とする案を含む)の検討"}
ONLY_FAVOR = re.compile(r"((当社|甲)(に|にとって)有利(である|だ)?(ため|ので|から|という理由)|(甲|当社)の(取得|受領|回収)額が(減少|減る|小さく)(する|なる)?(ため|ので|から)|有利なため修正しない|有利であるため(合理的|妥当|修正不要))")
def is_penalty_like(n): return bool(PEN_RE.search((n.get("term_label") or "") + (n.get("value_text") or "")) or n.get("numeric_type") in ("penalty", "interest", "cap"))
def penalty_findings(nr, tier):
    """nr: numeric_reviews の1件。戻り値: [(severity, kind, message)]"""
    F = []; lab = nr.get("term_label"); pc = nr.get("penalty_checks") or {}
    if not is_penalty_like(nr): return F
    miss = [k for k in PEN if k not in pc]
    if miss: F.append(("error", "機械検証", "違約金等『%s』: 追加評価項目が欠落%s" % (lab, [PEN_JA[k] for k in miss])))
    for k in PEN:
        v = pc.get(k)
        if not v: continue
        if v.get("status") not in ("評価済", "未評価", "不明"): F.append(("error", "機械検証", "違約金等『%s』: %sのstatusが不正" % (lab, PEN_JA[k])))
        if v.get("status") == "評価済" and len((v.get("text") or "").strip()) < 15: F.append(("error", "機械検証", "違約金等『%s』: %sが評価済だが内容が実質的でない" % (lab, PEN_JA[k])))
    alltext = " ".join((v or {}).get("text", "") for v in pc.values()) + " " + (nr.get("retention_reason") or "") + " " + (nr.get("rationality_conclusion") or "")
    if ONLY_FAVOR.search(alltext): F.append(("error", "機械検証", "違約金等『%s』: 当社に有利/当社の取得額が減ることのみを理由に合理的と判断又は代替案を排除している" % lab))
    b = pc.get("p11_base_alternatives") or {}
    if b.get("status") == "評価済" and not b.get("compared_alternatives"): F.append(("error", "機械検証", "違約金等『%s』: 算定基礎の代替案を検討したと記録しながら比較した案(compared_alternatives)がない" % lab))
    if not (nr.get("rationality_status") in ("確認済", "未確認", "条件付き")): F.append(("error", "機械検証", "違約金等『%s』: 数値そのものの合理性の確認状況(rationality_status=確認済/条件付き/未確認)が未記載" % lab))
    if nr.get("rationality_status") == "確認済":
        unev = [PEN_JA[k] for k in PEN if (pc.get(k) or {}).get("status") != "評価済"]
        if unev: F.append(("error", "機械検証", "違約金等『%s』: 合理性『確認済』だが未評価/不明の項目あり%s" % (lab, unev)))
        if not nr.get("rationality_evidence"): F.append(("error", "機械検証", "違約金等『%s』: 合理性『確認済』だが一次資料又は経済的合理性の根拠資料(rationality_evidence)の記録がない" % lab))
    if nr.get("retained") and not (nr.get("retention_reason") or "").strip(): F.append(("error", "機械検証", "違約金等『%s』: 数値を維持するが理由(retention_reason)がない" % lab))
    F.append(("info", "要人間判断", "違約金等『%s』: 数値の合理性(想定損害・契約金額との釣り合い)は機械判定不能。確認済みでない場合、条項全体を検証済みとして扱わない" % lab))
    return F

# ---------- 4. 複数条項にまたがる論点・4層の検証状況 ----------
CROSS_TOPICS = {   # (論点キー): (キーワードA, キーワードB, 表示名)。双方が契約書に現れる場合のみ検討を要求(類型非依存)
    "pay_vs_acceptance": (r"(支払|代金|対価)", r"(検収|検査)", "支払条件と検収条件"),
    "tooling_vs_ownership": (r"(金型|治具|型)", r"(所有権|帰属|譲渡)", "金型製作費用と所有権移転"),
    "penalty_vs_damages": (r"(違約金|遅延損害金|損害金)", r"(損害賠償|賠償)", "違約金と損害賠償"),
    "cap_vs_exceptions": (r"(上限|限度|を超えない)", r"(故意|重大な過失|除く|ただし)", "損害賠償上限と例外"),
    "termination_vs_accrued": (r"(解除|解約|終了)", r"(既に|既発生|債権|債務|期限の利益)", "契約解除と既発生債権"),
    "termination_vs_wip": (r"(解除|解約|終了)", r"(仕掛|在庫|原材料|費用)", "契約解除と仕掛品等の費用"),
    "quality_vs_recall": (r"(品質保証|保証|不具合|契約不適合)", r"(回収|リコール|市場措置|是正)", "品質保証と回収費用"),
    "tooling_delivery_vs_supply": (r"(金型|治具)", r"(引渡|返還|供給|継続供給|保管)", "金型引渡義務と供給継続"),
}
def required_cross_topics(contract_text):
    """契約書全体に双方のキーワードが現れる論点のみ要求する(類型・条項番号に依存しない)。"""
    out = []
    for k, (a, b, nm) in CROSS_TOPICS.items():
        if re.search(a, contract_text) and re.search(b, contract_text): out.append((k, nm))
    return out
LAYERS = ["wording_status", "effect_status", "clause_status", "issue_status"]
LV = {"検証済": 3, "条件付き": 2, "未検証": 1, "問題あり": 0}
LAYER_JA = {"wording_status": "修正文言", "effect_status": "修正文案の法的効果", "clause_status": "条項全体", "issue_status": "関連条項を含む論点全体"}
def issue_group_findings(rv, contract_text):
    F = []; groups = rv.get("issue_groups")
    req = required_cross_topics(contract_text) if contract_text else []
    if groups is None:
        if req: F.append(("error", "機械検証", "複数条項にまたがる論点の管理(issue_groups)がない。検討を要する論点: %s" % [nm for _, nm in req]))
        return F
    by_topic = {g.get("topic_key"): g for g in groups}
    for k, nm in req:
        g = by_topic.get(k)
        if not g: F.append(("error", "機械検証", "複数条項論点『%s』の検討記録(issue_groups.topic_key=%s)がない(該当しない場合も『該当なし』と理由を記録する)" % (nm, k))); continue
        if g.get("applicable") is False and len((g.get("not_applicable_reason") or "").strip()) < 10: F.append(("error", "機械検証", "論点『%s』: 該当なしとするが理由がない" % nm))
    clauses = {m for m in re.findall(r"^(第[0-9０-９]+条)", contract_text or "", flags=re.M)}
    for g in groups:
        if g.get("applicable") is False: continue
        gid = g.get("id") or g.get("topic_key"); cl = g.get("related_clauses") or []
        if len(cl) < 2: F.append(("error", "機械検証", "論点%s: 関連条項が2条以上明示されていない(複数条項論点)" % gid))
        for c in cl:
            if contract_text and c not in clauses: F.append(("error", "機械検証", "論点%s: 関連条項%sが契約書に存在しない" % (gid, c)))
        st = {k: g.get(k) for k in LAYERS}
        for k, v in st.items():
            if v not in LV: F.append(("error", "機械検証", "論点%s: %sの検証状況(%s)が不正又は未記載(文言/法的効果/条項全体/論点全体を別々に記録)" % (gid, LAYER_JA[k], v)))
        if all(v in LV for v in st.values()):
            for lo, hi in zip(LAYERS, LAYERS[1:]):
                if LV[st[hi]] > LV[st[lo]]: F.append(("error", "機械検証", "論点%s: %s(%s)が下位の%s(%s)より高い(下位が未確認なら上位を検証済みとしない)" % (gid, LAYER_JA[hi], st[hi], LAYER_JA[lo], st[lo])))
        pc = g.get("post_revision_check") or {}
        if pc.get("status") not in ("解消", "未解消", "要判断") or len((pc.get("text") or "").strip()) < 15: F.append(("error", "機械検証", "論点%s: 修正後の契約全体で問題が解消したかの確認(post_revision_check)が未記載" % gid))
        if st.get("issue_status") == "検証済" and pc.get("status") != "解消": F.append(("error", "機械検証", "論点%s: 論点全体『検証済』だが修正後の確認は『%s』" % (gid, pc.get("status"))))
        if g.get("single_clause_fix_only") and st.get("issue_status") == "検証済": F.append(("error", "機械検証", "論点%s: 一つの条項の修正のみで複数条項の論点を解決済みとしている" % gid))
    return F

# ---------- 5. Wordコメント ----------
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def docx_comments(path):
    z = zipfile.ZipFile(path)
    if "word/comments.xml" not in z.namelist(): return []
    out = []
    for c in etree.fromstring(z.read("word/comments.xml")):
        paras = []
        for p in c.iter("{%s}p" % W): paras.append("".join(t.text or "" for t in p.iter("{%s}t" % W)))
        out.append({"id": c.get("{%s}id" % W), "author": c.get("{%s}author" % W), "text": "\n".join(paras)})
    return out
def _n(s): return re.sub(r"\s+", "", s or "")
def verify_comments(path, expected):
    """expected: word_revisions(コメントを持つもの)。件数でなく本文の完全一致を検証する。戻り値: (errors, details)"""
    got = docx_comments(path); E = []; D = []
    exp = [x for x in expected if x.get("comment")]
    if len(got) != len(exp): E.append("コメント件数: 予定%d件に対し実ファイル%d件" % (len(exp), len(got)))
    used = set()
    for x in exp:
        want = _n(x["comment"]); hit = None
        for i, g in enumerate(got):
            if i in used: continue
            if _n(g["text"]) == want: hit = i; break
        if hit is None:
            part = next((i for i, g in enumerate(got) if i not in used and want.startswith(_n(g["text"])[:30]) and len(_n(g["text"])) < len(want)), None)
            if part is not None:
                used.add(part); E.append("%s: コメント本文が途中で途切れている(予定%d字に対し実際%d字。欠落末尾『%s』)" % (x["revision_id"], len(want), len(_n(got[part]["text"])), x["comment"].replace("\n", "")[len(_n(got[part]["text"])) - 0:][:30]))
            else: E.append("%s: 予定したコメント本文がWordファイルに存在しない" % x["revision_id"])
            D.append({"revision_id": x["revision_id"], "match": False}); continue
        used.add(hit); D.append({"revision_id": x["revision_id"], "match": True, "chars": len(want)})
    for x in exp:   # 複数案・選定理由・代替案の識別マーカー
        c = x["comment"]
        if "他案" in c and "理由" not in c: E.append("%s: 他案を記載しているが選定理由の記載がない" % x["revision_id"])
    return E, D
LEAK = re.compile(r"(AI|ＡＩ|独立再検証|反証|検証者|判断保留|交渉上の(提案|選択肢|許容)|不採用|採用案|選定理由|他案|社内|当社の(判断|方針|許容|基準)|許容範囲|譲歩|下限|プレイブック|プロファイル|一次資料未確認|機械検証|システム|経営判断|取引判断|最低|ここまで)")
def external_leaks(comments):
    F = []
    for c in comments:
        m = LEAK.search(c.get("text", c.get("comment", "")))
        if m: F.append("相手方提示用コメントに内部情報の疑い『%s』: %s" % (m.group(0), (c.get("text") or c.get("comment") or "")[:50].replace("\n", " ")))
    return F
