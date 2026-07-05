import pandas as pd
import numpy as np


def quiet_eruption_signal(df: pd.DataFrame, index_df: pd.DataFrame = None) -> pd.Series:
    """
    静默爆发点选股模型（口袋支点+杯柄突破逻辑）

    Parameters
    ----------
    df : pd.DataFrame
        个股日线数据，须含 open, high, low, close, volume
    index_df : pd.DataFrame, optional
        大盘指数日线，须含 close 列，index 与 df 对齐。
        不传则 cond_d（跑赢大盘）不参与评分。

    Returns
    -------
    pd.Series
        -1=无信号, 0=信号, 1=强信号（可叠加评分）
    """
    df = df.copy()

    # ========== 1. 基础均线 ==========
    df['MA10']  = df['close'].rolling(10).mean()
    df['MA20']  = df['close'].rolling(20).mean()
    df['MA50']  = df['close'].rolling(50).mean()
    df['MA200'] = df['close'].rolling(200).mean()

    # ========== 2. 量能 ==========
    df['VOL120']    = df['volume'].rolling(120).mean()
    df['VOL_MAX20'] = df['volume'].rolling(20).max().shift(1)  # 前20日最大量（不含当天）

    # ========== 3. 振幅（shift 防未来函数）==========
    HHV10 = df['high'].rolling(10).max()
    LLV10 = df['low'].rolling(10).min()
    df['RANGE10'] = ((HHV10 - LLV10) / LLV10 * 100).shift(1)

    HHV100 = df['high'].rolling(100).max()

    df['prev_close'] = df['close'].shift(1)
    df['prev_high']  = df['high'].shift(1)

    # ========== 4. 条件（布尔列，便于调试看哪条没满足）==========

    # A: 中期多头排列，MA50 > MA200，且 MA200 走平或上翘
    df['cond_a'] = (df['MA50'] > df['MA200']) & (df['MA200'] >= df['MA200'].shift(20))

    # B: 股价在 MA20 附近（±3%）+ 前期振幅收窄
    df['cond_b'] = (
        df['close'].div(df['MA20']).between(0.97, 1.03)
        & (df['RANGE10'] < 15)
    )

    # C: 量价启动
    pct_chg = df['close'] / df['prev_close'] - 1
    df['cond_c'] = (
        (df['volume'] > df['VOL120'] * 1.5)            # 放量 > 120日均量1.5倍
        & (df['volume'] >= df['VOL_MAX20'])             # 创20日量新高
        & (pct_chg.between(0.03, 0.09))                 # 涨3%-9%
    )

    # D: 跑赢大盘 2%（可选，无指数数据时忽略）
    if index_df is not None:
        idx = index_df.reindex(df.index).ffill()
        idx_ret = idx['close'] / idx['close'].shift(1) - 1
        df['cond_d'] = (pct_chg - idx_ret) > 0.02
    else:
        df['cond_d'] = True  # 无指数时放过

    # E: 从 100 日高点回撤超过 15%
    df['cond_e'] = df['close'] / HHV100 < 0.85

    # ========== 5. 综合信号 ==========
    signal = df['cond_a'] & df['cond_b'] & df['cond_c'] & df['cond_d'] & df['cond_e']

    return signal.astype(int)  # 0/1


def quiet_eruption_score(df: pd.DataFrame, index_df: pd.DataFrame = None) -> pd.Series:
    """
    评分版：每满足一个条件得 1 分，满分 5 分。
    用于排序，避免硬过滤把弱信号全丢掉。
    """
    df = df.copy()

    df['MA10']  = df['close'].rolling(10).mean()
    df['MA20']  = df['close'].rolling(20).mean()
    df['MA50']  = df['close'].rolling(50).mean()
    df['MA200'] = df['close'].rolling(200).mean()

    df['VOL120']    = df['volume'].rolling(120).mean()
    df['VOL_MAX20'] = df['volume'].rolling(20).max().shift(1)

    HHV10 = df['high'].rolling(10).max()
    LLV10 = df['low'].rolling(10).min()
    RANGE10 = ((HHV10 - LLV10) / LLV10 * 100).shift(1)
    HHV100 = df['high'].rolling(100).max()

    prev_close = df['close'].shift(1)
    pct_chg = df['close'] / prev_close - 1

    score = pd.Series(0, index=df.index)

    score += (df['MA50'] > df['MA200']) & (df['MA200'] >= df['MA200'].shift(20))
    score += df['close'].div(df['MA20']).between(0.97, 1.03) & (RANGE10 < 15)
    score += (df['volume'] > df['VOL120'] * 1.5) & (df['volume'] >= df['VOL_MAX20']) & pct_chg.between(0.03, 0.09)
    score += df['close'] / HHV100 < 0.85

    if index_df is not None:
        idx_ret = index_df.reindex(df.index).ffill()['close'].pct_change()
        score += (pct_chg - idx_ret) > 0.02
    else:
        score += (pct_chg > 0.02)  # 无指数时改为跑赢无风险收益

    return score


# ==================== 使用示例 ====================
if __name__ == "__main__":
    dates = pd.date_range(start='2025-01-01', periods=500, freq='B')
    np.random.seed(42)
    demo_df = pd.DataFrame({
        'open':   np.random.randn(500).cumsum() + 100,
        'high':   np.random.randn(500).cumsum() + 102,
        'low':    np.random.randn(500).cumsum() + 98,
        'close':  np.random.randn(500).cumsum() + 100,
        'volume': np.random.randint(1_000_000, 5_000_000, 500),
    })

    # 构造一个模拟大盘
    index_df = pd.DataFrame({
        'close': np.random.randn(500).cumsum() + 3000,
    }, index=demo_df.index)

    signals = quiet_eruption_signal(demo_df, index_df)
    scores  = quiet_eruption_score(demo_df, index_df)

    buy_dates = demo_df.index[signals == 1]
    print(f"买点信号数: {signals.sum()}")
    print(f"评分 >=4 的日期数: {(scores >= 4).sum()}")
    if len(buy_dates):
        print("触发日期：")
        print(buy_dates)
