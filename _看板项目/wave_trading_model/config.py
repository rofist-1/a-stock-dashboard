"""
全局配置参数
============
所有可调参数集中在此，方便策略调优。
"""

INDEX_CODE = "000001.SH"
INDEX_NAME = "上证指数"

INDEX_ALTERNATIVES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
}

MA_PERIOD = 20
MA_LONGBOOK = 60

MARKET_BULL = "上涨市"
MARKET_RANGE = "震荡市"
MARKET_BEAR = "下跌市"

POSITION_LIMITS = {
    MARKET_BULL: 1.0,
    MARKET_RANGE: 0.5,
    MARKET_BEAR: 0.1,
}

RPS_THRESHOLD_LEADER = 90
RPS_WARN_THRESHOLD = 80
RPS_EXIT_THRESHOLD = 90

STYLE_WEIGHT = "权重行情"
STYLE_BROAD = "普涨行情"
STYLE_CLUSTER = "抱团行情"

INITIAL_POSITION_RATIO = 0.3
RELAY_POSITION_RATIO = 0.4
MAX_POSITION_RATIO = 0.7
MAX_POSITIONS = 3

LAUNCH_MA = 10
LAUNCH_VOLUME_SHRINK = 0.7
LAUNCH_CANDLE_PATTERNS = ["十字星", "小阳线", "长下影"]

RELAY_MIN_GAIN = 0.30
RELAY_MA = 30
RELAY_VOLUME_SHRINK = 0.5

STOP_LOSS_MA_BELOW_PCT = 0.03
MAX_LOSS_PER_TRADE = 0.02

NEW_HIGH_DAYS = 100
RPS_LOOKBACK_10 = 10
RPS_LOOKBACK_20 = 20
RPS_LOOKBACK_60 = 60

SECTOR_TOP_N = 10
STOCK_WATCH_N = 5

# ========== 趋势中军筛选参数 ==========
TREND_LEADER_MIN_CIRC_MARKET_YI = 100   # 流通市值 > 100亿
TREND_LEADER_MIN_AMOUNT_5D_YI = 5       # 5日日均成交额 > 5亿
TREND_LEADER_REJECT_CONTINUE = 2        # 拒绝≥N连板
TREND_LEADER_MA_PERIOD = 20             # MA20
TREND_LEADER_PULLBACK_WINDOW = 5        # 回踩形态检测窗口（日）
TREND_LEADER_VOLUME_SHRINK = 0.8        # 缩量定义：量比 < 0.8
TREND_LEADER_NEAR_MA_THRESHOLD = 0.03   # 靠近MA5/MA13 3%以内算"回踩到位"

# 趋势中军评分权重
TREND_LEADER_WEIGHTS = {
    "market_cap": 20,           # 市值越大越好（机构容量）
    "turnover": 20,             # 成交额越大越好（流动性）
    "ma_position": 20,          # MA20上方幅度（趋势强度）
    "pullback_pattern": 25,     # 回踩形态得分（技术面）
    "industry_position": 15,    # 行业地位（逻辑面）
}

OUTPUT_DIR = None
