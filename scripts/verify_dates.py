#!/usr/bin/env python3
"""日付・曜日・遅延損害金の決定論的検算。
  verify_dates.py weekday 2026-11-24
  verify_dates.py scan レポート.txt      (「2026年11月24日(火)」「令和8年11月24日（火）」形式の曜日整合を検査)
  verify_dates.py delay 金額 年率% 日数 [--basis 365|366]   (単純計算の遅延損害金。率の法的根拠は別途要確認)
  verify_dates.py addmonths 2026-11-24 12
営業日計算は休日定義が契約ごとに異なるため、休日リストファイルを --holidays で与えた場合のみ実行する。
"""
import sys, re, datetime, argparse, calendar
W = "月火水木金土日"
def wd(d): return W[d.weekday()]
def parse_era(s):
    return int(s) + 2018   # 令和
PAT = re.compile(r"(令和\s*(\d+|元)|(\d{4}))\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[（(]\s*([月火水木金土日])\s*(?:曜日)?\s*[）)]")
def scan(text):
    bad, n = [], 0
    for m in PAT.finditer(text):
        n += 1
        y = (parse_era(1 if m.group(2) == "元" else m.group(2)) if m.group(2) else int(m.group(3)))
        try: d = datetime.date(y, int(m.group(4)), int(m.group(5)))
        except ValueError: bad.append((m.group(0), "存在しない日付")); continue
        if wd(d) != m.group(6): bad.append((m.group(0), "曜日不一致: 正しくは" + wd(d)))
    return n, bad
def addmonths(d, k):
    m = d.month - 1 + k; y = d.year + m // 12; m = m % 12 + 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))
def business_days(start, end, holidays):
    d, n = start, 0
    while d < end:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5 and d not in holidays: n += 1
    return n
if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(2)
    if a[0] == "weekday":
        d = datetime.date.fromisoformat(a[1]); print(d, wd(d))
    elif a[0] == "scan":
        n, bad = scan(open(a[1], encoding="utf-8").read())
        for b in bad: print("NG:", *b)
        print("checked=%d" % n, "RESULT:", "FAIL" if bad else "PASS"); sys.exit(1 if bad else 0)
    elif a[0] == "delay":
        amt, rate, days = float(a[1]), float(a[2]), int(a[3]); basis = int(a[a.index("--basis")+1]) if "--basis" in a else 365
        print("%.0f円 (元本%s × 年率%s%% × %d日 / %d日, 円未満切捨て)" % (int(amt*rate/100*days/basis), a[1], a[2], days, basis))
    elif a[0] == "addmonths":
        print(addmonths(datetime.date.fromisoformat(a[1]), int(a[2])))
