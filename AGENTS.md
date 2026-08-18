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

### 判读器 v1.5（已固化，全年回测验证）
- 手册: `交易模式4.0/每日判读与双模式操作手册.md` | 回测: `_策略脚本/判读器回测_v3.py`
- **五源打分**：①s1登顶≥5天 ②一级占比≥25%或细分≥20% ③龙头新高 ④高度板>3板 ⑤**涨停端同步闸门**（limit_up_filter 主类第一 == 新高池s1，同义归一）
- **同步性闸门全年零误判**：7月医药新高池堆积但涨停端=电力/芯片/智能电网×5全否决；8/3银行(涨停端核电)否决；5月芯片/8月医药同步放行
- **切换信号=涨停端衰减**：主升日 s1 在涨停端家数 次日衰减≥30% 或掉下第一→切轮动（8/13医药13→8/14医药9,-31%切；新高池46→44无感）
- 涨停端数据来源：`limit_up_filter` date 参数逐日拉（主类聚合行）；JSON l1Name/l1Count 仅7/13起

## A股波段看板（主看板，每日更新）
- **唯一主看板**：`C:\Users\Rofis\Desktop\a-stock-dashboard\`（index.html + data.json）
- 在线地址：https://rofist-1.github.io/a-stock-dashboard/ （GitHub Pages，来自桌面根仓库 `rofist-1/a-stock-dashboard`）
- **看板 UI 已升级为 v18**：`a-stock-dashboard/index.html` = `百日新高系统/A股市场情绪综合看板18.html` 部署版（含增速异动UI）；已把读取改相对路径 `fetch('data.json',{cache:'no-store'})`，localStorage 合并逻辑保留
- **数据文件**：`a-stock-dashboard/data.json`（按日期升序的数组，UTF-8 编码，当前 153 条到 8/18，最近交易日为最新）
- **同步副本**（每次更新必须三处同时写）：
  1. `a-stock-dashboard/data.json`
  2. `百日新高系统/data.json`
  3. 桌面 `a股波段看板_YYYY-MM-DD.json`（文件名为当日日期）
- **每日更新流程**（收盘后）：
  1. 用户提供收盘数据（成交量、涨停/跌停/炸板/连板、百日新高/新低、板块 s1-s3/w1-w3 明细）
  2. 追加当日记录到 data.json 并排序；字段格式见 8/14 记录（date/volume/limitUp/limitDown/bomb/chain/newHigh/newLow/newHighDaily + s1~s3、w1~w3 及细分 b1/b2 + l1~l3 龙头）
  3. 三副本同步写入
  4. git add + commit（信息如"看板数据更新 0814"）+ push origin main
- **数据字段口径**：
  - volume=两市成交额(亿)；limitUp/limitDown=涨停/跌停家数；bomb=炸板家数；chain=连板股数
  - newHigh/newLow=全市场百日新高/新低家数；newHighDaily=新高新增家数
  - s1~s3=强势板块(名称/总家数/新增 + 细分b1/b2)；w1~w3=潜在观察板块(同结构 + pct/assist/reason)
- **注意事项（避免搞错）**：
  - 数据文件为 **UTF-8 编码**；PowerShell 控制台 `Get-Content` 默认 GBK 读会乱码，属显示问题不影响文件；读写请用 Python `encoding='utf-8'`
  - 不要用"同步看板.bat"自动同步（按修改时间取最新文件，曾取到旧版122条导致数据回退到7/3）
  - 浏览器访问请走 http://127.0.0.1:8765 本地服务器（file:// 直开会 CORS 报错）；index.html 已加 `fetch('data.json', {cache:'no-store'})` 防缓存
  - 数据更新后必须 push，否则 GitHub Pages 停留在旧数据
  - 判断当日是否有"最新日期偏旧"问题：以 data.json 最后一条 date 为准（8/14 曾出过此问题）
  - l1~l3 龙头=涨停最多板块，来源 `limit_up_ladder` 主类排行（非ST涨停家数口径）；8/14、8/17、8/18 已补，7/13 起有值
