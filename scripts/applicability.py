#!/usr/bin/env python3
"""取適法(中小受託取引適正化法)の適用要件を構造化判定する決定論的エンジン。
入力: facts JSON(契約・当事者の事実関係。不明は null/省略)。出力: 要件ごとの充足状況・必要事実・総合判定・根拠条項。
判定ロジックは キャッシュ済み一次資料(第2条第1項・第8項・第9項)の数値・構造に対応。条文が変わればキャッシュと本ロジックの再検証が必要。
機械判定できるのは数値基準・構造のみ。『委託内容が製造委託等に当たるか』『政令指定の情報成果物/役務か』『常時使用する従業員の数の算定』等は
利用者が申告した事実(facts)を受け取るのみで、法的解釈は人間/再検証へ回す(法的解釈未確定)。
facts 例:
{"reference_date":"2026-11-24","contract_date":"2026-12-01",
 "entrustment":{"type":"製造委託","matches_definition":true,"designated_by_cabinet_order":null},
 "client":{"form":"法人","capital_yen":50000000,"employees":120,"is_state_or_art14_person":false},
 "contractor":{"form":"法人","capital_yen":8000000,"employees":20}}
"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legal_sources as L
OK, NG, UNK, LEG, NA = "充足", "不充足", "事実関係不明", "法的解釈未確定", "該当なし"
ACT = "act_331AC0000000120"

def g(d, *path):
    for k in path:
        if not isinstance(d, dict) or d.get(k) is None: return None
        d = d[k]
    return d
def req(name, status, basis, ref, need=None, confirmed=None, group="必須"):
    return {"name": name, "status": status, "basis": basis, "ref": ref, "required_fact": need, "confirmed_fact": confirmed, "group": group}

def judge(facts, cache_dir=None):
    src = L.load(ACT, cache_dir); ref_date = facts.get("reference_date")
    out = {"law": src and src["law_title"], "source_id": ACT, "reference_date": ref_date, "requirements": [], "required_facts": [], "withheld": []}
    if src is None or not ref_date:
        out.update(overall="判断保留", effective_at_reference_date="不明", asserted_applicable=False, allow_assertive_revision=False)
        out["withheld"].append("一次資料(法令キャッシュ)または基準日がない"); return out
    out["reliability"] = L.reliability(src)
    out["effective_at_reference_date"] = L.effectiveness(src, ref_date)
    cd = facts.get("contract_date")
    out["effective_at_contract_date"] = L.effectiveness(src, cd) if cd else "不明"
    out["transitional_provisions_retrieved"] = src.get("transitional_provisions_retrieved", False)
    R = out["requirements"]
    # R0: 現行性
    if out["effective_at_reference_date"] != "施行済":
        R.append(req("法令の有効性(基準日)", NG, "基準日時点で施行済でない(%s)" % out["effective_at_reference_date"], "enforcement_date"))
    else: R.append(req("法令の有効性(基準日)", OK, "施行日 %s ≤ 基準日(%s)" % (src["enforcement_date"], ref_date), "enforcement_date"))
    if cd and out["effective_at_contract_date"] != "施行済":
        R.append(req("契約日時点の適用法令", LEG, "契約日が施行日(%s)前: 旧法(下請法)の適用/経過措置の確認が必要。経過措置は未取得" % src["enforcement_date"], "附則(未取得)", "経過措置(令和七年法律第四十一号附則)"))
        out["required_facts"].append("経過措置(令和七年法律第四十一号附則)の確認")
    # R1: 委託内容
    et = g(facts, "entrustment", "type"); md = g(facts, "entrustment", "matches_definition")
    if et is None or md is None:
        R.append(req("委託内容が製造委託等に該当", UNK, "委託の類型/定義該当性の申告なし", "2-1,2-6", "委託の類型と定義該当性(業として販売/請負う製造物の部品・金型等の製造委託か 等)")); out["required_facts"].append("委託の類型と第2条第1項等の定義該当性")
    elif md is False: R.append(req("委託内容が製造委託等に該当", NG, "申告: 定義非該当(%s)" % et, "2-1,2-6", confirmed="type=%s, matches_definition=false" % et))
    else: R.append(req("委託内容が製造委託等に該当", LEG if False else OK, "申告に基づく(定義該当性自体の法的評価は再検証対象)", "2-1,2-6", confirmed="type=%s, matches_definition=true(申告)" % et))
    is_info = et in ("情報成果物作成委託", "役務提供委託")
    designated = g(facts, "entrustment", "designated_by_cabinet_order")
    if is_info:
        if designated is None:
            R.append(req("政令指定の情報成果物/役務か", LEG, "政令(平成十三年政令第五号等)の指定該当性は未判定。第8項第1/2/5号と第3/4/6号のどちらの基準かが決まらない", "2-8-1,2-8-3", "政令指定の該当性")); out["required_facts"].append("政令指定の情報成果物/役務への該当性")
        else: R.append(req("政令指定の情報成果物/役務か", OK, "申告: 指定%s" % ("あり" if designated else "なし"), "2-8-1,2-8-3", confirmed=str(designated)))
    cl, ct = facts.get("client") or {}, facts.get("contractor") or {}
    # 国等・政府契約法14条
    ex = cl.get("is_state_or_art14_person")
    if ex is None: R.append(req("委託事業者が国等/政府契約支払遅延防止法14条の者でない", UNK, "申告なし", "2-8-*", "委託事業者の属性")); out["required_facts"].append("委託事業者が国・政府契約法14条の者でないこと")
    elif ex: R.append(req("委託事業者が国等/政府契約支払遅延防止法14条の者でない", NG, "該当者は除外", "2-8-*"))
    else: R.append(req("委託事業者が国等/政府契約支払遅延防止法14条の者でない", OK, "申告", "2-8-*", confirmed="false"))
    # 規模要件: 資本金基準 / 従業員基準
    def small(p, cap_limit): # 個人 or 資本金<=limit
        if p.get("form") == "個人": return True
        c = p.get("capital_yen")
        if c is None: return None
        if c <= cap_limit: return True          # 個人でも法人でも該当(形態不明でも確定)
        return None if p.get("form") is None else False   # 上限超: 形態不明なら個人の可能性が残る(独立オラクル境界試験で発見した不備の修正)
    def capital_route():
        if cl.get("form") is None: return None, "委託事業者の形態(法人/個人)不明"
        if cl["form"] != "法人": return False, "委託事業者が法人でない(第8項各号は法人たる事業者)"
        cap = cl.get("capital_yen")
        if cap is None: return None, "委託事業者の資本金不明"
        if not is_info or designated is True:     # 第1号/第2号 (製造委託等・政令指定情報成果物/役務)
            tiers = [("2-8-1", 300_000_000, None, "2-9-1"), ("2-8-2", 10_000_000, 300_000_000, "2-9-2")]   # 2-8-1は上限なし(3億円超)。中間3で修正: 従来は上限=3億円としていたため3億円超の委託事業者が不充足になっていた
        else: tiers = [("2-8-3", 50_000_000, None, "2-9-3"), ("2-8-4", 10_000_000, 50_000_000, "2-9-4")]
        if is_info and designated is None: return None, "政令指定の該当性が未定のため資本金基準の区分(1,2号/3,4号)が決まらない"
        for item, lo, hi, citem in tiers:
            upper_ok = (hi is None) or cap <= hi
            if cap > lo and upper_ok:
                lim = {"2-8-1": 300_000_000, "2-8-2": 10_000_000, "2-8-3": 50_000_000, "2-8-4": 10_000_000}[item]
                s = small(ct, lim)
                if s is None: return None, "受託事業者の資本金/形態不明(第8項%s: 委託事業者資本金%s円は該当レンジ)" % (item, "{:,}".format(cap))
                return (True, "委託事業者%s円 > %s円、受託事業者が個人または資本金%s円以下: %s" % ("{:,}".format(cap), "{:,}".format(lo), "{:,}".format(lim), item)) if s else (False, "委託事業者は%sのレンジだが受託事業者の資本金が上限%s円超" % (item, "{:,}".format(lim)))
        return False, "委託事業者の資本金が各号の下限(資本金基準)を満たさない"
    def employee_route():
        if cl.get("form") != "法人": return (None if cl.get("form") is None else False), "委託事業者が法人でない/不明"
        e, ce = cl.get("employees"), ct.get("employees")
        if e is None or ce is None: return None, "常時使用する従業員数(委託事業者または受託事業者)不明"
        lim = 100 if (is_info and designated is False) else 300
        if is_info and designated is None: return None, "政令指定の該当性が未定のため従業員基準(100人/300人)が決まらない"
        return (e > lim and ce <= lim), "委託事業者従業員%d人(>%d人が必要)、受託事業者%d人(≤%d人が必要)" % (e, lim, ce, lim)
    cr, crb = capital_route(); er, erb = employee_route()
    R.append(req("資本金基準(第2条第8項・第9項 1〜4号)", {True: OK, False: NG, None: UNK}[cr], crb, "2-8-*/2-9-*",
                 None if cr is not None else "委託事業者・受託事業者の資本金(円)と法人/個人の別", crb if cr is not None else None, group="選択肢"))
    R.append(req("従業員基準(第2条第8項・第9項 5・6号)", {True: OK, False: NG, None: UNK}[er], erb, "2-8-5,2-8-6/2-9-5,2-9-6",
                 None if er is not None else "委託事業者・受託事業者の常時使用する従業員数", erb if er is not None else None, group="選択肢"))
    if cr is None: out["required_facts"].append("委託事業者・受託事業者の資本金・法人/個人の別")
    if er is None: out["required_facts"].append("常時使用する従業員の数(委託事業者・受託事業者)")
    scale = OK if (cr or er) else (NG if (cr is False and er is False) else UNK)
    R.append(req("規模要件(資本金基準または従業員基準のいずれか)", scale, "資本金基準=%s / 従業員基準=%s" % (cr, er), "2-8,2-9"))
    # みなし規定(第10項: 再委託)は別途
    R.append(req("みなし委託事業者(第2条第10項:支配関係+再委託)", NA if scale == OK else LEG, "規模要件を満たさない場合に限り検討。親会社等の支配関係と再委託の事実は未確認", "2-10(未キャッシュ)", None if scale == OK else "親会社等による支配関係・再委託の有無"))
    # 総合
    st = [r["status"] for r in R if r["name"] in ("法令の有効性(基準日)", "委託内容が製造委託等に該当", "委託事業者が国等/政府契約支払遅延防止法14条の者でない", "規模要件(資本金基準または従業員基準のいずれか)")]
    if NG in st: overall = "適用なし(確定できる範囲で不充足)" if (st[-1] == NG or NG in st[:3]) else "判断保留"
    elif UNK in st or any(r["status"] == LEG for r in R if r["name"] in ("契約日時点の適用法令", "政令指定の情報成果物/役務か")): overall = "判断保留(条件付き)"
    else: overall = "適用あり"
    if overall.startswith("適用なし") and st[-1] == NG:   # 規模不充足でも みなし規定の余地
        overall = "適用なし(規模要件不充足。ただしみなし規定(第10項)は事実関係未確認)"
    out["overall"] = overall; out["asserted_applicable"] = overall == "適用あり"
    out["allow_assertive_revision"] = out["asserted_applicable"] and L.can_support_firm(src)
    if not L.can_support_firm(src): out["withheld"].append("法令キャッシュが『確定』の根拠にできる信頼区分でない: " + L.reliability(src))
    if out["asserted_applicable"] and not out["transitional_provisions_retrieved"] and (cd and out["effective_at_contract_date"] != "施行済"): out["asserted_applicable"] = False
    out["mechanical_vs_interpretive"] = "数値基準・構造は機械判定。定義該当性・政令指定・従業員の算定・みなし規定は申告値の受領のみで法的解釈は未判定"
    out["required_facts"] = list(dict.fromkeys(out["required_facts"]))
    return out
if __name__ == "__main__":
    print(json.dumps(judge(json.load(open(sys.argv[1], encoding="utf-8"))), ensure_ascii=False, indent=1))
