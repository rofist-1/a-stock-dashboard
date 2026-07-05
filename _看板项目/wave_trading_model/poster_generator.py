# -*- coding: utf-8 -*-
"""
精美 HTML 简报海报生成器
"""
import os, json, uuid, sys
from datetime import datetime
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
import config
import sector_analysis

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

# ── 颜色定义 ──
C_RESONANCE = "#22c55e"   # 三线共振 - 绿
C_WATCH     = "#f59e0b"   # 观察 - 黄
C_FALLBACK  = "#64748b"   # 无数据 - 灰
C_GOOD      = "#16a34a"   # 达标
C_FAIL      = "#ef4444"   # 未达标
C_MAIN_BG   = "#0b1120"   # 主背景
C_CARD_BG   = "#131c31"   # 卡片背景
C_BORDER    = "#1e2d4a"   # 边框
C_TEXT      = "#e2e8f0"   # 主文字
C_MUTED     = "#64748b"   # 次要文字


def _rps_color(r):
    if r is None: return C_FALLBACK
    try: r = float(r)
    except: return C_FALLBACK
    if r >= 90:  return "#22c55e"
    if r >= 80:  return "#eab308"
    if r >= 60:  return "#f97316"
    return "#ef4444"

def _form_color(f):
    if f == "缩量回踩": return "#3b82f6"
    if f == "强势上攻": return "#22c55e"
    if f == "高位横盘": return "#f59e0b"
    return "#64748b"

def _nh_diff_color(v):
    try:
        d = int(v)
        return "#22c55e" if d > 0 else "#ef4444" if d < 0 else "#94a3b8"
    except:
        return "#64748b"

def _tag(t, c="#2563eb"):
    return f'<span style="display:inline-block;background:{c}22;color:{c};padding:1px 10px;border-radius:20px;font-size:0.7rem;font-weight:600;letter-spacing:0.3px;">{t}</span>'

def _cell(v, align="center"):
    return f'<td style="text-align:{align};padding:6px 8px;border-bottom:1px solid #1e2d4a;font-size:0.82rem;">{v}</td>'

def parse_new_high_pool(md_path):
    """解析百日新高潜力股池.md"""
    import re
    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()
    date_match = re.search(r'##\s*(\d{4}-\d{2}-\d{2})', text)
    pool_date = date_match.group(1) if date_match else "未知日期"
    summary_match = re.search(r'## .*?\n\n(.*?)\n\n###', text, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else ""
    tiers = []
    tier_sections = re.split(r'(###\s*Tier\s*\d\s*★+.*?)(?=\n)', text)
    for i in range(1, len(tier_sections)-1, 2):
        header = tier_sections[i].strip()
        body = tier_sections[i+1] if i+1 < len(tier_sections) else ""
        tier_match = re.match(r'###\s*Tier\s*(\d)\s*(★+)\s*(.*)', header)
        if not tier_match: continue
        tier_level = int(tier_match.group(1))
        tier_stars = tier_match.group(2)
        tier_desc = tier_match.group(3).strip()
        rows = []
        lines = body.strip().split('\n')
        in_table = False
        for line in lines:
            if line.startswith('|') and line.endswith('|'):
                cells = [c.strip() for c in line.split('|')[1:-1]]
                if not in_table:
                    if any(c in ' '.join(cells) for c in ['代码', '名称', '收盘']):
                        in_table = True
                    continue
                if cells and all(c.replace('-','') == '' for c in cells):
                    continue
                if cells and len(cells) >= 6:
                    rows.append({
                        "code": cells[0], "name": cells[1],
                        "ma60_dist": cells[2], "volume_ratio": cells[3],
                        "turnover": cells[4], "market_cap": cells[5],
                        "concept": cells[6] if len(cells) > 6 else "",
                    })
        if rows:
            tiers.append({"level": tier_level, "stars": tier_stars, "desc": tier_desc, "stocks": rows})
    comment_match = re.search(r'\*\*总评\*\*[：:](.*?)(?:\n---|\n$|$)', text, re.DOTALL)
    total_comment = comment_match.group(1).strip() if comment_match else ""
    return {"date": pool_date, "summary": summary, "tiers": tiers, "total_comment": total_comment}

def generate_poster(briefing, new_high_sectors=None, new_high_pool=None):
    """
    生成精致简报海报 HTML
    new_high_sectors: [("板块名", 总数, 新增, "hot|watch"), ...] 用户百日新高数据
    """
    ms = briefing["market_state"]
    mst = briefing["market_style"]
    all_sectors = briefing.get("all_sectors", [])
    mainline_sectors = briefing["mainline_sectors"]["list"]
    sentiment = briefing.get("sentiment_dragons", [])
    market_stats = briefing.get("market_stats", {})

    # 用 market_stats 覆盖大盘顶栏的不准确数据
    ms_vol = market_stats.get("volume_yi", ms.get("turnover_yi", "--"))
    if ms_vol != "--": ms_vol = f"{ms_vol:.0f}" if isinstance(ms_vol, (int,float)) else ms_vol
    ms_zu = market_stats.get("limit_up", "--")
    ms_zd = market_stats.get("limit_down", "--")
    ms_zhadian = market_stats.get("zhadian", "--")
    ms_fbrate = market_stats.get("fengban_rate", "--")
    ms_lb = market_stats.get("lianban", "--")
    ms_nh = market_stats.get("new_high", "--")
    ms_nl = market_stats.get("new_low", "--")
    ms_diff = market_stats.get("new_high_diff", "--")
    if ms_diff == "--" and ms_nh != "--" and ms_nl != "--":
        try: ms_diff = int(ms_nh) - int(ms_nl)
        except: pass
    trend = briefing.get("trend_leaders", [])
    action = briefing["action_summary"]
    cfg = briefing["config"]
    gen_time = briefing["generated_at"]

    # ── 状态列格式化 ──
    state_color = "#22c55e" if ms["state"] == "上涨市" else "#f59e0b" if ms["state"] == "震荡市" else "#ef4444"
    pos_limit = ms["position_limit_text"]
    temp = mst["market_temperature"]
    temp_color = "#22c55e" if temp >= 60 else "#eab308" if temp >= 30 else "#ef4444"

    # ── RPS Table ──
    rps_rows = ""
    for s in all_sectors:
        r10 = f"{s['rps_10']:.0f}" if s.get("rps_10") else "--"
        r20 = f"{s['rps_20']:.0f}" if s.get("rps_20") else "--"
        r60 = f"{s['rps_60']:.0f}" if s.get("rps_60") else "--"
        res = "●" if s.get("three_resonance") else "○"
        res_c = C_RESONANCE if s.get("three_resonance") else C_MUTED
        lu = str(s.get("limit_up_num", 0))
        boost = s.get("rps_nh_boost", 0)
        boost_badge = f' <span style="font-size:0.65rem;color:#8b5cf6;">+{boost:.0f}</span>' if boost > 0 else ""
        rps_rows += f"""<tr>
          {_cell(f'{s["name"]}{boost_badge}', "left")}
          {_cell(f'<span style="color:{_rps_color(r10)};font-weight:700;">{r10}</span>')}
          {_cell(f'<span style="color:{_rps_color(r20)};font-weight:700;">{r20}</span>')}
          {_cell(f'<span style="color:{_rps_color(r60)};font-weight:700;">{r60}</span>')}
          {_cell(f'<span style="color:{res_c};font-size:1.1rem;">{res}</span>')}
          {_cell(lu)}
        </tr>"""

    # ── 主线板块 ──
    main_rows = ""
    for s in mainline_sectors:
        r10 = f"{s['rps_10']:.0f}" if s.get("rps_10") else "--"
        r20 = f"{s['rps_20']:.0f}" if s.get("rps_20") else "--"
        r60 = f"{s['rps_60']:.0f}" if s.get("rps_60") else "--"
        res = "Y" if s.get("three_resonance") else "."
        res_c = C_RESONANCE if s.get("three_resonance") else C_MUTED
        lu = str(s.get("limit_up_num", 0))
        nh = s.get("new_high_100d", "?")
        main_rows += f"""<tr>
          {_cell(f'<span style="font-weight:600;">{s["name"]}</span>', "left")}
          {_cell(f'<span style="color:{_rps_color(r10)}">{r10}</span>')}
          {_cell(f'<span style="color:{_rps_color(r20)}">{r20}</span>')}
          {_cell(f'<span style="color:{_rps_color(r60)}">{r60}</span>')}
          {_cell(f'<span style="color:{res_c};font-weight:700;">{res}</span>')}
          {_cell(lu)}
          {_cell(f'<span style="font-weight:600;">{nh}</span>')}
        </tr>"""

    # ── 百日新高交叉验证 ──
    new_high_html = ""
    if new_high_sectors and len(new_high_sectors) > 0:
        nh_rows = ""
        for i, (name, total, nd, cat) in enumerate(new_high_sectors):
            cat_label = "热门" if cat == "hot" else "异动"
            cat_c = "#16a34a" if cat == "hot" else "#f59e0b"
            # RPS 交叉查找
            rps_match = None
            existing_names = [s["name"] for s in all_sectors]
            resolved = sector_analysis._name_resolve(name, existing_names)
            if resolved:
                for s in all_sectors:
                    if s["name"] == resolved:
                        rps_match = s
                        break
            if rps_match:
                r10v = f"{rps_match['rps_10']:.0f}" if rps_match.get("rps_10") else "--"
                r20v = f"{rps_match['rps_20']:.0f}" if rps_match.get("rps_20") else "--"
                r60v = f"{rps_match['rps_60']:.0f}" if rps_match.get("rps_60") else "--"
                r10raw = f"{rps_match['rps_10_raw']:.0f}" if rps_match.get("rps_10_raw") else r10v
                r20raw = f"{rps_match['rps_20_raw']:.0f}" if rps_match.get("rps_20_raw") else r20v
                r60raw = f"{rps_match['rps_60_raw']:.0f}" if rps_match.get("rps_60_raw") else r60v
                boost = rps_match.get("rps_nh_boost", 0)
                res3 = rps_match.get("three_resonance", False)
                cross = _tag("三线共振", C_RESONANCE) if res3 else _tag("观察", C_WATCH)
                if boost > 0:
                    rps_str = f'<span style="font-size:0.7rem;color:#64748b;">({r10raw}/{r20raw}/{r60raw})</span> <span style="color:{_rps_color(r10v)}">{r10v}</span>/<span style="color:{_rps_color(r20v)}">{r20v}</span>/<span style="color:{_rps_color(r60v)}">{r60v}</span>'
                    boost_tag = _tag(f"+{boost:.0f}新高", "#8b5cf6")
                else:
                    rps_str = f'<span style="color:{_rps_color(r10v)}">{r10v}</span>/<span style="color:{_rps_color(r20v)}">{r20v}</span>/<span style="color:{_rps_color(r60v)}">{r60v}</span>'
                    boost_tag = ""
            else:
                rps_str = '<span style="color:#64748b;">--/--/--</span>'
                cross = _tag("未收录", C_MUTED)
                boost_tag = ""
            nh_rows += f"""<tr>
              {_cell(f'<span style="font-weight:600;">{name}</span>', "left")}
              {_cell(_tag(cat_label, cat_c))}
              {_cell(f'<span style="font-weight:600;">{total}</span>')}
              {_cell(f'<span style="font-weight:600;color:#22c55e;">{nd}</span>')}
              {_cell(rps_str)}
              {_cell(cross)}
              {_cell(boost_tag)}
            </tr>"""
        new_high_html = f"""
        <div class="section">
          <div class="section-title">📊 百日新高板块排名 × RPS 交叉验证</div>
          <div style="font-size:0.75rem;color:#64748b;margin:-4px 0 8px 0;">手动录入 → 自动比对RPS系统</div>
          <table class="data-table">
            <thead><tr>
              <th style="text-align:left;">板块</th><th>分类</th><th>百日新高</th><th>新增</th><th>RPS10/20/60</th><th>RPS判定</th><th>新高加成</th>
            </tr></thead>
            <tbody>{nh_rows}</tbody>
          </table>
          <div style="margin-top:8px;font-size:0.73rem;color:#64748b;">
            <b>交叉规则：</b>百日新高排名靠前 + RPS三线共振 = 最强方向 |
            百日新高靠前但RPS未共振 = 潜在分歧 |
            百日新高在异动区提前出现 = RPS同步前的领先信号
          </div>
        </div>
        """
    else:
        new_high_html = f"""
        <div class="section">
          <div class="section-title">📊 百日新高板块排名 × RPS 交叉验证</div>
          <div style="padding:16px;text-align:center;color:#64748b;">
            <div style="font-size:1.5rem;margin-bottom:6px;">📝</div>
            <div>运行脚本时输入今日前3大热门板块 + 前3潜在异动板块的百日新高数据</div>
            <div style="font-size:0.78rem;margin-top:4px;">输入方式: <code>python run_briefing.py</code> 后按提示操作</div>
          </div>
        </div>
        """

    # ── 市场环境参考面板 ──
    def _mv(v, suffix=""):
        if v == "--" or v is None: return '<span style="color:#64748b;">--</span>'
        return f'<span style="font-weight:600;">{v}{suffix}</span>'
    def _pct_color(pct_str):
        if pct_str == "--": return "#64748b"
        try:
            v = float(pct_str.replace("%","").replace("+",""))
            return "#22c55e" if v > 0 else "#ef4444" if v < 0 else "#94a3b8"
        except: return "#64748b"
    ms_html = f"""
    <div class="section">
      <div class="section-title">📈 市场环境参考</div>
      <div style="font-size:0.75rem;color:#64748b;margin:-4px 0 8px 0;">数据来源: 自动抓取涨停/强势/指数池</div>
      <table class="data-table">
        <thead><tr>
          <th>日期</th><th>成交量(亿)</th><th>环比</th><th>涨停</th><th>环比</th><th>跌停</th><th>炸板</th><th>连板</th><th>百日新高</th><th>百日新低</th><th>差值</th><th>封板率</th>
        </tr></thead>
        <tbody><tr>
          <td>{_mv(market_stats.get("date","--"))}</td>
          <td>{_mv(market_stats.get("volume_yi"),"")}</td>
          <td style="color:{_pct_color(str(market_stats.get("volume_pct_chg","--")))};">{_mv(market_stats.get("volume_pct_chg"))}</td>
          <td style="color:#22c55e;">{_mv(market_stats.get("limit_up"))}</td>
          <td>{_mv(market_stats.get("limit_up_pct_chg"))}</td>
          <td style="color:#ef4444;">{_mv(market_stats.get("limit_down"))}</td>
          <td style="color:#f59e0b;">{_mv(market_stats.get("zhadian"))}</td>
          <td>{_mv(market_stats.get("lianban"))}</td>
          <td style="color:#8b5cf6;">{_mv(market_stats.get("new_high"))}</td>
          <td style="color:#94a3b8;">{_mv(market_stats.get("new_low"))}</td>
          <td style="color:{_nh_diff_color(market_stats.get("new_high_diff","--"))};">{_mv(market_stats.get("new_high_diff"))}</td>
          <td>{_mv(market_stats.get("fengban_rate"))}</td>
        </tr></tbody>
      </table>
    </div>
    """

    # ── 情绪龙头 ──
    sent_html = ""
    sent_found = False
    for sd in sentiment:
        dragons = sd.get("dragons", [])
        if not dragons: continue
        sent_found = True
        sent_html += f'<div style="margin-bottom:4px;"><span style="font-weight:600;">{sd["sector_name"]}:</span></div>'
        for d in dragons[:3]:
            lu_tag = ""
            if d.get("is_limit_up_today"):
                cn = d.get("continue_num", 0)
                if cn > 1: lu_tag = _tag(f"{cn}连板", "#ef4444")
                else: lu_tag = _tag("涨停", "#22c55e")
            rt = (d.get("reason_type") or "")[:20]
            sent_html += f'<div style="display:flex;align-items:center;gap:6px;padding:2px 0;font-size:0.82rem;">'
            sent_html += f'<span style="font-weight:600;">{d["name"]}</span>'
            sent_html += f'<span style="color:#94a3b8;">评分{d["dragon_score"]}</span>'
            sent_html += lu_tag
            if rt: sent_html += f'<span style="color:#64748b;font-size:0.75rem;">{rt}</span>'
            sent_html += '</div>'
    if not sent_found:
        sent_html = '<div style="padding:8px;text-align:center;color:#64748b;font-size:0.82rem;">无情绪龙头数据</div>'

    # ── 趋势中军 ──
    tl_html = ""
    tl_found = False
    for ts in trend:
        leaders = ts.get("trend_leaders", [])
        if not leaders: continue
        tl_found = True
        qual = ts.get("qualified_count", 0)
        total = ts.get("total_candidates", 0)
        tl_html += f'<div style="margin-bottom:6px;"><span style="font-weight:600;">{ts["sector_name"]}</span> <span style="color:#64748b;font-size:0.78rem;">(合格{qual}/{total})</span></div>'
        for s in leaders:
            tag_c = C_GOOD if s.get("qualified") else C_FAIL
            tag_icon = "●" if s.get("qualified") else "○"
            cap = f"{s['market_cap_yi']:.0f}亿" if s.get("market_cap_yi") else "--"
            amt = f"{s['amount_5d_yi']:.1f}亿" if s.get("amount_5d_yi") else "--"
            ma_d = f"{s['ma_distance_pct']:+.1f}%" if s.get("ma_distance_pct") is not None else "--"
            form = s.get("ma_form", "?")
            form_c = _form_color(form)
            pat = ""
            if s.get("has_pullback_pattern"):
                pat = ' <span style="color:#3b82f6;font-size:0.75rem;">⤵ 回踩线</span>'
            tl_html += f'<div style="display:flex;align-items:center;gap:6px;padding:2px 0;font-size:0.82rem;">'
            tl_html += f'<span style="color:{tag_c};">{tag_icon}</span>'
            tl_html += f'<span style="font-weight:600;">{s["name"]}</span>'
            tl_html += f'<span style="color:#94a3b8;">评分{s["total_score"]:.0f}</span>'
            tl_html += f'<span style="color:#64748b;font-size:0.78rem;">流通{cap}</span>'
            tl_html += f'<span style="color:#64748b;font-size:0.78rem;">成交{amt}</span>'
            tl_html += f'<span style="color:#64748b;font-size:0.78rem;">MA20{ma_d}</span>'
            tl_html += f'<span style="display:inline-block;background:{form_c}22;color:{form_c};padding:0 8px;border-radius:10px;font-size:0.7rem;font-weight:600;">{form}</span>'
            tl_html += pat
            tl_html += '</div>'
            if s.get("fails"):
                for f in s["fails"][:2]:
                    tl_html += f'<div style="padding-left:28px;font-size:0.7rem;color:#ef4444;">✗ {f}</div>'
    if not tl_found:
        tl_html = '<div style="padding:8px;text-align:center;color:#64748b;font-size:0.82rem;">无趋势中军数据</div>'

    # ── 百日新高潜力股池 ──
    pool_html = ""
    if new_high_pool:
        tiers = new_high_pool.get("tiers", [])
        if tiers:
            tier_colors = {1: "#22c55e", 2: "#3b82f6", 3: "#f59e0b"}
            for t in tiers:
                lv = t["level"]
                pool_html += f'<div style="margin-top:10px;"><span style="font-weight:700;color:{tier_colors.get(lv,"#94a3b8")};">Tier {lv} {t["stars"]}</span> <span style="color:#94a3b8;font-size:0.78rem;">{t["desc"]}</span></div>'
                for st in t["stocks"]:
                    cap = st.get("market_cap", "?")
                    ma60 = st.get("ma60_dist", "")
                    vr = st.get("volume_ratio", "")
                    tr = st.get("turnover", "")
                    conc = st.get("concept", "")
                    pool_html += f'<div style="display:flex;align-items:center;gap:6px;padding:2px 0;font-size:0.82rem;flex-wrap:wrap;">'
                    pool_html += f'<span style="font-weight:600;">{st["name"]}</span>'
                    pool_html += f'<span style="color:#64748b;font-size:0.78rem;">{st["code"]}</span>'
                    pool_html += f'<span style="color:{_rps_color(int(float(ma60.replace("%","").replace("+",""))))}">{ma60}</span>'
                    pool_html += f'<span style="color:#64748b;font-size:0.78rem;">量{vr}</span>'
                    pool_html += f'<span style="color:#64748b;font-size:0.78rem;">换{tr}</span>'
                    pool_html += f'<span style="color:#64748b;font-size:0.78rem;">{cap}亿</span>'
                    if conc:
                        pool_html += f'<span style="color:#60a5fa;font-size:0.75rem;">{conc}</span>'
                    pool_html += '</div>'
            if new_high_pool.get("total_comment"):
                pool_html += f'<div style="margin-top:6px;font-size:0.8rem;color:#eab308;border-top:1px solid #1e2d4a;padding-top:6px;">{new_high_pool["total_comment"]}</div>'
        else:
            pool_html = '<div style="color:#64748b;font-size:0.82rem;">无潜力股数据</div>'
    else:
        pool_html = '<div style="padding:8px;text-align:center;color:#64748b;font-size:0.82rem;">请在桌面维护 百日新高潜力股池.md 文件</div>'

    # ── HTML 组装 ──
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>波段交易模型 · 每日简报海报 {datetime.now().strftime("%Y-%m-%d")}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; font-family:'Segoe UI','Inter','PingFang SC','Microsoft YaHei',system-ui,sans-serif; }}
  body {{ background:linear-gradient(135deg,#0b1120,#131c31,#0f172a); min-height:100vh; padding:20px; color:#e2e8f0; }}
  .poster {{ max-width:1000px; margin:0 auto; display:flex; flex-direction:column; gap:16px; }}
  /* header */
  .header {{ background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%); border-radius:20px; padding:24px 28px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; box-shadow:0 8px 32px rgba(37,99,235,0.15); }}
  .header h1 {{ font-size:1.6rem; font-weight:700; color:#fff; }}
  .header .date {{ font-size:0.85rem; color:#93c5fd; background:rgba(255,255,255,0.1); padding:4px 16px; border-radius:20px; }}
  /* cards */
  .card {{ background:#131c31; border:1px solid #1e2d4a; border-radius:16px; padding:18px 22px; box-shadow:0 4px 20px rgba(0,0,0,0.2); }}
  .section {{ margin-bottom:14px; }}
  .section:last-child {{ margin-bottom:0; }}
  .section-title {{ font-size:0.95rem; font-weight:700; color:#e2e8f0; margin-bottom:8px; display:flex; align-items:center; gap:6px; }}
  .section-line {{ height:2px; background:linear-gradient(90deg,#1e2d4a,transparent); margin:4px 0 10px 0; }}
  /* grid */
  .env-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px; }}
  .env-item {{ background:rgba(255,255,255,0.04); border-radius:12px; padding:10px 12px; text-align:center; }}
  .env-label {{ font-size:0.62rem; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; }}
  .env-value {{ font-size:1.3rem; font-weight:700; margin-top:2px; }}
  /* tables */
  .data-table {{ width:100%; border-collapse:collapse; font-size:0.82rem; }}
  .data-table th {{ text-align:center; padding:6px 8px; color:#64748b; font-size:0.65rem; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; border-bottom:2px solid #1e2d4a; }}
  .data-table td {{ padding:6px 8px; border-bottom:1px solid rgba(30,45,74,0.5); font-size:0.82rem; text-align:center; }}
  .data-table tr:last-child td {{ border-bottom:none; }}
  .data-table tr:hover td {{ background:rgba(255,255,255,0.02); }}
  /* action bar */
  .action-bar {{ background:linear-gradient(135deg,#1e293b,#0f172a); border:1px solid #334155; border-radius:14px; padding:12px 18px; text-align:center; font-size:0.88rem; }}
  /* footer */
  .footer {{ text-align:center; padding:10px; font-size:0.7rem; color:#475569; }}
  @media (max-width:640px) {{ body {{ padding:10px; }} .header {{ padding:16px; }} .header h1 {{ font-size:1.2rem; }} .card {{ padding:12px 14px; }} }}
</style>
</head>
<body>
<div class="poster">

  <!-- 头部 -->
  <div class="header">
    <div>
      <h1>波段交易模型 · 每日简报</h1>
      <div style="font-size:0.78rem;color:#93c5fd;margin-top:4px;">{gen_time}</div>
    </div>
    <div style="text-align:right;">
              <div style="font-size:1.8rem;font-weight:700;color:#fff;">{ms['latest_price'] if ms['latest_price'] is not None else '--'}</div>
              <div style="font-size:0.75rem;color:#93c5fd;">{ms['index_name'] or '上证指数'} · MA20 {ms['ma20'] if ms['ma20'] is not None else '--'}</div>
    </div>
  </div>

  <!-- 市场环境 -->
  <div class="card">
    <div class="section-title">📡 大盘环境 · 仓位管理</div>
    <div class="section-line"></div>
    <div class="env-grid">
      <div class="env-item">
        <div class="env-label">大盘状态</div>
        <div class="env-value" style="color:{state_color};">{ms['state']}</div>
      </div>
      <div class="env-item">
        <div class="env-label">仓位上限</div>
        <div class="env-value" style="color:#facc15;">{pos_limit}</div>
      </div>
      <div class="env-item">
        <div class="env-label">市场风格</div>
        <div class="env-value" style="color:#60a5fa;">{mst['style']}</div>
      </div>
      <div class="env-item">
        <div class="env-label">成交额</div>
        <div class="env-value" style="color:#a78bfa;">{ms_vol}<span style="font-size:0.6rem;color:#64748b;">亿</span></div>
      </div>
      <div class="env-item">
        <div class="env-label">涨停/跌停</div>
        <div class="env-value"><span style="color:#22c55e;">{ms_zu}</span>/<span style="color:#ef4444;">{ms_zd}</span></div>
      </div>
      <div class="env-item">
        <div class="env-label">市场温度</div>
        <div class="env-value" style="color:{temp_color};">{temp}°</div>
      </div>
    </div>
    <div style="margin-top:8px;font-size:0.75rem;color:#64748b;text-align:center;">
      炸板{ms_zhadian} · 封板率{ms_fbrate} · 连板{ms_lb} · 百日新高{ms_nh} · 新低{ms_nl} · 差值<span style="color:{_nh_diff_color(ms_diff)};font-weight:600;">{ms_diff}</span> · MA20斜率{ms['ma20_slope_pct']:+.2f}% · {ms['reason']}
    </div>
  </div>

  <!-- RPS 板块排表 -->
  <div class="card">
    <div class="section-title">📊 全部热门板块 RPS 排行</div>
    <div class="section-line"></div>
    <table class="data-table">
      <thead><tr>
        <th style="text-align:left;">板块</th><th>RPS10</th><th>RPS20</th><th>RPS60</th><th>共振</th><th>涨停</th>
      </tr></thead>
      <tbody>{rps_rows}</tbody>
    </table>
  </div>

  <!-- 主线板块 -->
  <div class="card">
    <div class="section-title">📌 主线板块 — RPS 三线判定</div>
    <div class="section-line"></div>
    <table class="data-table">
      <thead><tr>
        <th style="text-align:left;">板块</th><th>RPS10</th><th>RPS20</th><th>RPS60</th><th>共振</th><th>涨停</th><th>百日新高</th>
      </tr></thead>
      <tbody>{main_rows}</tbody>
    </table>
  </div>

  <!-- 百日新高交叉验证 -->
  {new_high_html}

  <!-- 市场环境参考 -->
  {ms_html}

  <!-- 情绪龙头 -->
  <div class="card">
    <div class="section-title">🚩 情绪信号 · 短线风向标</div>
    <div class="section-line"></div>
    {sent_html}
  </div>

  <!-- 趋势中军(精简) -->
  <div class="card">
    <div class="section-title">🎯 趋势中军 · 系统筛选</div>
    <div class="section-line"></div>
    {tl_html}
  </div>

  <!-- 百日新高潜力股池 -->
  <div class="card">
    <div class="section-title">📋 百日新高潜力股池</div>
    <div class="section-line"></div>
    <div style="font-size:0.75rem;color:#64748b;margin:-4px 0 4px 0;">来源: 桌面百日新高潜力股池.md · 手动维护 · Tier1=最佳介入窗口</div>
    {pool_html}
  </div>

  <!-- 决策摘要 -->
  <div class="action-bar">
    {action}
  </div>

  <!-- 次日预警 -->
  <div class="card">
    <div class="section-title">⏰ 次日预警</div>
    <div class="section-line"></div>
    {_next_day_warning(trend)}
  </div>

  <!-- 参数 -->
  <div style="text-align:center;font-size:0.7rem;color:#475569;padding:8px;">
    RPS>{cfg['rps_threshold']} | 预警RPS10<{cfg['rps_warn']} | 缩量<{cfg['launch_volume_shrink']}/{cfg['relay_volume_shrink']} | 中继>={cfg['relay_min_gain']} | 最多{cfg['max_positions']}只
    <br>趋势中军: 流通市值{cfg['trend_leader_min_cap']} | 日均额{cfg['trend_leader_min_amt']} | 拒绝连板 | 价在MA20上+MA20向上
  </div>

  <div class="footer">
    波段交易模型 · 情绪龙头(风向标) + 趋势中军(系统筛选) + 百日新高潜力股池(手工维护) · 等待是交易的一部分
  </div>

</div>
</body>
</html>"""

    return html


def _next_day_warning(trend):
    warns = []
    for ts in trend:
        for s in ts.get("trend_leaders", []):
            if s.get("qualified") and s.get("ma_form") == "\u7f29\u91cf\u56de\u8c03":
                cap = f"{s['market_cap_yi']:.0f}\u4ebf" if s.get("market_cap_yi") else "--"
                warns.append(f'<div style="font-size:0.82rem;padding:2px 0;"><span style="font-weight:600;">{s["name"]}</span> ({ts["sector_name"]}) \u6d41\u901a{cap} \u8bc4\u5206{s["total_score"]:.0f}</div>')
    if warns:
        return "".join(warns) + '<div style="margin-top:6px;font-size:0.75rem;color:#eab308;">\u26a0 \u8bf7\u4ee5\u6b21\u65e5\u5f00\u76d8\u540e\u786e\u8ba4\u5f62\u6001\u4e3a\u51c6\uff0c\u52ff\u5728\u5c3e\u76d8\u4e70\u5165</div>'
    return '<div style="font-size:0.82rem;color:#64748b;text-align:center;">\u5f53\u524d\u65e0\u63a5\u8fd1\u4e70\u70b9\u7684\u8d8b\u52bf\u4e2d\u519b</div>'


def save_poster(briefing, filename=None, new_high_sectors=None, new_high_pool=None):
    """生成海报并保存到桌面和历史目录"""
    html = generate_poster(briefing, new_high_sectors, new_high_pool)
    today = datetime.now().strftime('%Y%m%d')

    # 1. 保存到历史目录
    hist_dir = os.path.join(_pkg_dir, "cache", "history", today)
    os.makedirs(hist_dir, exist_ok=True)
    hist_path = os.path.join(hist_dir, "poster.html")
    with open(hist_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 2. 保存到桌面
    path = None
    if filename is None:
        filename = f"\u6ce2\u6bb5\u4ea4\u6613\u6a21\u578b\u7b80\u62a5_{today}.html"
    path = os.path.join(DESKTOP, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # 3. 重建翻页看板
    rebuild_paginated_viewer()

    print(f"  \u6d77\u62a5\u5df2\u4fdd\u5b58: {path}")
    return path


def rebuild_paginated_viewer():
    """读取历史目录所有海报, 生成单文件翻页看板 -> 桌面"""
    hist_root = os.path.join(_pkg_dir, "cache", "history")
    if not os.path.isdir(hist_root):
        return

    days = sorted([d for d in os.listdir(hist_root) if d.isdigit()], reverse=True)
    if not days:
        return

    pages_html = ""
    options_html = ""
    first_day = days[0]

    for day in days:
        poster_path = os.path.join(hist_root, day, "poster.html")
        if not os.path.isfile(poster_path):
            continue
        with open(poster_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取 <body> 内容（去掉 header+footer, 只留 .poster）
        body_start = content.find('<div class="poster">')
        body_end = content.find('</div>\n</body>', body_start)
        if body_start == -1 or body_end == -1:
            body_html = content
        else:
            body_html = content[body_start:body_end + 6]

        pages_html += f'<div id="page-{day}" class="day-page">{body_html}</div>\n'
        label = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        sel = " selected" if day == first_day else ""
        options_html += f'<option value="{day}"{sel}>{label}</option>\n'

    viewer = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>波段交易模型 · 每日看板</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; font-family:'Segoe UI','Inter','PingFang SC','Microsoft YaHei',sans-serif; }}
  body {{ background:linear-gradient(135deg,#0b1120,#131c31,#0f172a); min-height:100vh; color:#e2e8f0; }}
  .nav-bar {{ position:sticky; top:0; z-index:999; background:linear-gradient(135deg,#1e3a5f,#2563eb); padding:12px 20px; display:flex; align-items:center; justify-content:center; gap:16px; box-shadow:0 4px 20px rgba(0,0,0,0.4); flex-wrap:wrap; }}
  .nav-bar .title {{ font-weight:700; font-size:1rem; color:#fff; }}
  .nav-bar button {{ background:rgba(255,255,255,0.15); border:none; color:#fff; padding:6px 16px; border-radius:8px; cursor:pointer; font-size:1rem; }}
  .nav-bar button:hover {{ background:rgba(255,255,255,0.25); }}
  .nav-bar select {{ background:rgba(255,255,255,0.15); border:none; color:#fff; padding:6px 12px; border-radius:8px; cursor:pointer; font-size:0.85rem; }}
  .nav-bar select option {{ background:#1e3a5f; color:#fff; }}
  .nav-bar .day-count {{ font-size:0.75rem; color:#93c5fd; }}
  .day-page {{ display:none; max-width:1000px; margin:16px auto; padding:0 12px; }}
  .day-page.active {{ display:block; }}
</style>
</head>
<body>
<div class="nav-bar">
  <span class="title">\u6ce2\u6bb5\u4ea4\u6613\u6a21\u578b</span>
  <button onclick="navigate(-1)">\u25c0</button>
  <select id="daySelect" onchange="goTo(this.value)">
    {options_html}
  </select>
  <button onclick="navigate(1)">\u25b6</button>
  <span class="day-count">{len(days)} \u5929\u5386\u53f2</span>
</div>
{pages_html}
<script>
  var _days = [{','.join(f"'{d}'" for d in days)}];
  var currentIdx = 0;
  function goTo(day) {{
    document.querySelectorAll('.day-page').forEach(function(p) {{ p.classList.remove('active'); }});
    var el = document.getElementById('page-' + day);
    if (el) el.classList.add('active');
    document.getElementById('daySelect').value = day;
    currentIdx = _days.indexOf(day);
  }}
  function navigate(dir) {{
    var next = currentIdx + dir;
    if (next < 0) next = 0;
    if (next >= _days.length) next = _days.length - 1;
    if (next !== currentIdx) goTo(_days[next]);
  }}
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'ArrowLeft') navigate(-1);
    if (e.key === 'ArrowRight') navigate(1);
  }});
</script>
</body>
</html>"""

    viewer_path = os.path.join(DESKTOP, "\u6ce2\u6bb5\u4ea4\u6613\u6a21\u578b\u770b\u677f.html")
    with open(viewer_path, "w", encoding="utf-8") as f:
        f.write(viewer)
    return viewer_path
