"""
大盘环境判断模块
===============
规则：用指数20日均线客观量化，杜绝主观感觉。

大盘状态      判断条件                   仓位上限
上涨市       指数 > MA20，且MA20向上     7-10成
震荡市       指数围绕MA20缠绕，MA20走平  3-5成
下跌市       指数 < MA20，且MA20向下     0-1成
"""

from datetime import datetime
# avoid relative import failures
import sys, os
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
import config
from data_fetcher import get_index_kline, get_market_overview


def _compute_ma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _ma_slope(closes, period=5):
    if len(closes) < period + 5:
        return 0
    ma_now = _compute_ma(closes, period)
    ma_before = _compute_ma(closes[:-5], period)
    if ma_now is None or ma_before is None or ma_before == 0:
        return 0
    return (ma_now - ma_before) / ma_before * 100


def analyze_market(index_code=config.INDEX_CODE, days=65):
    klines = get_index_kline(index_code, days)

    # 如果K线数据不足或质量差（SSE指数应~3000点），fallback到market_overview
    if not klines or len(klines) < 25:
        return _fallback_market_state()

    closes = [k["close"] for k in klines]
    # 验证数据质量：SSE指数close应在200以上（股票000001约10元就被排除了）
    avg_close = sum(closes) / len(closes) if closes else 0
    if avg_close < 200:
        return _fallback_market_state()

    latest_price = closes[-1] if closes else 0
    ma20 = _compute_ma(closes, 20)
    ma_slope_val = _ma_slope(closes, 20)

    if ma20 is None:
        return _fallback_market_state()

    above_ma20 = latest_price > ma20
    state = config.MARKET_RANGE
    reason_parts = []
    position_limit = config.POSITION_LIMITS[config.MARKET_RANGE]

    if above_ma20 and ma_slope_val > 0.5:
        state = config.MARKET_BULL
        reason_parts.append(f"指数{latest_price:.0f} > MA20{ma20:.0f}，MA20向上({ma_slope_val:+.2f}%)")
        position_limit = config.POSITION_LIMITS[config.MARKET_BULL]
    elif not above_ma20 and ma_slope_val < -0.5:
        state = config.MARKET_BEAR
        reason_parts.append(f"指数{latest_price:.0f} < MA20{ma20:.0f}，MA20向下({ma_slope_val:+.2f}%)")
        position_limit = config.POSITION_LIMITS[config.MARKET_BEAR]
    else:
        wrap_type = "上方运行" if above_ma20 else "下方运行"
        reason_parts.append(f"指数{latest_price:.0f}围绕MA20{ma20:.0f}缠绕({wrap_type}，斜率{ma_slope_val:+.2f}%)")
        position_limit = config.POSITION_LIMITS[config.MARKET_RANGE]

    turnover = klines[-1].get("amount", 0) if klines else 0

    return {
        "index_code": index_code,
        "index_name": config.INDEX_ALTERNATIVES.get(index_code, index_code),
        "latest_price": round(latest_price, 2),
        "ma20": round(ma20, 2) if ma20 else None,
        "ma20_slope_pct": round(ma_slope_val, 2),
        "above_ma20": above_ma20,
        "state": state,
        "position_limit": position_limit,
        "position_limit_text": f"{position_limit*10:.0f}成",
        "turnover_yi": round(turnover / 1e8, 1) if turnover else 0,
        "reason": "，".join(reason_parts),
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _fallback_market_state():
    """当指数K线不可用时(000001被解析为平安银行)，用market_overview涨跌比估算"""
    mo = get_market_overview()
    rise = mo.get("rise_count", 0) or 0
    fall = mo.get("fall_count", 0) or 0
    total = rise + fall
    ratio = rise / max(total, 1)
    temp = mo.get("market_temperature", 50) or 50

    if ratio > 0.6 and temp > 60:
        state = config.MARKET_BULL
        pos = config.POSITION_LIMITS[config.MARKET_BULL]
        reason = f"市场普涨(涨跌比{ratio*100:.0f}%/{100-ratio*100:.0f}%)，温度{temp:.0f}，近似上涨市"
    elif ratio < 0.4 or temp < 30:
        state = config.MARKET_BEAR
        pos = config.POSITION_LIMITS[config.MARKET_BEAR]
        reason = f"市场普跌(涨跌比{ratio*100:.0f}%)，温度{temp:.0f}，近似下跌市"
    else:
        state = config.MARKET_RANGE
        pos = config.POSITION_LIMITS[config.MARKET_RANGE]
        reason = f"涨跌均衡(涨跌比{ratio*100:.0f}%)，温度{temp:.0f}，近似震荡市"

    return {
        "index_code": config.INDEX_CODE,
        "index_name": config.INDEX_ALTERNATIVES.get(config.INDEX_CODE),
        "latest_price": None,
        "ma20": None,
        "ma20_slope_pct": 0,
        "above_ma20": None,
        "state": state,
        "position_limit": pos,
        "position_limit_text": f"{pos*10:.0f}成",
        "turnover_yi": mo.get("amount_yi", "--") if mo else "--",
        "reason": reason + " (指数K线不可用，用涨跌比替代)",
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _default_state():
    return {
        "index_code": config.INDEX_CODE,
        "index_name": config.INDEX_ALTERNATIVES.get(config.INDEX_CODE),
        "latest_price": 0,
        "ma20": None,
        "ma20_slope_pct": 0,
        "above_ma20": False,
        "state": config.MARKET_RANGE,
        "position_limit": config.POSITION_LIMITS[config.MARKET_RANGE],
        "position_limit_text": f"{config.POSITION_LIMITS[config.MARKET_RANGE]*10:.0f}成",
        "turnover_yi": 0,
        "reason": "数据不足，默认震荡市",
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
