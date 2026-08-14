# -*- coding: utf-8 -*-
"""
A股市场广度锚 (Breadth Anchor) 每日自动计算工具
================================================

样本池: 沪深300 + 中证500 + 中证1000 成分股（合并去重）
广度锚 = 收盘价站上 MA20 的家数 / 样本池有效家数

数据源: 优先 iFinD(同花顺), 不可用时降级 akshare(腾讯行情接口)

用法:
    python breadth_anchor.py                 # 跑最近一个交易日
    python breadth_anchor.py --date 2026-08-07   # 跑指定日期补数
    python breadth_anchor.py --refresh-universe  # 强制刷新成分股名单
    python breadth_anchor.py --workers 8 --source akshare   # 调并发数/数据源
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_CACHE = os.path.join(BASE_DIR, "universe_cache.json")
LOG_CSV = os.path.join(BASE_DIR, "breadth_anchor_log.csv")

INDEX_CODES = [
    ("000300", "沪深300"),
    ("000905", "中证500"),
    ("000852", "中证1000"),
]

# 最近 N 个交易日为 MA20 所需窗口（+余量）
LOOKBACK_TRADING_DAYS = 60
# 上市不足该交易日数视为次新股（从成分股名单排除）
MIN_LISTED_DAYS = 25
# MA 窗口
MA_WINDOW = 20
# 体质判定阈值
REGIME_STRONG = 60.0
REGIME_WEAK = 40.0

CACHE_TTL_DAYS = 28  # 成分股每月初刷新，给约4周有效期


# ---------------------------------------------------------------------------
# 数据源抽象：iFinD 优先，akshare 兜底
# ---------------------------------------------------------------------------
class DataSource:
    """数据源基类。子类必须实现 fetch_daily 与 fetch_universe。"""

    name = "base"

    def fetch_daily(self, code, start_date, end_date):
        """返回 DataFrame，列含 date(YYYY-MM-DD), close；无数据返回空列表。"""
        raise NotImplementedError

    def fetch_universe(self):
        """返回 {'000300': [codes...], '000905': [...], '000852': [...]}"""
        raise NotImplementedError


class IfindSource(DataSource):
    """iFinD(同花顺) 数据源。环境无 iFinDPy 时自动跳过。
    启用方式：pip install iFinDPy 并配置同花顺行情终端登录。
    注意：以下接口名为通用骨架，真实 SDK 方法名需按已装版本校准。"""

    name = "ifind"

    def __init__(self):
        import iFinDPy as ths  # 不可用则在 import 处抛异常
        self.ths = ths

    def fetch_daily(self, code, start_date, end_date):
        # iFinD 历史日线：ths.historical_data_period_quote 返回 (error_code, DataFrame)
        # 字段约定 date / close 需自行按返回结构归一化
        df = self.ths.historical_data_period_quote(
            code, "close", "", start_date, end_date, "1d", "0", "1"
        )
        return df

    def fetch_universe(self):
        out = {}
        for idx, name in INDEX_CODES:
            df = self.ths.ths_index_cons(idx)
            out[idx] = df["code"].tolist()
        return out


class AkshareSource(DataSource):
    """akshare 数据源。成分股用中证指数官网接口；日线用腾讯行情接口
    （东财接口易被限流）。"""

    name = "akshare"
    REQUEST_TIMEOUT = 15

    def __init__(self, workers=8):
        import akshare as ak
        self.ak = ak
        self.workers = workers

    def _normalize_symbol(self, code):
        """6位代码 -> 带交易所前缀（腾讯接口要求）。"""
        code = str(code).strip()
        if code.startswith(("60", "68", "90", "51", "58", "50", "56")):
            return "sh" + code
        if code.startswith(("00", "30", "15", "16", "12")):
            return "sz" + code
        if code.startswith(("43", "83", "87", "92", "82", "88")):
            return "bj" + code
        # 兜底：多数A股以 60/00/30 开头
        if code.startswith("6"):
            return "sh" + code
        return "sz" + code

    def fetch_daily(self, code, start_date, end_date):
        """返回 list of (date, close)。失败抛异常由调用方重试。"""
        sym = self._normalize_symbol(code)
        try:
            df = self.ak.stock_zh_a_hist_tx(
                symbol=sym,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
                timeout=self.REQUEST_TIMEOUT,
            )
        except Exception:
            # 部分代码腾讯接口不返回，降级到东财（失败会抛异常）
            df = self.ak.stock_zh_a_hist(
                symbol=sym,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
        if df is None or len(df) == 0:
            return []
        # 统一列名：akshare 不同接口列名不同（中文/英文）
        date_col = "date" if "date" in df.columns else "日期"
        close_col = "close" if "close" in df.columns else "收盘"
        out = []
        for _, row in df.iterrows():
            d = str(row[date_col])[:10]
            c = float(row[close_col])
            out.append((d, c))
        return out

    def fetch_universe(self):
        out = {}
        for idx, name in INDEX_CODES:
            df = self.ak.index_stock_cons_csindex(symbol=idx)
            # 成分券代码列名：不同版本可能为中文或英文
            code_col = "成分券代码" if "成分券代码" in df.columns else "code"
            if code_col not in df.columns:
                raise RuntimeError(
                    "index_stock_cons_csindex 列名异常: %s" % df.columns.tolist()
                )
            codes = [str(c).strip() for c in df[code_col].tolist()]
            out[idx] = codes
        return out


# ---------------------------------------------------------------------------
# 成分股名单：本地缓存 + 月度刷新
# ---------------------------------------------------------------------------
def load_universe(source, force_refresh=False):
    """返回 {'000300':[...], '000905':[...], '000852':[...], 'fetched_at': ISO}
    合并去重后的完整代码列表可通过 merge 得到。"""
    cached = None
    if os.path.exists(UNIVERSE_CACHE) and not force_refresh:
        try:
            with open(UNIVERSE_CACHE, "r", encoding="utf-8") as f:
                cached = json.load(f)
        except Exception:
            cached = None

    fresh_enough = False
    if cached and cached.get("fetched_at"):
        try:
            fetched = dt.datetime.fromisoformat(cached["fetched_at"])
            if (dt.datetime.now() - fetched).days <= CACHE_TTL_DAYS:
                fresh_enough = True
        except Exception:
            fresh_enough = False

    if fresh_enough:
        print("[universe] 使用本地缓存 (拉取于 %s)" % cached["fetched_at"])
        return cached

    print("[universe] 获取最新成分股名单...")
    uni = source.fetch_universe()
    uni["fetched_at"] = dt.datetime.now().isoformat(timespec="seconds")
    with open(UNIVERSE_CACHE, "w", encoding="utf-8") as f:
        json.dump(uni, f, ensure_ascii=False, indent=2)
    for idx, codes in uni.items():
        if idx != "fetched_at":
            print("  %s: %d 只" % (idx, len(codes)))
    return uni


def merge_universe(uni):
    """三指数合并去重，返回 (sorted_codes, name_map)。"""
    all_codes = []
    for idx, name in INDEX_CODES:
        all_codes.extend(uni.get(idx, []))
    return sorted(set(all_codes))


# ---------------------------------------------------------------------------
# 核心计算
# ---------------------------------------------------------------------------
def compute_ma20(closes):
    """给定最近>=20的收盘价列表（按日期升序），返回最新收盘与MA20。"""
    if len(closes) < MA_WINDOW:
        return None, None
    ma20 = sum(closes[-MA_WINDOW:]) / MA_WINDOW
    return closes[-1], ma20


def fetch_with_retry(source, code, start_date, end_date, max_retries=3):
    """拉取单只股票日线，失败重试（指数退避）。"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            rows = source.fetch_daily(code, start_date, end_date)
            return rows
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(attempt)
    raise last_err


def process_one(code, source, start_date, end_date):
    """单只股票：返回 dict 结果或分类剔除原因。"""
    try:
        rows = fetch_with_retry(source, code, start_date, end_date)
    except Exception as e:
        return {"code": code, "excluded": "error", "reason": repr(e)[:80]}

    if not rows:
        return {"code": code, "excluded": "nodata"}

    # 判断停牌：最新交易日数据必须覆盖目标日
    end = dt.date.fromisoformat(end_date[:4] + "-" + end_date[4:6] + "-"
                                + end_date[6:8])
    last_date = dt.date.fromisoformat(max(r[0] for r in rows))
    # 若最后数据早于目标日 -> 停牌
    if last_date < end:
        return {"code": code, "excluded": "suspended"}

    # 有效K线数 < 25 交易日：次新股（上市不足）或数据不足
    if len(rows) < MIN_LISTED_DAYS:
        return {"code": code, "excluded": "new"}

    closes = [r[1] for r in rows]
    closes = closes[-LOOKBACK_TRADING_DAYS:]  # 只看最近60个交易日
    if len(closes) < MA_WINDOW:
        return {"code": code, "excluded": "nodata"}

    latest, ma20 = compute_ma20(closes)
    if latest is None:
        return {"code": code, "excluded": "nodata"}
    return {
        "code": code,
        "excluded": None,
        "latest": latest,
        "ma20": ma20,
        "above": latest > ma20,
        "ndays": len(closes),
    }


def run_day(source, target_date, workers=8):
    """跑指定交易日，返回结果 dict。"""
    # 目标日往前推约 LOOKBACK+ 自然日（含周末，余量充足）
    end_date = target_date.strftime("%Y%m%d")
    start = target_date - dt.timedelta(days=LOOKBACK_TRADING_DAYS + 30)
    start_date = start.strftime("%Y%m%d")

    uni = load_universe(source)
    codes = merge_universe(uni)
    print("[universe] 合并去重后共 %d 只" % len(codes))

    # 并发拉取
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(process_one, c, source, start_date, end_date): c
            for c in codes
        }
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"code": futs[fut], "excluded": "error",
                                "reason": repr(e)[:80]})
            if done % 200 == 0:
                print("[fetch] %d/%d" % (done, len(codes)))

    # 汇总
    ex_count = {"suspended": 0, "new": 0, "nodata": 0, "error": 0}
    above = 0
    valid = 0
    for r in results:
        if r["excluded"]:
            ex_count[r["excluded"]] = ex_count.get(r["excluded"], 0) + 1
        else:
            valid += 1
            if r["above"]:
                above += 1

    excluded_total = sum(ex_count.values())
    pool = len(codes) - excluded_total
    breadth = (above / pool * 100.0) if pool else 0.0

    # 5日前比较
    change_5d, prev_pct = get_change_5d(target_date, breadth)

    # 体质判定
    if breadth > REGIME_STRONG:
        regime = "强市（多数股票在趋势中）"
    elif breadth >= REGIME_WEAK:
        regime = "结构市（只有主线有机会）"
    else:
        regime = "弱市（谨慎）"

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "pool_size": pool,
        "excluded_total": excluded_total,
        "excluded_detail": ex_count,
        "above_ma20": above,
        "breadth_pct": breadth,
        "change_5d": change_5d,
        "prev_5d_pct": prev_pct,
        "regime": regime,
        "total_codes": len(codes),
    }


def get_change_5d(target_date, breadth):
    """从日志读取约5个交易日前的广度锚。返回 (delta_pct, prev_pct)。"""
    prev_pct = None
    if os.path.exists(LOG_CSV):
        rows = []
        with open(LOG_CSV, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rows.append((dt.date.fromisoformat(row["date"]),
                                 float(row["breadth_pct"])))
                except Exception:
                    continue
        rows.sort()
        # 找 target_date 之前最近的一条
        prev = None
        for d, p in rows:
            if d < target_date:
                prev = (d, p)
            else:
                break
        if prev:
            prev_pct = prev[1]
    if prev_pct is None:
        return None, None
    return breadth - prev_pct, prev_pct


def append_log(res):
    header = ["date", "pool_size", "excluded", "above_ma20",
              "breadth_pct", "change_5d", "regime"]
    file_exists = os.path.exists(LOG_CSV)
    # 同日已存在则跳过，避免重复追加
    if file_exists and os.path.getsize(LOG_CSV) > 0:
        with open(LOG_CSV, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("date") == res["date"]:
                    print("[log] 当日 %s 已记录，跳过追加" % res["date"])
                    return
    with open(LOG_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists or os.path.getsize(LOG_CSV) == 0:
            writer.writeheader()
        writer.writerow({
            "date": res["date"],
            "pool_size": res["pool_size"],
            "excluded": res["excluded_total"],
            "above_ma20": res["above_ma20"],
            "breadth_pct": "%.1f" % res["breadth_pct"],
            "change_5d": "%.1f" % res["change_5d"]
                        if res["change_5d"] is not None else "",
            "regime": res["regime"],
        })


def print_report(res):
    ex = res["excluded_detail"]
    line = "日期: %s\n" % res["date"]
    line += "样本池: %d只（剔除%d只：停牌%d/次新%d/无数据%d/错误%d）\n" % (
        res["pool_size"], res["excluded_total"],
        ex.get("suspended", 0), ex.get("new", 0),
        ex.get("nodata", 0), ex.get("error", 0))
    line += "站上MA20: %d只\n" % res["above_ma20"]
    if res["change_5d"] is not None:
        line += "广度锚: %.1f%%（5日前: %.1f%%，变化: %+.1fpct）\n" % (
            res["breadth_pct"], res["prev_5d_pct"], res["change_5d"])
    else:
        line += "广度锚: %.1f%%（5日前: 无历史）\n" % res["breadth_pct"]
    line += "体质判定: %s\n" % res["regime"]
    print(line)


def resolve_target_date(date_str):
    """解析 --date。不传则取最近一个交易日（akshare 交易日历）。"""
    if date_str:
        return dt.date.fromisoformat(date_str)
    import akshare as ak
    cal = ak.tool_trade_date_hist_sina()
    dates = sorted(dt.date.fromisoformat(str(d)) for d in cal["trade_date"])
    today = dt.date.today()
    past = [d for d in dates if d <= today]
    if not past:
        raise RuntimeError("交易日历无今天及以前的数据")
    return past[-1]


def main():
    ap = argparse.ArgumentParser(description="A股市场广度锚计算工具")
    ap.add_argument("--date", help="目标交易日 YYYY-MM-DD，默认最近交易日")
    ap.add_argument("--refresh-universe", action="store_true",
                    help="强制刷新成分股名单")
    ap.add_argument("--workers", type=int, default=8, help="并发线程数")
    ap.add_argument("--source", default="auto",
                    choices=["auto", "ifind", "akshare"],
                    help="数据源：auto 自动检测 iFinD，不可用则用 akshare")
    args = ap.parse_args()

    # 数据源选择
    source = None
    if args.source in ("auto", "ifind"):
        try:
            source = IfindSource()
            print("[source] 使用 iFinD(同花顺)")
        except Exception as e:
            if args.source == "ifind":
                print("[source] iFinD 不可用: %s" % repr(e)[:100])
                sys.exit(1)
            source = None
    if source is None:
        source = AkshareSource(workers=args.workers)
        print("[source] iFinD 不可用，降级使用 akshare")

    target = resolve_target_date(args.date)
    print("[date] 目标交易日: %s" % target)

    res = run_day(source, target, workers=args.workers)
    print_report(res)
    append_log(res)
    print("[log] 已追加至 %s" % LOG_CSV)


if __name__ == "__main__":
    main()
