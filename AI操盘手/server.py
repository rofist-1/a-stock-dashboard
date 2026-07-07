# -*- coding: utf-8 -*-
"""AI操盘手 - A股分析平台 (悟道数据源)"""
import http.server
import json
import os
import sys
import time
import threading
import webbrowser
import urllib.request
import urllib.parse
from datetime import datetime

PORT = 8899
WORKDIR = os.path.dirname(os.path.abspath(__file__))
API_BASE = "https://api.cxdy.vip/api/"
API_TOKEN = "4377183a3f71a9eda95741cd2eb8e6a944c6fe90"

STOCK_CACHE = []      # [{code, name, market}]
MARKET_CACHE = {}      # {code: {name,close,pctChg,peTtm,pb,totalMv,circMv,turnover,amount,volume,open,high,low,preClose}}
CACHE_TIME = 0


def api_post(endpoint, **params):
    params["apiToken"] = API_TOKEN
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(API_BASE + endpoint, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def refresh_cache():
    global STOCK_CACHE, MARKET_CACHE, CACHE_TIME
    # 加载股票列表
    resp = api_post("hslb")
    STOCK_CACHE = []
    for item in (resp if isinstance(resp, list) else resp.get("data", [])):
        code = str(item.get("code", "")).replace("sh", "").replace("sz", "")
        name = str(item.get("name", ""))
        if code and name and code.isdigit() and len(code) == 6:
            mk = "sh" if code.startswith(("60", "68")) else "sz"
            STOCK_CACHE.append({"code": code, "name": name, "market": mk})

    # 加载实时行情
    resp = api_post("ssjy")
    rows = resp.get("data", []) if isinstance(resp, dict) else resp
    if not isinstance(rows, list):
        rows = []
    for r in rows:
        raw_code = str(r.get("代码", r.get("code", ""))).replace("sh", "").replace("sz", "")
        if not raw_code.isdigit() or len(raw_code) != 6:
            continue
        MARKET_CACHE[raw_code] = {
            "name": str(r.get("名称", r.get("name", ""))),
            "close": fmt_num(r.get("最新价", r.get("close"))),
            "pctChg": fmt_num(r.get("涨跌幅", r.get("pctChg"))),
            "change": fmt_num(r.get("涨跌额", r.get("change"))),
            "open": fmt_num(r.get("今开", r.get("open"))),
            "high": fmt_num(r.get("最高", r.get("high"))),
            "low": fmt_num(r.get("最低", r.get("low"))),
            "preClose": fmt_num(r.get("昨收", r.get("preClose"))),
            "volume": fmt_num(r.get("成交量", r.get("volume"))),
            "amount": fmt_num(r.get("成交额", r.get("amount"))),
            "turnover": fmt_num(r.get("换手率", r.get("turnoverRate"))),
            "peTtm": fmt_num(r.get("市盈率", r.get("peTtm"))),
            "pb": fmt_num(r.get("市净率", r.get("pb"))),
            "totalMv": fmt_num(r.get("总市值", r.get("totalMarketCap"))),
            "circMv": fmt_num(r.get("流通市值", r.get("circMarketCap"))),
        }
    CACHE_TIME = time.time()


def fmt_num(v):
    if v is None or v == "" or v == "-":
        return "-"
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return str(v)


def search_stocks(q):
    q = q.lower().strip()
    results = []
    for s in STOCK_CACHE:
        if q in s["name"].lower() or q == s["code"]:
            results.append(s)
            if len(results) >= 15:
                break
    results.sort(key=lambda x: (0 if q == x["code"] else 0 if q in x["name"].lower() else 1, -len(x["name"])))
    return results


# ========== HTML ==========
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI操盘手 - A股分析</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei",sans-serif;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);min-height:100vh;color:#e0e0e0;display:flex;flex-direction:column;align-items:center}
.header{text-align:center;padding:30px 20px 15px}
.header h1{font-size:32px;background:linear-gradient(90deg,#f7971e,#ffd200);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header p{color:#999;margin-top:6px;font-size:13px}
.container{width:95%;max-width:960px}
.search-box{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.15);border-radius:14px;padding:16px 20px;margin-bottom:14px;position:relative}
.search-row{display:flex;gap:10px}
.search-box input{flex:1;min-width:180px;padding:12px 16px;border-radius:10px;border:2px solid rgba(255,255,255,.2);background:rgba(255,255,255,.08);color:#fff;font-size:16px;outline:none;transition:border-color .3s;font-family:inherit}
.search-box input:focus{border-color:#f7971e}
.search-box input::placeholder{color:#666}
.search-box button{padding:12px 28px;border-radius:10px;border:none;background:linear-gradient(135deg,#f7971e,#ffd200);color:#1a1a2e;font-size:16px;font-weight:bold;cursor:pointer;transition:transform .2s;white-space:nowrap}
.search-box button:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(247,151,30,.4)}
.search-box button:disabled{opacity:.5;cursor:not-allowed;transform:none}
.hint{font-size:11px;color:#666;margin-top:6px}
.dropdown{position:absolute;left:20px;right:20px;top:54px;background:#1e1e3a;border:1px solid rgba(255,255,255,.2);border-radius:0 0 10px 10px;max-height:260px;overflow-y:auto;z-index:10;display:none}
.dropdown.show{display:block}
.dropdown-item{padding:10px 16px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,.05);display:flex;justify-content:space-between;align-items:center;transition:background .15s;font-size:14px}
.dropdown-item:hover,.dropdown-item.active{background:rgba(247,151,30,.2)}
.dropdown-item .name{color:#e0e0e0}
.dropdown-item .code{color:#888;font-size:12px}
.dropdown-item .market{font-size:11px;color:#666;margin-left:6px}

.panels{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:700px){.panels{grid-template-columns:1fr}}
.panel{background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:16px 18px}
.panel.full{grid-column:1/-1}
.panel h3{font-size:14px;color:#f7971e;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid rgba(255,255,255,.1)}
.row{display:flex;justify-content:space-between;padding:4px 0;font-size:13px;border-bottom:1px solid rgba(255,255,255,.03)}
.row .l{color:#888}.row .v{color:#e0e0e0;font-weight:500}.row .up{color:#ef4444}.row .down{color:#4ade80}
.price-large{font-size:28px!important;font-weight:bold}
.loader{text-align:center;padding:50px}.spinner{display:inline-block;width:40px;height:40px;border:3px solid rgba(255,255,255,.1);border-top-color:#f7971e;border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loader p{margin-top:12px;color:#888;font-size:13px}
.empty{text-align:center;color:#555;padding:50px;font-size:14px}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;margin:2px}
.tag-up{background:rgba(239,68,68,.2);color:#ef4444}
.tag-down{background:rgba(74,222,128,.2);color:#4ade80}
</style>
</head>
<body>
<div class="header"><h1>AI操盘手</h1><p>A股实时行情 · 悟道数据 · 更新于 <span id="cacheTime">--</span></p></div>
<div class="container">
<div class="search-box">
<div class="search-row">
<input type="text" id="codeInput" placeholder="输入股票代码或名称搜索..." autofocus autocomplete="off">
<button id="runBtn" onclick="analyze()">查看</button>
</div>
<div class="dropdown" id="dropdown"></div>
<div class="hint">支持代码和名称搜索，输入即筛选 | 点击股票查看详情</div>
</div>
<div id="loading" class="loader" style="display:none"><div class="spinner"></div><p>加载中...</p></div>
<div id="content"></div>
</div>

<script>
let timer=null,aidx=-1,results=[];
async function init(){try{const r=await fetch("/api/cache_time");const d=await r.json();document.getElementById("cacheTime").textContent=d.time||"--"}catch(e){}}
async function doSearch(){
  const q=document.getElementById("codeInput").value.trim();
  if(!q||q.length<1){closeDd();return}
  try{const r=await fetch("/api/search?q="+encodeURIComponent(q));const d=await r.json();results=d.results||[];aidx=-1;renderDd()}catch(e){closeDd()}
}
function renderDd(){
  const dd=document.getElementById("dropdown");
  if(!results.length){closeDd();return}
  let h="";results.forEach((r,i)=>{
    let cls=i===aidx?"dropdown-item active":"dropdown-item";
    let mk=r.market==="sh"?"沪":"深";
    h+=`<div class="${cls}" data-idx="${i}" onmousedown="sel(${i},event)"><span class="name">${esc(r.name)}</span><span><span class="code">${r.code}</span><span class="market">${mk}市</span></span></div>`
  });dd.innerHTML=h;dd.classList.add("show")
}
function closeDd(){document.getElementById("dropdown").classList.remove("show");results=[];aidx=-1}
function sel(i,e){e.preventDefault();const r=results[i];document.getElementById("codeInput").value=r.name+" "+r.code;closeDd();showStock(r.code)}
function esc(t){const d=document.createElement("div");d.textContent=t;return d.innerHTML}

document.getElementById("codeInput").addEventListener("input",function(){clearTimeout(timer);timer=setTimeout(doSearch,200)});
document.getElementById("codeInput").addEventListener("keydown",function(e){
  const dd=document.getElementById("dropdown");
  if(e.key==="ArrowDown"){e.preventDefault();if(!dd.classList.contains("show")){doSearch();return}aidx=Math.min(aidx+1,results.length-1);renderDd()}
  else if(e.key==="ArrowUp"){e.preventDefault();aidx=Math.max(aidx-1,-1);renderDd()}
  else if(e.key==="Enter"){
    const s=document.querySelector(".dropdown-item.active");
    if(s){e.preventDefault();const r=results[aidx];document.getElementById("codeInput").value=r.name+" "+r.code;closeDd();showStock(r.code)}
    else if(!dd.classList.contains("show")){analyze()}
  }else if(e.key==="Escape"){closeDd()}
});
document.addEventListener("click",function(e){if(!e.target.closest(".search-box"))closeDd()});

async function analyze(){
  const input=document.getElementById("codeInput").value.trim();
  if(!input)return;
  const m=input.match(/(\d{6})/);
  if(m){showStock(m[1]);return}
  if(results.length>0){showStock(results[0].code);return}
  alert("请输入6位股票代码或从列表选择")
}

async function showStock(code){
  document.getElementById("content").innerHTML="";
  document.getElementById("loading").style.display="block";
  document.getElementById("runBtn").disabled=true;
  try{
    const r=await fetch("/api/stock?code="+code);
    const d=await r.json();
    document.getElementById("loading").style.display="none";
    document.getElementById("runBtn").disabled=false;
    if(d.error){document.getElementById("content").innerHTML=`<div class="empty" style="color:#f87171">${esc(d.error)}</div>`}
    else render(d)
  }catch(e){
    document.getElementById("loading").style.display="none";
    document.getElementById("runBtn").disabled=false;
    document.getElementById("content").innerHTML=`<div class="empty" style="color:#f87171">加载失败</div>`
  }
}

function render(d){
  const pct=d.pctChg||0;
  const color=pct>=0?"up":"down";
  const sign=pct>=0?"+":"";
  const mv=d.totalMv;
  const cmv=d.circMv;

  let h=`<div class="panels"><div class="panel full">`;
  h+=`<h3>${esc(d.name||"")} (${d.code})</h3>`;
  h+=`<div class="row"><span class="l">最新价</span><span class="v ${color} price-large">${d.close||"-"}</span></div>`;
  h+=`<div class="row"><span class="l">涨跌幅</span><span class="v ${color}">${sign}${fmtPct(pct)}%</span></div>`;
  h+=`<div class="row"><span class="l">涨跌额</span><span class="v ${color}">${d.change||"-"}</span></div>`;
  h+=`<div class="row"><span class="l">今开 / 昨收</span><span class="v">${d.open||"-"} / ${d.preClose||"-"}</span></div>`;
  h+=`<div class="row"><span class="l">最高 / 最低</span><span class="v">${d.high||"-"} / ${d.low||"-"}</span></div>`;
  h+=`<div class="row"><span class="l">成交额</span><span class="v">${fmtAmt(d.amount)}</span></div>`;
  h+=`<div class="row"><span class="l">成交量</span><span class="v">${fmtVol(d.volume)}</span></div>`;
  h+=`<div class="row"><span class="l">换手率</span><span class="v">${fmtPct(d.turnover)}%</span></div>`;
  h+=`</div>`;

  // 估值面板
  h+=`<div class="panel"><h3>估值指标</h3>`;
  h+=`<div class="row"><span class="l">PE(TTM)</span><span class="v">${d.peTtm||"-"}</span></div>`;
  h+=`<div class="row"><span class="l">PB</span><span class="v">${d.pb||"-"}</span></div>`;
  h+=`<div class="row"><span class="l">总市值</span><span class="v">${fmtYi(d.totalMv)}亿</span></div>`;
  h+=`<div class="row"><span class="l">流通市值</span><span class="v">${fmtYi(d.circMv)}亿</span></div>`;
  // 估值分位解读
  let peTag="", pbTag="";
  if(d.peTtm&&d.peTtm!=="-"){
    const pe=Number(d.peTtm);
    if(pe<0)peTag=`<span class="tag tag-down">亏损</span>`;
    else if(pe<15)peTag=`<span class="tag tag-down">低估</span>`;
    else if(pe<30)peTag=`<span class="tag tag-up">合理</span>`;
    else peTag=`<span class="tag tag-up">偏高</span>`;
  }
  if(d.pb&&d.pb!=="-"){
    const pb=Number(d.pb);
    if(pb<1)pbTag=`<span class="tag tag-down">破净</span>`;
    else if(pb<3)pbTag=`<span class="tag tag-up">合理</span>`;
    else if(pb<8)pbTag=`<span class="tag tag-up">偏高</span>`;
    else pbTag=`<span class="tag tag-up">极高</span>`;
  }
  h+=`<div class="row"><span class="l">估值评价</span><span class="v">${peTag} ${pbTag}</span></div>`;
  h+=`</div></div>`;

  document.getElementById("content").innerHTML=h
}

function fmtPct(v){if(v==="-"||v===undefined)return"-";return Number(v).toFixed(2)}
function fmtAmt(v){if(v==="-"||!v)return"-";v=Number(v)/1e8;return v>=1?v.toFixed(1)+"亿":(Number(v)*1e4).toFixed(0)+"万"}
function fmtVol(v){if(v==="-"||!v)return"-";v=Number(v)/1e4;return v>=1?v.toFixed(1)+"万手":Math.round(Number(v)*1e3)+"手"}
function fmtYi(v){if(v==="-"||!v)return"-";return (Number(v)/1e8).toFixed(2)}

init();
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            self.send_html(HTML)
            return

        if parsed.path == "/api/search":
            params = urllib.parse.parse_qs(parsed.query)
            q = params.get("q", [""])[0]
            self.send_json({"results": search_stocks(q)})
            return

        if parsed.path == "/api/stock":
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [""])[0]
            data = MARKET_CACHE.get(code)
            if not data:
                self.send_json({"error": f"未找到股票 {code}"})
                return
            data["code"] = code
            self.send_json(data)
            return

        if parsed.path == "/api/cache_time":
            t = datetime.fromtimestamp(CACHE_TIME).strftime("%H:%M:%S") if CACHE_TIME else "--"
            self.send_json({"time": t})
            return

        self.send_response(404)
        self.end_headers()

    def send_html(self, content):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    print("   正在加载股票列表...", end="", flush=True)
    refresh_cache()
    print(f" OK ({len(STOCK_CACHE)}只 / {len(MARKET_CACHE)}只有行情)")

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n   AI操盘手上线: http://127.0.0.1:{PORT}")
    print(f"   在浏览器打开以上地址即可使用")
    print(f"   按 Ctrl+C 停止\n")
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n   已停止")
        server.shutdown()
