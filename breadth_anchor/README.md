# A股市场广度锚（Breadth Anchor）

每日收盘后自动计算**样本池内收盘价站上 MA20 的个股占比**，用于衡量市场整体趋势体质。

样本池 = 沪深300 + 中证500 + 中证1000 成分股（合并去重，约 1800 只，覆盖大中小盘）。

---

## 快速开始

### 1. 安装依赖

需要 Python 3.9+ 与 `pandas`、`akshare`：

```bash
pip install pandas akshare
```

> 建议使用独立 venv：`python -m venv .venv` → `.venv\Scripts\activate` → `pip install pandas akshare`

### 2. 每日运行

```bash
python breadth_anchor.py                 # 跑最近一个交易日
```

运行结束后终端打印当日结果，并追加一行到 `breadth_anchor_log.csv`。

### 3. 其他命令

```bash
python breadth_anchor.py --date 2026-08-07   # 补跑指定日期
python breadth_anchor.py --refresh-universe   # 强制刷新成分股名单（月度自动，一般无需手动）
python breadth_anchor.py --workers 16         # 调高并发数（默认8，被限流时降低）
python breadth_anchor.py --source akshare     # 强制使用 akshare
```

---

## 输出示例

```
日期: 2026-08-07
样本池: 1800只（剔除0只：停牌0/次新0/无数据0/错误0）
站上MA20: 1368只
广度锚: 76.0%（5日前: 无历史，变化: +1.2pct）
体质判定: 强市（多数股票在趋势中）
```

> 剔除分类：`停牌` = 最新K线未覆盖目标日；`次新` = 有效K线 < 25 根（上市不足约25个交易日）；`无数据` = 当日拉取为空或不足20根；`错误` = 重试3次后仍失败。

### 体质判定阈值

| 广度锚 | 判定 |
|--------|------|
| > 60% | 强市（多数股票在趋势中） |
| 40% ~ 60% | 结构市（只有主线有机会） |
| < 40% | 弱市（谨慎） |

---

## 数据源

本工具**优先使用 iFinD（同花顺）**，环境不可用时自动降级到 **akshare（腾讯行情接口）**。

### 当前环境结论（2026-08-08 实测）

| 数据源 | 状态 |
|--------|------|
| iFinDPy SDK | ❌ 未安装，自动跳过 |
| akshare 东财日线接口 | ⚠️ 易被限流（实测连接被拒） |
| akshare 腾讯日线接口 `stock_zh_a_hist_tx` | ✅ 稳定可用（当前默认） |
| akshare 中证成分股 `index_stock_cons_csindex` | ✅ 稳定可用 |

**当前实际运行 = akshare + 腾讯接口**，已内置并发（默认8线程）、每请求 15s 超时、失败重试3次。

### 如何切换数据源

- **升级到 iFinD**：`pip install iFinDPy`（需同花顺终端登录）。脚本启动时 `--source auto` 会自动检测 `iFinDPy`，检测到即用 iFinD；也可 `--source ifind` 强制指定。iFinD 分支为通用骨架，`fetch_daily` / `fetch_universe` 内部字段名需按你安装的 SDK 版本校准。
- **强制 akshare**：`python breadth_anchor.py --source akshare`（默认降级路径）。

如需切换为 akshare 的东财接口，修改 `AkshareSource.fetch_daily` 中的降级分支顺序即可。

---

## 日志文件 `breadth_anchor_log.csv`

| 字段 | 含义 |
|------|------|
| `date` | 交易日 YYYY-MM-DD |
| `pool_size` | 有效样本数（总成分数 - 剔除数） |
| `excluded` | 剔除数量（停牌/次新/无数据/错误合计） |
| `above_ma20` | 站上 MA20 家数 |
| `breadth_pct` | 广度锚（%，保留1位小数） |
| `change_5d` | 较约5个交易日前的变化（百分点） |
| `regime` | 体质判定文案 |

首次运行无历史，`change_5d` 为空；运行几次后自动带出 5 日前对比。

---

## 文件结构

```
breadth_anchor/
├── breadth_anchor.py       # 主脚本（计算 + 日志 + CLI）
├── universe_cache.json     # 成分股缓存（每月自动刷新，可 --refresh-universe 强制）
├── breadth_anchor_log.csv  # 每日结果日志（追加）
└── README.md               # 本文档
```

---

## 计算口径

- 对每只成分股拉取目标日前约 **90 个自然日**的日线（前复权），覆盖约 60 个交易日，留足 MA20 余量。
- `MA20` = 最近 20 个交易日收盘价的简单算术平均。
- `站上` = 最新收盘价 > 当日 MA20。
- `广度锚` = 站上家数 ÷ 有效样本家数 × 100%（保留1位小数）。
- 剔除规则：停牌（最新K线未到目标日）、次新（有效K线 < 25 根）、无数据/不足（有效K线 < 20 根）、错误（拉取失败）。

> 数据来源为站内/公开行情接口，复权方式为前复权（qfq），与同花顺/东财前复权口径基本一致（实测 40 只样本仅 1 只因复权差异判定不同，属边界情况）。
