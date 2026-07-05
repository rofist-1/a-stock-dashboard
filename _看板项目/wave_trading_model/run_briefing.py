# -*- coding: utf-8 -*-
"""
每日 14:50 自动运行脚本
======================
推送方式:
  微信: PushPlus 推送极简摘要
  邮箱: 完整简报到 rofist-1@outlook.com

用法:
  python wave_trading_model/run_briefing.py
"""

import os, sys, json, io, re
from datetime import datetime, date
# 控制台UTF-8输出支持（防止emoji报错）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wave_trading_model import config
from wave_trading_model.briefing import generate_briefing
from wave_trading_model.data_fetcher import get_market_overview

# ======================== 推送工具 ========================
def _load_notify_config():
    """加载推送配置, 缺省时静默跳过推送"""
    try:
        from wave_trading_model.notify_config import (PUSHPLUS_TOKEN, SMTP_SERVER,
            SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO, ENABLE_WECHAT, ENABLE_EMAIL)
        return {"pushplus_token": PUSHPLUS_TOKEN, "smtp_server": SMTP_SERVER,
                "smtp_port": SMTP_PORT, "smtp_user": SMTP_USER, "smtp_pass": SMTP_PASS,
                "email_to": EMAIL_TO, "enable_wechat": ENABLE_WECHAT, "enable_email": ENABLE_EMAIL}
    except: return {}

def push_wechat(title, content, token):
    if not token: return False
    try:
        import urllib.request
        data = json.dumps({"token": token, "title": title, "content": content, "template": "txt"}).encode()
        req = urllib.request.Request("http://www.pushplus.plus/send", data=data,
            headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read()).get("code") == 200
    except: return False

def send_email(subject, body, cfg):
    if not cfg.get("smtp_pass"): return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = cfg["smtp_user"]
        msg["To"] = cfg["email_to"]
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as s:
            s.starttls()
            s.login(cfg["smtp_user"], cfg["smtp_pass"])
            s.send_message(msg)
        return True
    except: return False

# ======================== 交易日判断 ========================
def is_trading_day():
    today = datetime.now()
    if today.weekday() >= 5: return False
    try:
        ov = get_market_overview(today.strftime("%Y-%m-%d"))
        if ov and isinstance(ov, dict) and ov.get("trade_date"):
            return True
        if ov is None or isinstance(ov, dict):
            return True  # API不可用时, 周一至周五视为交易日
    except: pass
    return True  # 工作日默认认为有行情

# ======================== 简报格式化 ========================
def format_wechat_summary(briefing):
    ms = briefing["market_state"]
    mst = briefing["market_style"]
    sectors = briefing["mainline_sectors"]
    trend = briefing["trend_leaders"]

    lines = []
    lines.append(f"【波段交易模型 · 每日简报】")
    lines.append(f"时间: {briefing['generated_at']}")
    lines.append("")

    # 大盘+仓位
    lines.append(f"大盘: {ms['state']}")
    lines.append(f"仓位上限: {ms['position_limit_text']}")
    lines.append(f"风格: {mst['style']}")
    lines.append("")

    # 主线板块
    resonance = [s['name'] for s in sectors['list'] if s.get('three_resonance')]
    if resonance:
        lines.append(f"三线共振: {'/'.join(resonance[:5])}")
    lines.append("")

    # 趋势中军 -> 次日预警
    warns = []
    for ts in trend:
        for s in ts.get("trend_leaders", []):
            if s.get("qualified") and s.get("ma_form") == "缩量回调":
                warns.append(s['name'])
    if warns:
        lines.append("【次日预警】接近买点的趋势中军:")
        for w in warns[:10]:
            lines.append(f"  {w}")
        lines.append("⚠ 请以次日开盘后确认形态为准，勿在尾盘买入")
    else:
        lines.append("当前无接近买点个股")

    lines.append("")
    lines.append(briefing["action_summary"])
    return "\n".join(lines)

def format_email_full(briefing):
    buf = io.StringIO()

    ms = briefing["market_state"]
    mst = briefing["market_style"]
    sectors = briefing["mainline_sectors"]
    sent = briefing["sentiment_dragons"]
    tl = briefing["trend_leaders"]
    action = briefing["action_summary"]

    buf.write(f"波段交易模型 · 每日决策简报\n")
    buf.write(f"生成时间: {briefing['generated_at']}\n")
    buf.write("=" * 60 + "\n\n")

    buf.write(f"[大盘环境 + 仓位管理]\n")
    buf.write(f"  指数: {ms['index_name']} ({ms['index_code']})\n")
    buf.write(f"  最新价: {ms['latest_price'] if ms['latest_price'] is not None else '--'}  |  MA20: {ms['ma20'] if ms['ma20'] is not None else '--'}\n")
    buf.write(f"  MA20斜率: {ms['ma20_slope_pct']:+.2f}%  |  状态: {ms['state']}\n")
    buf.write(f"  建议仓位上限: {ms['position_limit_text']}\n")
    buf.write(f"  成交额: {ms['turnover_yi'] if ms['turnover_yi'] is not None else '--'}亿\n")
    buf.write(f"  判断依据: {ms['reason']}\n\n")

    buf.write(f"[市场风格]\n")
    buf.write(f"  风格: {mst['style']}\n")
    buf.write(f"  上涨{mst['rise_count']}家 / 下跌{mst['fall_count']}家 (占比{mst['rise_ratio']*100:.0f}%)\n")
    buf.write(f"  涨停{mst['limit_up_count']}家 / 跌停{mst['limit_down_count']}家\n")
    buf.write(f"  市场温度: {mst['market_temperature']}/100\n\n")

    buf.write(f"[全部热门板块 - RPS排序]\n")
    all_secs = briefing.get("all_sectors", [])
    for s in all_secs:
        r10 = f"{s['rps_10']:.0f}" if s.get('rps_10') else '--'
        r20 = f"{s['rps_20']:.0f}" if s.get('rps_20') else '--'
        r60 = f"{s['rps_60']:.0f}" if s.get('rps_60') else '--'
        res = "Y" if s.get('three_resonance') else "N"
        buf.write(f"  {s['name']:<16} RPS({r10}/{r20}/{r60}) 共振={res} 涨停{s['limit_up_num']}\n")
    buf.write("\n")
    buf.write(f"[主线板块 - 三线共振 RPS>=90]\n")
    if sectors['list']:
        for s in sectors['list']:
            r10 = f"{s['rps_10']:.0f}" if s.get('rps_10') else '--'
            r20 = f"{s['rps_20']:.0f}" if s.get('rps_20') else '--'
            r60 = f"{s['rps_60']:.0f}" if s.get('rps_60') else '--'
            buf.write(f"  {s['name']:<16} RPS({r10}/{r20}/{r60}) 涨停{s['limit_up_num']} | {s.get('status','')}\n")
    else:
        buf.write("  (暂无板块同时满足三线RPS>=90)\n")
    buf.write("\n")

    buf.write(f"[情绪信号 - 短线风向标]\n")
    for sd in sent:
        for d in sd.get("dragons", [])[:3]:
            lu = "涨停" if d.get("is_limit_up_today") else ""
            cn = f"{d['continue_num']}连板" if d.get("continue_num", 0) > 1 else ""
            buf.write(f"  {d['name']:<8} [评分{d['dragon_score']} {d['dragon_rank']}] {lu} {cn}\n")
    if not sent: buf.write("  (无数据)\n")
    buf.write("\n")

    buf.write(f"[趋势中军 - 机构容量票筛选]\n")
    for ts in tl:
        leaders = ts.get("trend_leaders", [])
        qual = ts.get("qualified_count", 0)
        total = ts.get("total_candidates", 0)
        buf.write(f"  {ts['sector_name']} (合格{qual}/{total})\n")
        for s in leaders:
            tag = "✓" if s.get("qualified") else "✗"
            cap = f"{s['market_cap_yi']:.0f}亿" if s.get("market_cap_yi") else "--"
            amt = f"{s['amount_5d_yi']:.1f}亿" if s.get("amount_5d_yi") else "--"
            ma = f"{s['ma_distance_pct']:+.1f}%" if s.get("ma_distance_pct") is not None else "--"
            form = s.get("ma_form", "")
            pat = " ↓回踩线" if s.get("has_pullback_pattern") else ""
            buf.write(f"  {tag} {s['name']:<8} 评分{s['total_score']:.0f} | 流通{cap} | 成交{amt} | MA20距{ma} | {form}{pat}\n")
            if s.get("fails"):
                for f in s['fails'][:2]: buf.write(f"    未达标: {f}\n")
    buf.write("\n")

    # 次日预警区
    buf.write(f"[重要 · 次日预警]\n")
    warns = []
    for ts in tl:
        for s in ts.get("trend_leaders", []):
            if s.get("qualified") and s.get("ma_form") == "缩量回调":
                cap = f"{s['market_cap_yi']:.0f}亿" if s.get("market_cap_yi") else "--"
                warns.append(f"{s['name']:<8} ({ts['sector_name']}) 流通{cap} 评分{s['total_score']:.0f}")
    if warns:
        for w in warns:
            buf.write(f"  {w}\n")
        buf.write(f"\n  ⚠ 请以次日开盘后确认形态为准，勿在尾盘买入\n")
    else:
        buf.write("  当前无接近买点的趋势中军\n")
    buf.write("\n")

    buf.write(f"[决策摘要]\n")
    buf.write(f"  {action}\n\n")

    buf.write(f"[模型参数]\n")
    c = briefing["config"]
    buf.write(f"  RPS>{c['rps_threshold']} | 预警RPS10<{c['rps_warn']} | 缩量<{c['launch_volume_shrink']}/{c['relay_volume_shrink']}\n")
    buf.write(f"  中继涨幅>={c['relay_min_gain']} | 最多{c['max_positions']}只\n")
    buf.write(f"  趋势中军: 流通市值{c['trend_leader_min_cap']} | 成交额{c['trend_leader_min_amt']} | 拒绝连板 | 价在MA20上+MA20向上\n\n")

    buf.write("=" * 60 + "\n")
    buf.write("用法指南:\n")
    buf.write("  情绪信号 = 短线最热方向的风向标，不是买入信号\n")
    buf.write("  趋势中军 = 波段交易核心的机构容量票，等待买点\n")
    buf.write("  次日预警 = 接近买点区域的候选，开盘确认形态后再操作\n")
    buf.write("  核心原则: 等待是交易的一部分\n")
    buf.write("=" * 60 + "\n")
    return buf.getvalue()

# ======================== 百日新高数据输入 ========================
NEWHIGH_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "newhigh_sectors.json")

def _load_newhigh_cache():
    try:
        if os.path.exists(NEWHIGH_CACHE):
            with open(NEWHIGH_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
    except: pass
    return None

def _save_newhigh_cache(data):
    os.makedirs(os.path.dirname(NEWHIGH_CACHE), exist_ok=True)
    with open(NEWHIGH_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _input_newhigh_sectors():
    """交互: 输入6个板块的百日新高数据 + 全市场百日新低，返回 (sectors, new_low)"""
    cached = _load_newhigh_cache()
    if cached:
        names = ', '.join(c.get("name","?") for c in cached[:6])
        prev_low = cached[0].get("new_low", "--") if cached else "--"
        print(f"\n  [上次缓存]: 板块={names}  百日新低={prev_low}")
        r = input("  沿用上次数据? (Y/n): ").strip().lower()
        if r != 'n':
            new_low = cached[0].get("new_low", 0)
            sectors = [(c["name"], c["total"], c["new"], c["cat"]) for c in cached[:6]]
            return (sectors, new_low)

    print("\n  [百日新高数据录入] — 依次输入前3热门板块 + 前3潜在异动板块")
    print("  (留空=跳过，输入格式: 板块名称,总数,新增)")
    result = []
    for i, cat_label in enumerate(["热门板块①", "热门板块②", "热门板块③", "异动观察①", "异动观察②", "异动观察③"], 1):
        cat = "hot" if i <= 3 else "watch"
        raw = input(f"  {cat_label} (名称,总数,新增): ").strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) >= 3:
            try:
                result.append((parts[0], int(parts[1]), int(parts[2]), cat))
            except:
                print("    格式错误，跳过")

    # 百日新低
    new_low_raw = input("\n  全市场百日新低 (留空=默认0): ").strip()
    new_low = 0
    try: new_low = int(new_low_raw) if new_low_raw else 0
    except: pass

    if result:
        cache_data = [{"name": r[0], "total": r[1], "new": r[2], "cat": r[3], "new_low": new_low} for r in result]
        _save_newhigh_cache(cache_data)
    return (result, new_low)


# ======================== 历史记录 ========================
HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "history")


def _save_history(briefing, poster_path, new_high_sectors):
    """保存简报JSON+海报HTML到历史记录"""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    # 保存简报JSON
    record = {
        "date": date_str,
        "generated_at": briefing.get("generated_at", ""),
        "market_state": briefing.get("market_state"),
        "market_style": briefing.get("market_style"),
        "market_stats": briefing.get("market_stats"),
        "mainline_sectors": briefing.get("mainline_sectors"),
        "all_sectors": briefing.get("all_sectors"),
        "sentiment_dragons": briefing.get("sentiment_dragons"),
        "trend_leaders": briefing.get("trend_leaders"),
        "config": briefing.get("config"),
        "new_high_sectors": [{"name": s[0], "total": s[1], "new": s[2], "cat": s[3]} for s in (new_high_sectors or [])],
    }
    json_path = os.path.join(HISTORY_DIR, f"{date_str}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    # 复制海报HTML
    if poster_path and os.path.exists(poster_path):
        import shutil
        html_path = os.path.join(HISTORY_DIR, f"{date_str}.html")
        shutil.copy2(poster_path, html_path)

    return json_path


def _list_history():
    """列出所有历史记录，按日期降序"""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    entries = []
    for f in os.listdir(HISTORY_DIR):
        if f.endswith(".json") and f[:8].isdigit():  # YYYYMMDD.json
            date_str = f[:8]
            json_path = os.path.join(HISTORY_DIR, f)
            html_path = os.path.join(HISTORY_DIR, f"{date_str}.html")
            try:
                with open(json_path, "r", encoding="utf-8") as fh:
                    rec = json.load(fh)
                ms = rec.get("market_stats", {})
                ml = rec.get("mainline_sectors", {}).get("list", [])
                entries.append({
                    "date": date_str,
                    "generated_at": rec.get("generated_at", ""),
                    "state": rec.get("market_state", {}).get("state", "?"),
                    "volume": ms.get("volume_yi", "--"),
                    "limit_up": ms.get("limit_up", "--"),
                    "mainline": [s["name"] for s in ml[:3]],
                    "has_html": os.path.exists(html_path),
                })
            except:
                pass
    entries.sort(key=lambda x: x["date"], reverse=True)
    return entries


def _regenerate_history(date_str):
    """从历史JSON重新生成海报并打开"""
    json_path = os.path.join(HISTORY_DIR, f"{date_str}.json")
    if not os.path.exists(json_path):
        print(f"  {date_str} 无历史记录")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        rec = json.load(f)

    from poster_generator import generate_poster, parse_new_high_pool
    briefing = {
        "market_state": rec.get("market_state"),
        "market_style": rec.get("market_style"),
        "mainline_sectors": rec.get("mainline_sectors"),
        "all_sectors": rec.get("all_sectors"),
        "sentiment_dragons": rec.get("sentiment_dragons", []),
        "trend_leaders": rec.get("trend_leaders", []),
        "buy_point_alerts": [],
        "action_summary": f"{date_str} 历史简报",
        "config": rec.get("config", {
            "rps_threshold": 90, "rps_warn": 80, "rps_exit": 70,
            "launch_volume_shrink": 0.5, "relay_volume_shrink": 0.6,
            "relay_min_gain": 0.15, "max_positions": 3,
            "trend_leader_min_cap": ">100亿", "trend_leader_min_amt": ">5亿",
        }),
        "market_stats": rec.get("market_stats", {}),
        "generated_at": rec.get("generated_at", date_str),
    }

    new_high_sectors = [
        (s["name"], s["total"], s["new"], s.get("cat", "hot"))
        for s in rec.get("new_high_sectors", [])
    ]

    html = generate_poster(briefing, new_high_sectors=new_high_sectors or None)

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    # 加载当日潜力股池
    nhp_pool_path = os.path.join(desktop, "百日新高潜力股池.md")
    if os.path.exists(nhp_pool_path):
        try:
            from poster_generator import parse_new_high_pool
            nhp = parse_new_high_pool(nhp_pool_path)
            html = generate_poster(briefing, new_high_sectors=new_high_sectors or None, new_high_pool=nhp)
        except:
            pass
    fpath = os.path.join(desktop, f"波段交易模型简报_{date_str}.html")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已生成: {fpath}")
    import webbrowser
    webbrowser.open("file://" + fpath)


# ======================== 历史浏览模式 ========================
def _history_browser():
    """交互式历史记录浏览器"""
    entries = _list_history()
    if not entries:
        print("\n  暂无历史记录")
        return

    page = 0
    page_size = 5
    total = len(entries)

    while True:
        os.system("cls" if os.name == "nt" else "clear")
        start = page * page_size
        batch = entries[start:start + page_size]

        print(f"\n   历史简报 ({page+1}/{(total-1)//page_size+1}) 共{total}条")
        print(f"  {'='*58}")
        print(f"  {'日期':<12} {'状态':<8} {'成交量':<10} {'涨停':<8} {'主线'}")
        print(f"  {'-'*58}")
        for e in batch:
            ml_str = ", ".join(e["mainline"][:2]) if e["mainline"] else "无"
            flag = " " if e["has_html"] else ""
            print(f"  {e['date']:<12} {e['state']:<8} {str(e['volume']):<10} {str(e['limit_up']):<8} {ml_str[:20]}{flag}")
        print(f"  {'-'*58}")
        print(f"  [N]下一页  [P]上一页  [输入日期查看]  [Q]退出")
        cmd = input(f"  > ").strip().lower()

        if cmd == "q":
            break
        elif cmd == "n" and (page + 1) * page_size < total:
            page += 1
        elif cmd == "p" and page > 0:
            page -= 1
        elif cmd and len(cmd) == 8 and cmd.isdigit():
            _regenerate_history(cmd)
            input("  按回车继续...")
        elif cmd and len(cmd) == 10 and "-" in cmd:
            _regenerate_history(cmd.replace("-", ""))
            input("  按回车继续...")


# ======================== MAIN ========================
def main():
    # 历史模式
    if len(sys.argv) > 1 and sys.argv[1] in ("--history", "-h", "history", "h"):
        _history_browser()
        return

    today = datetime.now()
    print(f"\n  [{today.strftime('%Y-%m-%d %H:%M')}] 波段交易模型每日运行")
    print(f"  ===============================================")

    # 交易日检查
    if not is_trading_day():
        print(f"  今天不是交易日或数据未就绪，跳过推送")
        return

    # 百日新高数据
    new_high_sectors, new_low = _input_newhigh_sectors()
    if not new_high_sectors:
        new_high_sectors = None

    # 生成简报（传入百日新高数据以修正RPS）
    print(f"  [1/4] 生成简报...", end=" ")
    sys.stdout.flush()
    briefing = generate_briefing(new_high_data=new_high_sectors, new_low=new_low)
    print("完成")

    # 生成海报
    print(f"  [2/4] 生成海报...", end=" ")
    sys.stdout.flush()
    from poster_generator import save_poster, parse_new_high_pool
    nhp_path = os.path.join(os.path.expanduser("~"), "Desktop", "百日新高潜力股池.md")
    nhp = parse_new_high_pool(nhp_path) if os.path.exists(nhp_path) else None
    poster_path = save_poster(briefing, new_high_sectors=new_high_sectors, new_high_pool=nhp)
    print(f"完成 -> {poster_path.split(os.sep)[-1]}")

    # 保存历史记录
    _save_history(briefing, poster_path, new_high_sectors)

    # 格式化
    wechat_text = format_wechat_summary(briefing)
    email_text = format_email_full(briefing)

    # 加载通知配置
    ncfg = _load_notify_config()

    # 推送微信
    print(f"  [3/4] 推送微信...", end=" ")
    sys.stdout.flush()
    if ncfg.get("enable_wechat") and ncfg.get("pushplus_token"):
        ok = push_wechat("波段交易模型 · 每日简报", wechat_text, ncfg["pushplus_token"])
        print(f"{'完成' if ok else '失败'}")
    else:
        print("跳过(未配置)")

    # 发送邮件
    print(f"  [4/4] 发送邮件...", end=" ")
    sys.stdout.flush()
    if ncfg.get("enable_email") and ncfg.get("smtp_pass"):
        ok = send_email(f"波段交易模型简报 {today.strftime('%Y-%m-%d')}", email_text, ncfg)
        print(f"{'完成' if ok else '失败'}")
    else:
        print("跳过(未配置)")

    # 同时打印到控制台
    print(f"\n{email_text}")
    print(f"\n  推送完成。")

if __name__ == "__main__":
    main()
