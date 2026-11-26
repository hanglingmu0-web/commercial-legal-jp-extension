# -*- coding: utf-8 -*-
"""取適法(act_331AC0000000120)2条8項・9項に基づく適用要件判定(製造委託のみ)。独立実装。

条文(AI転記・公式原文との照合未了)の文言のみを根拠とする。
判定方式: 条文どおりの「確定値」判定 crisp() を書き、None(不明)は取り得る値で全補完して
crisp() を評価する(超評価)。全補完で真→適用あり、全補完で偽→適用なし、割れる→判断保留。
これにより「不明を推測で補わず、確定できる場合のみ判定」「どの経路でも該当し得ないなら適用なし」を満たす。
"""
import itertools
import json
import os

_DEFAULT_ENFORCEMENT = "2026-01-01"
_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                      "legal_cache", "act_331AC0000000120.json")


def _enforcement_date():
    try:
        with open(_CACHE, encoding="utf-8") as f:
            return json.load(f).get("enforcement_date") or _DEFAULT_ENFORCEMENT
    except Exception:
        return _DEFAULT_ENFORCEMENT


# 金額・人数の閾値(条文の数字)
_CAP_3OKU = 300_000_000   # 2-8-1 / 2-9-1: 三億円
_CAP_1000MAN = 10_000_000  # 2-8-2 / 2-9-2: 千万円
_EMP_300 = 300             # 2-8-5 / 2-9-5: 三百人


def crisp(entr, kform, kcap, kemp, art14, cform, ccap, cemp):
    """全項目が確定している場合の判定(True=法の適用あり)。k=委託事業者(client), c=受託側(contractor)。"""
    # 2-1: 製造委託の定義に該当しなければ対象外(本実装は製造委託のみ対象)。
    if not entr:
        return False

    # 以下 2-8-3, 2-8-4, 2-8-6 / 2-9-3, 2-9-4, 2-9-6 は情報成果物作成委託・役務提供委託に係る
    # 経路であり、製造委託には適用されないため評価しない。
    # 2-6: 本課題は製造委託のみを対象とするので、製造委託等のうち製造委託以外は扱わない。

    # 2-8-1/2/5 括弧書: 「政府契約の支払遅延防止等に関する法律第十四条に規定する者を除く」
    # 2-8-5 括弧書: 「国及び…第十四条に規定する者を除く」(is_state_or_art14_person が国と14条の者を兼ねる)
    if art14:
        return False

    k_corp = (kform == "法人")  # 2-8-1/2/5: いずれも「法人たる事業者」であることが委託事業者側の要件(個人は委託事業者にならない)

    # 2-8-1: 資本金>三億円の法人 → 相手方は 2-9-1: 個人 又は 資本金<=三億円の法人
    k1 = k_corp and kcap > _CAP_3OKU
    c1 = (cform == "個人") or (cform == "法人" and ccap <= _CAP_3OKU)  # 2-9-1: 個人は資本金を問わない
    r1 = k1 and c1

    # 2-8-2: 千万円<資本金<=三億円の法人 → 相手方は 2-9-2: 個人 又は 資本金<=千万円の法人
    k2 = k_corp and _CAP_1000MAN < kcap <= _CAP_3OKU
    c2 = (cform == "個人") or (cform == "法人" and ccap <= _CAP_1000MAN)  # 2-9-2
    r2 = k2 and c2

    # 2-8-5: 常時使用従業員>300の法人 → 相手方は 2-9-5: 従業員<=300の個人 又は 法人
    # (個人にも従業員数要件が及ぶ。資本金は問わない)
    k5 = k_corp and kemp > _EMP_300
    c5 = cemp <= _EMP_300
    # 2-8-5 括弧書(第1号該当者が2-9-1該当者に、又は第2号該当者が2-9-2該当者に委託する場合を除く)
    # = 資本金基準の経路(r1またはr2)が成立する組合せは5号経路から除外。
    excluded_5 = r1 or r2
    r5 = k5 and c5 and not excluded_5

    # 2-8 各号「いずれかに該当」/ 2-9 各号「いずれかに該当」→ 経路の論理和。
    # 注: 2-8-5括弧書により r5 = A5 and not(r1 or r2) だが、r1 or r2 or r5 = r1 or r2 or A5 であり、
    # 括弧書は最終的な「適用あり/なし」の結論には影響しない(経路の帰属のみ変わる)。
    return r1 or r2 or r5


_CAPS = [0, 1, _CAP_1000MAN, _CAP_1000MAN + 1, _CAP_3OKU, _CAP_3OKU + 1]
_EMPS = [0, _EMP_300, _EMP_300 + 1]


def _cands(val, universe):
    return [val] if val is not None else universe


def judge(facts):
    ref = facts.get("reference_date")
    if not ref:
        return "判断保留"  # 基準日不明では施行前後を確定できない
    if str(ref) < _enforcement_date():  # ISO形式の文字列比較
        return "未施行"

    e = facts.get("entrustment") or {}
    cl = facts.get("client") or {}
    ct = facts.get("contractor") or {}

    results = set()
    for entr, art14, kform, cform in itertools.product(
            _cands(e.get("matches_definition"), [True, False]),
            _cands(cl.get("is_state_or_art14_person"), [True, False]),
            _cands(cl.get("form"), ["法人", "個人"]),
            _cands(ct.get("form"), ["法人", "個人"])):
        # 個人の資本金は条文上無関係(2-9-1/2: 「個人又は…法人」)。個人なら資本金の不明は影響しない。
        kcaps = [0] if kform == "個人" else _cands(cl.get("capital_yen"), _CAPS)
        ccaps = [0] if cform == "個人" else _cands(ct.get("capital_yen"), _CAPS)
        for kcap, ccap, kemp, cemp in itertools.product(
                kcaps, ccaps,
                _cands(cl.get("employees"), _EMPS), _cands(ct.get("employees"), _EMPS)):
            results.add(bool(crisp(entr, kform, kcap, kemp, art14, cform, ccap, cemp)))
            if len(results) > 1:
                return "判断保留"
    return "適用あり" if results == {True} else "適用なし"
