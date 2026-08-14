# 会话：交易模式

# 持久化信息

## 迪雅数据 API
- Token: 4377183a3f71a9eda95741cd2eb8e6a944c6fe90
- 参数名：`apiToken`（不是 `apikey`）
- 基础地址：`https://api.cxdy.vip/api/`
- 套餐：基础版 ¥39/月
- 关键端点：
  - `hslb` - 股票列表
  - `lsjy` - 历史K线（需传 symbol=sh/sz+代码, adjust=qfq, start_date, end_date）
  - `ssjy` - 实时行情
  - `bkzj` - 概念板块
  - `gsxq` - 公司详情（含行业）
  - `qgqp` - 千股千评（含换手率/市盈率）

## 回测策略：放量站上60日线
- 买入：信号日次日开盘
- 卖出：跌破5日线次日开盘
- 大盘过滤：上证指数需站上MA60
- 选股条件：站上60日线 + 量比≥1.5 + 近20日涨幅≤25% + 流通市值20~500亿
- 回测结果（6月）：胜率46.6% / 平均收益+1.30% / 盈亏比2.55 / 累计+304%

## 板块 RPS 排名（已固化）
- 脚本: `C:\Users\Rofis\Desktop\sw_rps_calc.py`
- 运行: `& "C:/Users/Rofis/.agents/skills/stockaskill/.venv/Scripts/python.exe" "C:/Users/Rofis/Desktop/sw_rps_calc.py" [--top N]`
- 依赖环境: 技能 venv（Python 3.13 + akshare），非系统 Python 3.9
- 数据源: akshare `index_hist_sw`（申万宏源，31 个一级行业指数，稳定约 30s）
- 口径: RPS5/20/50/120 = 行业指数各周期涨幅在 31 个行业中的百分位排名
- 综合 RPS = RPS20×0.5 + RPS50×0.3 + RPS120×0.2
- 输出: 控制台前 N + `reports/<时间戳>_板块RPS.csv/.md`
- 备注: 不用东财全市场行情接口（易被限流）；不要逐股拉全市场算成分中位数（太慢，1 小时+）

## 交易模式4.0 模块
详见 `交易模式4.0/README.md`

### 核心工具链
1. **百日新高筛选系统** (`交易模式4.0/百日新高/screening_rules.md`)
   - stock_screener 海选 → 三通道分类 → 产业链验证 → 买点监控
2. **板块生命周期分析** (`交易模式4.0/板块生命周期/`)
   - 锚点自动检测 / 游资型vs趋势型 / 初期-中期-末期标记
   - 运行: `python 交易模式4.0/板块生命周期/sector_lifecycle_v3.py`
3. **每日简报** — 整合上述两模块输出
