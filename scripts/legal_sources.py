"""検証済み法令キャッシュ: 保存・現行性判定・引用照合。
キャッシュは「取得経路」「原文性(verbatim)」「取得日時」を必ず持つ。古い/要約取得/未取得の資料を現行法令として無条件に使わない。
"""
import os, json, re, unicodedata, datetime, hashlib, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.environ.get("LEGAL_CACHE_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "legal_cache")
MAX_AGE_DAYS = 30   # 法令キャッシュの有効期間(超過は要再取得)

def load(source_id, cache_dir=None):
    p = os.path.join(cache_dir or CACHE_DIR, source_id + ".json")
    if not os.path.isfile(p): return None
    return json.load(open(p, encoding="utf-8"))
def all_sources(cache_dir=None):
    d = cache_dir or CACHE_DIR
    return {f[:-5]: json.load(open(os.path.join(d, f), encoding="utf-8")) for f in sorted(os.listdir(d)) if f.endswith(".json")}
def norm(s): return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))
def d(s): return datetime.date.fromisoformat(s[:10])

ACQ_MACHINE, ACQ_MODEL, ACQ_SUMMARY, ACQ_SERVICE = "machine_fetch", "model_transcription", "summary", "service_excerpt"
def acquisition(src):
    if src is None: return None
    if src.get("acquisition"): return src["acquisition"]
    if src.get("transcribed_by_model") or src.get("retrieval_route", "").startswith("組込みブラウザ"): return ACQ_MODEL   # 旧形式キャッシュの移行
    if "要約" in src.get("retrieval_route", ""): return ACQ_SUMMARY
    if src.get("kind") == "Guidance": return ACQ_SERVICE
    return ACQ_MACHINE if src.get("verbatim") else ACQ_SUMMARY

def trace(src, cache_dir=None):
    """キャッシュ→取得原文の追跡: 原文ファイルのSHA-256再計算と、原文からの条項再生成結果とキャッシュの一致を検査。"""
    if src is None: return {"ok": False, "reason": "資料なし"}
    rp = src.get("raw_path")
    if not rp: return {"ok": False, "reason": "取得原文(raw)なし"}
    full = os.path.join(os.path.dirname(cache_dir or CACHE_DIR), rp) if not os.path.isabs(rp) else rp
    if not os.path.isfile(full): return {"ok": False, "reason": "取得原文ファイルが存在しない: " + rp}
    raw = open(full, "rb").read()
    if hashlib.sha256(raw).hexdigest() != src.get("raw_sha256"): return {"ok": False, "reason": "取得原文のSHA-256が記録と不一致(改変の疑い)"}
    import ingest_egov as I
    prov = I.flatten(json.loads(raw.decode("utf-8"))["law_full_text"])
    if prov != src.get("provisions"): return {"ok": False, "reason": "原文から再生成した条項とキャッシュが不一致"}
    return {"ok": True, "reason": "原文SHA-256一致・条項再生成一致", "raw_text": norm("".join(_strings(json.loads(raw.decode("utf-8"))["law_full_text"])))}
def _strings(n):
    if isinstance(n, str): yield n
    elif isinstance(n, dict):
        for c in n.get("children", []): yield from _strings(c)

def reliability(src, cache_dir=None):
    """信頼区分。『一次・原文(機械取得)』のみが法的判断の『確定』根拠になり得る。AIの転記・要約は一次資料として扱わない。"""
    if src is None: return "一次資料取得不能(未取得)"
    if src.get("retrieval_route") == "FAILED": return "一次資料取得不能(取得失敗)"
    a = acquisition(src)
    if a == ACQ_MODEL: return "一次資料取得不能(AI転記のみ。機械取得の原文なし)"
    if a == ACQ_SUMMARY: return "二次/要約(原文ではない)"
    if a == ACQ_SERVICE: return "行政解説(二次資料)"
    if src.get("test_fixture") and not os.environ.get("LEGAL_ALLOW_FIXTURE"): return "試験用フィクスチャ(本番使用不可)"
    t = trace(src, cache_dir)
    if not t["ok"]: return "一次・原文だが追跡不能(%s)" % t["reason"]
    return "一次・原文(機械取得・追跡検証済)" + ("[試験用]" if src.get("test_fixture") else "")

def can_support_firm(src, cache_dir=None):
    return reliability(src, cache_dir).startswith("一次・原文(機械取得・追跡検証済)")

def currency(src, ref_date, event_date=None, today=None, tier="standard", cache_dir=None):
    """現行性の多軸評価。取得日・公布日・施行日・改正履歴・経過措置・基準日・対象取引時期・最終確認日を区別して返す。"""
    MAXAGE = {"light": 30, "standard": 7, "high": 1}[tier]
    today = today or ref_date
    r = {"retrieved_at": src.get("retrieved_at"), "promulgation_date": src.get("promulgation_date"), "enforcement_date": src.get("enforcement_date"),
         "scheduled_enforcement_date": src.get("scheduled_enforcement_date"), "amendment_history_retrieved": bool(src.get("amendment_history_retrieved")),
         "transitional_provisions_retrieved": bool(src.get("transitional_provisions_retrieved")), "reference_date": ref_date, "event_date": event_date,
         "last_verified_at": src.get("last_verified_at") or src.get("retrieved_at"), "effective_at_reference_date": effectiveness(src, ref_date),
         "effective_at_event_date": effectiveness(src, event_date) if event_date else "不明", "needs_refresh": [], "caveats": []}
    age = (d(today) - d(r["last_verified_at"])).days
    r["age_days"] = age
    if age < 0: r["needs_refresh"].append("最終確認日が基準日より後(日付不整合)")
    if age > MAXAGE: r["needs_refresh"].append("最終現行性確認から%d日経過(%sレベルの許容%d日)" % (age, tier, MAXAGE))
    sched = src.get("scheduled_enforcement_date")
    if sched and d(sched) <= d(ref_date): r["needs_refresh"].append("取得後に施行予定の改正(施行%s)が基準日までに到来している可能性" % sched)
    if sched and d(sched) > d(ref_date) and (d(sched) - d(ref_date)).days <= 90: r["caveats"].append("基準日から90日以内に施行予定の改正あり(%s)" % sched)
    if not r["amendment_history_retrieved"]: r["caveats"].append("改正履歴(過去の改正経緯)は未取得")
    if event_date and d(event_date) < d(src["enforcement_date"] or "1900-01-01") and not r["transitional_provisions_retrieved"]:
        r["needs_refresh"].append("対象取引時期が施行日(%s)より前で、経過措置(附則)が未取得: 旧法/新法いずれの適用か確定不能" % src.get("enforcement_date"))
    if event_date is None: r["caveats"].append("対象契約・取引の実施時期が未指定: 経過措置の影響を判定不能")
    r["transitional_impact"] = ("経過措置の影響は不明(未取得)" if not r["transitional_provisions_retrieved"] else "経過措置を取得済")
    r["current_confirmed"] = not r["needs_refresh"] and can_support_firm(src, cache_dir)
    return r

def effectiveness(src, ref_date):
    """基準日時点の有効性。status: 施行済(現行)/未施行/廃止/不明"""
    if src is not None and src.get("kind") == "Guidance": return "対象外(解説資料)"
    if src is None or not src.get("enforcement_date"): return "不明"
    if src.get("repeal_status") == "Repeal" and src.get("repeal_date") and d(src["repeal_date"]) <= d(ref_date): return "廃止"
    if d(src["enforcement_date"]) > d(ref_date): return "未施行"
    return "施行済"

def get_text(src, ref): return (src.get("provisions") or {}).get(ref)

def verify_quote(src, ref, quote, cache_dir=None):
    """引用文が当該資料・当該条項の原文に含まれるか。MATCH / NO_MATCH / REF_MISSING / NOT_VERBATIM"""
    if src is None: return "SOURCE_MISSING"
    t = get_text(src, ref)
    if t is None: return "REF_MISSING"
    if not src.get("verbatim"): return "NOT_VERBATIM"
    if acquisition(src) in (ACQ_MODEL,): return "MATCH_ON_TRANSCRIPT" if norm(quote) and norm(quote) in norm(t) else "NO_MATCH"   # 転記との照合のみ(取得原文との照合ではない)
    if not (norm(quote) and norm(quote) in norm(t)): return "NO_MATCH"
    tr = trace(src, cache_dir)
    if tr["ok"] and norm(quote) not in tr["raw_text"]: return "NO_MATCH_RAW"
    return "MATCH" if tr["ok"] else "TRACE_FAIL"

KAN = {"〇":0,"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
def kansuji_decimal(s):
    """『十四・六』→14.6, 『三百』→300 等(百/十/小数点のみ対応)。"""
    m = re.fullmatch(r"([〇一二三四五六七八九十百]+)(?:・([〇一二三四五六七八九]+))?", s)
    if not m: return None
    def toint(x):
        total, cur = 0, 0
        for ch in x:
            if ch == "百": total += (cur or 1) * 100; cur = 0
            elif ch == "十": total += (cur or 1) * 10; cur = 0
            else: cur = cur * 1 + KAN[ch] if False else KAN[ch]
        return total + cur
    v = toint(m.group(1))
    if m.group(2): v = float(str(v) + "." + "".join(str(KAN[c]) for c in m.group(2)))
    return v
def rate_from_text(text):
    m = re.search(r"年([〇一二三四五六七八九十百・]+)パーセント", text or "")
    return kansuji_decimal(m.group(1)) if m else None
