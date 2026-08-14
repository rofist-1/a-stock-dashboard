# -*- coding: utf-8 -*-
"""
板块 RPS 排名工具（复用脚本）
====================================
口径：31 个申万一级行业指数，各周期涨幅在行业内做百分位排名得到 RPS。
综合 RPS = RPS20*0.5 + RPS50*0.3 + RPS120*0.2（可按需改 WINDOWS / WEIGHTS）。

数据源：akshare index_hist_sw（申万宏源），无需东财全市场行情，稳定快速（约 30s）。

用法（用技能 venv 的 Python 运行）：
  & "C:/Users/Rofis/.agents/skills/stockaskill/.venv/Scripts/python.exe" sw_rps_calc.py

输出：控制台打印全 31 板块排名 + reports/<时间戳>_板块RPS.csv/.md
"""
import sys, io, time, os, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import akshare as ak
import pandas as pd

WINDOWS = {"RPS5": 5, "RPS20": 20, "RPS50": 50, "RPS120": 120}
WEIGHTS = {"RPS20": 0.5, "RPS50": 0.3, "RPS120": 0.2}
TOP_N = 20


def main() -> None:
    parser = argparse.ArgumentParser(description="板块 RPS 排名")
    parser.add_argument("--top", type=int, default=TOP_N, help="输出前 N 名（默认 20）")
    parser.add_argument("--days", type=int, default=250, help="取历史窗口天数（默认 250，够算 RPS120）")
    args = parser.parse_args()

    # ---------- 1. 获取 31 个申万一级行业 ----------
    sw = ak.sw_index_first_info()
    sw = sw[["行业代码", "行业名称", "成份个数"]].copy()
    print(f"申万一级行业总数: {len(sw)}")

    # ---------- 2. 逐行业拉历史指数 ----------
    hist = {}
    failed = []
    for _, row in sw.iterrows():
        code = row["行业代码"]  # 如 801010.SI
        name = row["行业名称"]
        num = code.split(".")[0]
        try:
            df = ak.index_hist_sw(symbol=num, period="day")
            df = df[["日期", "收盘"]].copy()
            df["日期"] = pd.to_datetime(df["日期"])
            df = df.sort_values("日期").tail(args.days).reset_index(drop=True)
            hist[name] = df
            print(f"  OK {name} ({len(df)} 行, 最新 {df['日期'].iloc[-1].date()})")
        except Exception as e:
            failed.append((name, code, repr(e)[:120]))
            print(f"  FAIL {name}: {repr(e)[:120]}")
        time.sleep(0.15)

    print(f"\n失败: {failed if failed else '无'}")

    # ---------- 3. 计算各周期涨幅 ----------
    data = {}
    for name, df in hist.items():
        closes = df["收盘"]
        rec = {"latest_date": df["日期"].iloc[-1]}
        for label, n in WINDOWS.items():
            if len(closes) > n:
                rec[label + "_chg"] = (closes.iloc[-1] / closes.iloc[-1 - n] - 1) * 100
            else:
                rec[label + "_chg"] = None
        data[name] = rec

    idx = pd.DataFrame(data).T

    # ---------- 4. RPS = 各周期涨幅百分位排名 ----------
    for label in WINDOWS:
        col = label + "_chg"
        if idx[col].notna().sum() == len(idx):
            idx[label] = idx[col].rank(pct=True) * 100
        else:
            idx[label] = None

    # ---------- 5. 综合 RPS ----------
    if all(c in idx for c in WEIGHTS):
        idx["RPS综合"] = sum(idx[c] * w for c, w in WEIGHTS.items())

    # ---------- 6. 排序输出 ----------
    out_cols = ["latest_date", "RPS5", "RPS20", "RPS50", "RPS120", "RPS综合"]
    for c in out_cols:
        if c != "latest_date":
            idx[c] = pd.to_numeric(idx[c], errors="coerce").round(1)
    idx = idx.sort_values("RPS综合", ascending=False)

    name2code = dict(zip(sw["行业名称"], sw["行业代码"]))
    idx.insert(0, "行业代码", [name2code.get(n, "") for n in idx.index])

    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.max_rows", 100)
    pd.set_option("display.width", 200)
    latest = idx["latest_date"].iloc[0]
    latest_s = latest.date() if hasattr(latest, "date") else latest
    print(f"\n===== 板块 RPS 排名 Top {min(args.top, len(idx))}（综合降序，截至 {latest_s}）=====")
    print(idx[out_cols].head(args.top).to_string())

    # ---------- 7. 存报告 ----------
    os.makedirs("reports", exist_ok=True)
    ts = pd.Timestamp.now().strftime("%Y-%m-%d-%H%M")
    report = idx.reset_index().rename(columns={"index": "行业名称"})
    report.to_csv(f"reports/{ts}_板块RPS.csv", index=False, encoding="utf-8-sig")

    md = ["# 板块 RPS 排名", "",
          f"- 数据截至: {latest_s}",
          "- RPS 口径: 行业指数各周期涨幅在 31 个申万一级行业中的百分位排名",
          "- 综合 RPS = RPS20×0.5 + RPS50×0.3 + RPS120×0.2",
          "- 数据源: akshare index_hist_sw（申万宏源）",
          "", "| 排名 | 行业代码 | 行业名称 | RPS5 | RPS20 | RPS50 | RPS120 | RPS综合 |",
          "|---|---|---|---|---|---|---|---|"]
    for i, (name, r) in enumerate(idx.head(args.top).iterrows(), 1):
        md.append(f"| {i} | {r['行业代码']} | {name} | {r['RPS5']} | {r['RPS20']} | {r['RPS50']} | {r['RPS120']} | {r['RPS综合']} |")
    with open(f"reports/{ts}_板块RPS.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\n报告已保存: reports/{ts}_板块RPS.csv / .md")


if __name__ == "__main__":
    main()
