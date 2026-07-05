"""
市场风格识别模块（辅助判断）
=========================
通过涨跌家数比、资金流向，区分行情的结构化特征。

权重行情：指数涨，个股跌多涨少 → 只做指数ETF或权重龙头
普涨行情：指数涨，个股涨多跌少 → 积极布局主线板块龙头
抱团行情：指数震荡或下跌，主线逆势抗跌 → 极端聚焦主线，低吸核心龙头
"""

from datetime import datetime
# avoid relative import failures
import sys, os
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
import config
from data_fetcher import get_market_overview


def analyze_style():
    overview = get_market_overview()
    if not overview:
        return _default_style()

    rise = overview.get("rise_count", 0) or 0
    fall = overview.get("fall_count", 0) or 0
    total = rise + fall
    if total == 0:
        return _default_style()

    rise_ratio = rise / total

    limit_up = overview.get("limit_up_count", 0) or 0
    limit_down = overview.get("limit_down_count", 0) or 0

    index_up = rise > fall
    major_weight = overview.get("major_cap_lead", False)

    style = config.STYLE_BROAD
    reason_parts = []

    if major_weight and rise_ratio < 0.5:
        style = config.STYLE_WEIGHT
        reason_parts.append(f"指数与个股背离(上涨{rise}家/下跌{fall}家)，权重主导")
    elif rise_ratio >= 0.6:
        style = config.STYLE_BROAD
        reason_parts.append(f"普涨格局(上涨{rise}/{total}，占比{rise_ratio*100:.0f}%)")
    elif index_up and rise_ratio < 0.5:
        style = config.STYLE_WEIGHT
        reason_parts.append(f"涨指数不涨个股(上涨{rise}/{total})，权重行情")
    else:
        style = config.STYLE_CLUSTER
        reason_parts.append(f"分化格局(涨{rise}/跌{fall})，关注结构性机会")

    if limit_down > 10:
        reason_parts.append(f"跌停{limit_down}家注意风险")

    market_temp = overview.get("market_temperature", 50)

    return {
        "style": style,
        "rise_count": rise,
        "fall_count": fall,
        "total_stocks": total,
        "rise_ratio": round(rise_ratio, 3),
        "limit_up_count": limit_up,
        "limit_down_count": limit_down,
        "market_temperature": market_temp,
        "reason": "，".join(reason_parts),
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _default_style():
    return {
        "style": config.STYLE_BROAD,
        "rise_count": 0,
        "fall_count": 0,
        "total_stocks": 0,
        "rise_ratio": 0.5,
        "limit_up_count": 0,
        "limit_down_count": 0,
        "market_temperature": 50,
        "reason": "数据不足，默认普涨格局",
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
