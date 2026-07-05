"""
买卖点操作模块
=============
只做两种低吸买点，一个终极卖点。

买点一：启动买点（强势股浅回调）
- 条件：股价突破历史新高或关键平台后，首次缩量回踩 5日或10日均线
- 信号：K线为缩量小阳线、十字星或长下影线
- 仓位：3成
- 止损：买入当天最低价或 10日均线下方-3%

买点二：中继买点（中期趋势标准回调）
- 条件：股价经历一波 30%以上上涨后，第一次缩量回踩 20日或30日均线
- 信号：成交量极度萎缩，K线止跌企稳
- 仓位：加仓4成，总仓位控制在7成以内
- 止损：20日均线下方-3%

终极卖点：生命线破位
- 条件：股价放量有效跌破 20日均线，或多次回踩后无力反弹最终跌破
- 动作：无条件全部清仓

核心设计原则：
- "强势观察区" = 股价在MA20上方，但尚未触发买入信号
- "符合买点区" = 股价回踩到关键均线 + 缩量企稳 + 均线趋势向上
"""

from datetime import datetime
# avoid relative import failures
import sys, os
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
import config
from data_fetcher import get_stock_kline


def _compute_ma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _ma_trend_up(closes, period, lookback=5):
    if len(closes) < period + lookback:
        return True
    ma_now = _compute_ma(closes, period)
    ma_before = _compute_ma(closes[:-lookback], period)
    if ma_now is None or ma_before is None:
        return True
    return ma_now > ma_before


def _volume_shrink_ratio(klines, lookback=5):
    if len(klines) < lookback + 1:
        return 1.0
    volumes = [k.get("volume", 0) or 0 for k in klines]
    if not volumes:
        return 1.0
    cur_vol = volumes[-1]
    avg_vol = sum(volumes[-(lookback+1):-1]) / lookback
    if avg_vol == 0:
        return 1.0
    return cur_vol / avg_vol


def _candle_pattern(klines):
    if len(klines) < 1:
        return "未知"
    k = klines[-1]
    open_p = k.get("open", 0)
    close = k.get("close", 0)
    high = k.get("high", 0)
    low = k.get("low", 0)
    if open_p == 0 or close == 0:
        return "未知"

    body = abs(close - open_p)
    upper_shadow = high - max(open_p, close)
    lower_shadow = min(open_p, close) - low
    total_range = high - low

    if total_range == 0:
        return "平盘"

    pct_chg = (close - open_p) / open_p * 100

    if body < total_range * 0.15:
        return "十字星"
    if lower_shadow > body * 2 and upper_shadow < body * 0.5:
        return "长下影"
    if 0 < pct_chg <= 2 and body < total_range * 0.4:
        return "小阳线"
    if -2 <= pct_chg < 0 and body < total_range * 0.4:
        return "小阴线"

    return "普通"


def _recent_peak(klines, lookback=30):
    if len(klines) < lookback:
        lookback = len(klines)
    highs = [k.get("high", 0) for k in klines[-lookback:]]
    return max(highs)


def _total_gain(klines, lookback=20):
    if len(klines) < lookback:
        lookback = len(klines)
    closes = [k.get("close", 0) for k in klines[-lookback:]]
    if len(closes) < 2 or closes[0] == 0:
        return 0
    return (closes[-1] - closes[0]) / closes[0]


def check_launch_buy(code, name, klines=None):
    if klines is None:
        klines = get_stock_kline(code, 65)
    if not klines or len(klines) < 15:
        return _neutral_signal(code, name)

    closes = [k["close"] for k in klines]
    latest_price = closes[-1]

    ma5 = _compute_ma(closes, 5)
    ma13 = _compute_ma(closes, 13)
    ma20 = _compute_ma(closes, 20)

    if None in (ma5, ma13, ma20):
        return _neutral_signal(code, name)

    above_ma13 = latest_price >= ma13 * 0.99
    above_ma20 = latest_price >= ma20 * 0.99
    ma13_trend_up = _ma_trend_up(closes, 13)
    ma20_trend_up = _ma_trend_up(closes, 20)

    if not (above_ma20 and ma20_trend_up):
        return _neutral_signal(code, name, zone="观察区",
                               msg="股价在MA20下方或MA20向下，不满足启动条件")

    vol_ratio = _volume_shrink_ratio(klines)
    candle = _candle_pattern(klines)

    peak_30 = _recent_peak(klines, 30)
    is_near_peak = latest_price >= peak_30 * 0.92 if peak_30 > 0 else True
    is_new_high = latest_price >= peak_30 * 0.995 if peak_30 > 0 else False

    hit_ma5 = abs(latest_price - ma5) / ma5 < 0.015 if ma5 > 0 else False
    hit_ma13 = abs(latest_price - ma13) / ma13 < 0.015 if ma13 > 0 else False

    volume_ok = vol_ratio <= config.LAUNCH_VOLUME_SHRINK
    candle_ok = candle in config.LAUNCH_CANDLE_PATTERNS
    hit_ma = hit_ma5 or hit_ma13

    buy_signal = hit_ma and volume_ok and (candle_ok or is_new_high)

    if buy_signal:
        stop_loss = round(min(ma13 * (1 - config.STOP_LOSS_MA_BELOW_PCT),
                              latest_price * 0.97), 2)
        return {
            "code": code,
            "name": name,
            "signal_type": "启动买点",
            "zone": "符合买点区",
            "triggered": True,
            "price": round(latest_price, 2),
            "ma5": round(ma5, 2),
            "ma13": round(ma13, 2),
            "ma20": round(ma20, 2),
            "volume_ratio": round(vol_ratio, 2),
            "candle_pattern": candle,
            "hit_ma5": hit_ma5,
            "hit_ma13": hit_ma13,
            "stop_loss": stop_loss,
            "stop_loss_pct": f"{config.STOP_LOSS_MA_BELOW_PCT*100:.0f}%",
            "suggested_position": f"{config.INITIAL_POSITION_RATIO*100:.0f}%",
            "msg": f"{name}缩量回踩MA{'5' if hit_ma5 else '13'}线({candle})，触发启动买点",
        }

    is_observing = above_ma20 and ma20_trend_up
    if is_observing:
        return _neutral_signal(code, name, zone="强势观察区",
                               msg=f"{name}在MA20上方强势运行，但未触发买点(量比{vol_ratio:.1f}/{candle})")

    return _neutral_signal(code, name, zone="观察区",
                           msg=f"{name}未满足启动条件")


def check_relay_buy(code, name, klines=None):
    if klines is None:
        klines = get_stock_kline(code, 80)
    if not klines or len(klines) < 35:
        return _neutral_signal(code, name)

    closes = [k["close"] for k in klines]
    latest_price = closes[-1]

    ma20 = _compute_ma(closes, 20)
    ma30 = _compute_ma(closes, 30)
    ma60 = _compute_ma(closes, 60)

    if None in (ma20, ma30):
        return _neutral_signal(code, name)

    gain_30d = _total_gain(klines, 30)
    gain_60d = _total_gain(klines, 60)
    gain_since_last_peak = max(gain_30d, gain_60d)

    above_ma20 = latest_price >= ma20 * 0.99
    ma20_trend_up = _ma_trend_up(closes, 20)
    ma30_trend_up = True if ma30 is None else _ma_trend_up(closes, 30)

    if not (above_ma20 and ma20_trend_up):
        return _neutral_signal(code, name, zone="观察区",
                               msg="均线趋势向下或股价在MA20下方")

    has_rallied = gain_since_last_peak >= config.RELAY_MIN_GAIN

    vol_ratio = _volume_shrink_ratio(klines)
    candle = _candle_pattern(klines)

    hit_ma20 = abs(latest_price - ma20) / ma20 < 0.02 if ma20 > 0 else False
    hit_ma30 = abs(latest_price - ma30) / ma30 < 0.02 if ma30 and ma30 > 0 else False

    volume_ok = vol_ratio <= config.RELAY_VOLUME_SHRINK
    candle_ok = candle == "十字星" or candle == "长下影"
    hit_ma = hit_ma20 or hit_ma30

    has_rallied_text = f"前期涨幅{gain_since_last_peak*100:.0f}%" if has_rallied else f"涨幅不足({gain_since_last_peak*100:.0f}%)"

    if has_rallied and hit_ma and volume_ok and candle_ok:
        stop_loss = round(min(ma20 * (1 - config.STOP_LOSS_MA_BELOW_PCT),
                              latest_price * 0.97), 2)
        return {
            "code": code,
            "name": name,
            "signal_type": "中继买点",
            "zone": "符合买点区",
            "triggered": True,
            "price": round(latest_price, 2),
            "ma20": round(ma20, 2),
            "ma30": round(ma30, 2) if ma30 else None,
            "gain_30d": round(gain_30d * 100, 1),
            "gain_60d": round(gain_60d * 100, 1),
            "volume_ratio": round(vol_ratio, 2),
            "candle_pattern": candle,
            "hit_ma20": hit_ma20,
            "hit_ma30": hit_ma30,
            "stop_loss": stop_loss,
            "stop_loss_pct": f"{config.STOP_LOSS_MA_BELOW_PCT*100:.0f}%",
            "suggested_position": f"{config.RELAY_POSITION_RATIO*100:.0f}%",
            "msg": f"{name}大涨{gain_since_last_peak*100:.0f}%后缩量回踩MA{'20' if hit_ma20 else '30'}线({candle})，触发中继买点",
        }

    if has_rallied or (above_ma20 and ma20_trend_up):
        return _neutral_signal(code, name, zone="强势观察区",
                               msg=f"{name} {has_rallied_text}，趋势完好但未触发买点(量比{vol_ratio:.1f}/{candle})")

    return _neutral_signal(code, name, zone="观察区",
                           msg=f"{name} {has_rallied_text}，等待回调")


def check_exit_signal(code, name, klines=None):
    if klines is None:
        klines = get_stock_kline(code, 65)
    if not klines or len(klines) < 25:
        return {"triggered": False, "msg": "数据不足"}

    closes = [k["close"] for k in klines]
    latest_price = closes[-1]
    ma20 = _compute_ma(closes, 20)
    ma60 = _compute_ma(closes, 60)

    if ma20 is None:
        return {"triggered": False, "msg": "均线数据不足"}

    vol_ratio = _volume_shrink_ratio(klines)

    below_ma20 = latest_price < ma20 * 0.97
    volume_expand = vol_ratio > 1.5

    recent_touches = 0
    for i in range(1, min(15, len(closes))):
        if closes[-(i+1)] < ma20 and closes[-i] >= ma20:
            recent_touches += 1

    breakout_failure = below_ma20 and volume_expand
    multi_touch_failure = recent_touches >= 3 and below_ma20

    if breakout_failure:
        return {
            "code": code,
            "name": name,
            "signal": "终极卖出",
            "triggered": True,
            "price": round(latest_price, 2),
            "ma20": round(ma20, 2),
            "volume_ratio": round(vol_ratio, 2),
            "reason": "放量跌破MA20",
            "action": "无条件全部清仓",
            "msg": f"{name}放量有效跌破MA20({ma20:.1f})，触发终极卖点",
        }

    if multi_touch_failure:
        return {
            "code": code,
            "name": name,
            "signal": "终极卖出",
            "triggered": True,
            "price": round(latest_price, 2),
            "ma20": round(ma20, 2),
            "volume_ratio": round(vol_ratio, 2),
            "reason": f"多次回踩MA20后跌破({recent_touches}次)",
            "action": "无条件全部清仓",
            "msg": f"{name}多次回踩MA20后最终跌破，触发终极卖点",
        }

    return {
        "code": code,
        "name": name,
        "signal": "持有",
        "triggered": False,
        "price": round(latest_price, 2),
        "ma20": round(ma20, 2),
        "volume_ratio": round(vol_ratio, 2),
        "msg": f"{name}在MA20({ma20:.1f})上方运行，持有",
    }


def monitor_stock(code, name, klines=None):
    if klines is None:
        klines = get_stock_kline(code, 80)
    if not klines or len(klines) < 25:
        return {"code": code, "name": name, "zone": "数据不足"}

    launch = check_launch_buy(code, name, klines)
    if launch["triggered"]:
        return launch

    relay = check_relay_buy(code, name, klines)
    if relay["triggered"]:
        return relay

    exit_sig = check_exit_signal(code, name, klines)
    if exit_sig["triggered"]:
        return exit_sig

    if launch.get("zone") == "强势观察区" or relay.get("zone") == "强势观察区":
        return _neutral_signal(code, name, zone="强势观察区",
                               msg=launch.get("msg", "") or relay.get("msg", ""))

    return _neutral_signal(code, name, zone="观察区",
                           msg=launch.get("msg", "") or relay.get("msg", "等待买点"))


def monitor_dragon_list(dragon_list):
    results = []
    for item in dragon_list:
        signal = monitor_stock(item["code"], item["name"])
        results.append(signal)
    return results


def _neutral_signal(code, name, zone="观察区", msg=""):
    return {
        "code": code,
        "name": name,
        "signal_type": "无",
        "zone": zone,
        "triggered": False,
        "msg": msg,
    }
