import json

batch1 = [
    {'name':'艾艾精工', 'code':'603580', 'price':57.97, 'chg':10.00, 'sector':'实控人变更ST摘帽', 'turnover':'9.76亿', 'mainNet':'-6540万'},
    {'name':'爱丽家居', 'code':'603221', 'price':18.63, 'chg':9.98, 'sector':'并购重组地产链', 'turnover':'2093万', 'mainNet':'1220万'},
    {'name':'妙可蓝多', 'code':'600882', 'price':22.78, 'chg':5.81, 'sector':'乳业食品饮料', 'turnover':'5.27亿', 'mainNet':'1660万'},
    {'name':'米奥会展', 'code':'300795', 'price':14.22, 'chg':5.02, 'sector':'Kimi概念平台经济', 'turnover':'6.20亿', 'mainNet':'1728万'},
    {'name':'承德露露', 'code':'000848', 'price':8.87, 'chg':4.72, 'sector':'食品饮料金融概念', 'turnover':'3.60亿', 'mainNet':'-4338万'},
    {'name':'洁雅股份', 'code':'301108', 'price':34.28, 'chg':4.67, 'sector':'美容护理病毒防治', 'turnover':'1.74亿', 'mainNet':'1343万'},
    {'name':'甘咨询', 'code':'000779', 'price':12.20, 'chg':4.54, 'sector':'AI应用基础建设', 'turnover':'9.84亿', 'mainNet':'5493万'},
    {'name':'浙江鼎力', 'code':'603338', 'price':60.48, 'chg':3.90, 'sector':'工程机械基础建设', 'turnover':'5.53亿', 'mainNet':'3.06亿'},
    {'name':'森马服饰', 'code':'002563', 'price':6.15, 'chg':3.02, 'sector':'谷子经济文创产品', 'turnover':'1.84亿', 'mainNet':'2093万'},
    {'name':'唐山港', 'code':'601000', 'price':4.77, 'chg':2.58, 'sector':'港口高股息精选', 'turnover':'2.61亿', 'mainNet':'8196万'},
    {'name':'伟星股份', 'code':'002003', 'price':10.83, 'chg':2.46, 'sector':'服装家纺高股息精选', 'turnover':'2.26亿', 'mainNet':'1.33亿'},
    {'name':'中国外运', 'code':'601598', 'price':6.40, 'chg':2.24, 'sector':'航运机器人概念', 'turnover':'1.73亿', 'mainNet':'6152万'},
    {'name':'格力电器', 'code':'000651', 'price':41.65, 'chg':2.08, 'sector':'家电食品饮料', 'turnover':'30.94亿', 'mainNet':'3915万'},
    {'name':'青农商行', 'code':'002958', 'price':3.09, 'chg':1.98, 'sector':'银行破净股概念', 'turnover':'2.63亿', 'mainNet':'2.17亿'},
    {'name':'美的集团', 'code':'000333', 'price':87.01, 'chg':1.92, 'sector':'家电智能电网', 'turnover':'41.50亿', 'mainNet':'8070万'},
    {'name':'兴蓉环境', 'code':'000598', 'price':7.33, 'chg':1.52, 'sector':'垃圾发电基础建设', 'turnover':'2.10亿', 'mainNet':'-417万'},
    {'name':'地铁设计', 'code':'003013', 'price':17.10, 'chg':1.00, 'sector':'轨道交通基础建设', 'turnover':'1.05亿', 'mainNet':'-339万'},
]

batch2 = [
    {'name':'春风动力', 'code':'603129', 'price':303.00, 'chg':0.85, 'sector':'两轮车汽车类', 'turnover':'1.04亿', 'mainNet':'6.28亿'},
    {'name':'平安银行', 'code':'000001', 'price':11.28, 'chg':0.71, 'sector':'银行跨境支付', 'turnover':'6.01亿', 'mainNet':'-1.49亿'},
    {'name':'招商公路', 'code':'001965', 'price':10.56, 'chg':0.57, 'sector':'金融概念基础建设', 'turnover':'1.98亿', 'mainNet':'-217万'},
    {'name':'上港集团', 'code':'600018', 'price':5.17, 'chg':0.19, 'sector':'港口破净股概念', 'turnover':'2.72亿', 'mainNet':'-135万'},
    {'name':'招商银行', 'code':'600036', 'price':39.66, 'chg':0.18, 'sector':'银行跨境支付', 'turnover':'18.15亿', 'mainNet':'45.63亿'},
    {'name':'西部矿业', 'code':'601168', 'price':36.91, 'chg':0.14, 'sector':'有色金属金属锌', 'turnover':'7.86亿', 'mainNet':'-8966万'},
    {'name':'兴业银行', 'code':'601166', 'price':18.59, 'chg':-0.05, 'sector':'银行跨境支付', 'turnover':'7.38亿', 'mainNet':'-3892万'},
    {'name':'建设银行', 'code':'601939', 'price':10.63, 'chg':-0.09, 'sector':'银行跨境支付', 'turnover':'5.04亿', 'mainNet':'-1.13亿'},
    {'name':'工商银行', 'code':'601398', 'price':7.95, 'chg':-0.25, 'sector':'银行跨境支付', 'turnover':'15.09亿', 'mainNet':'-1.39亿'},
    {'name':'交通银行', 'code':'601328', 'price':7.09, 'chg':-0.28, 'sector':'银行金融概念', 'turnover':'5.64亿', 'mainNet':'-9022万'},
    {'name':'超卓航科', 'code':'688237', 'price':67.90, 'chg':-0.45, 'sector':'军工汽车类', 'turnover':'2.34亿', 'mainNet':'931万'},
    {'name':'长江电力', 'code':'600900', 'price':28.93, 'chg':-0.48, 'sector':'水电基础建设', 'turnover':'38.04亿', 'mainNet':'9555万'},
    {'name':'海康威视', 'code':'002415', 'price':35.74, 'chg':-1.11, 'sector':'人工智能汽车电子', 'turnover':'16.00亿', 'mainNet':'-7623万'},
    {'name':'邮储银行', 'code':'601658', 'price':5.12, 'chg':-1.54, 'sector':'银行高股息精选', 'turnover':'9.15亿', 'mainNet':'-3407万'},
    {'name':'粤高速A', 'code':'000429', 'price':14.70, 'chg':-2.07, 'sector':'金融概念高股息精选', 'turnover':'1.44亿', 'mainNet':'-767万'},
    {'name':'星帅尔', 'code':'002860', 'price':19.33, 'chg':-2.23, 'sector':'家电光储充一体化', 'turnover':'2.54亿', 'mainNet':'5050万'},
    {'name':'共进股份', 'code':'603118', 'price':16.64, 'chg':-3.87, 'sector':'交换机通信', 'turnover':'32.18亿', 'mainNet':'-1.65亿'},
]

all_stocks = batch1 + batch2
print(f"Total: {len(all_stocks)} stocks")
print(f"上涨: {sum(1 for s in all_stocks if s['chg']>0)}")
print(f"下跌: {sum(1 for s in all_stocks if s['chg']<0)}")
print(f"涨停(>=9.5%): {sum(1 for s in all_stocks if s['chg']>=9.5)}")
print()

for s in all_stocks:
    arrow = "↑" if s['chg'] > 0 else ("↓" if s['chg'] < 0 else "→")
    info = f"{s['code']} {s['name']:6s} {s['price']:7.2f} {arrow}{abs(s['chg']):5.2f}% {s['sector']:20s} T:{s['turnover']:8s} M:{s['mainNet']:8s}"
    print(info)

# Save as JSON for data.json
entry = {
    "date": "2026-07-29",
    "stocks": [{"code": s["code"], "name": s["name"], "price": s["price"], "changePct": s["chg"], "sector": s["sector"], "turnover": s["turnover"], "mainNet": s["mainNet"]} for s in all_stocks]
}
with open(r'C:\Users\Rofis\Desktop\百日新高v4.0最终版\today_batch.json', 'w', encoding='utf-8') as f:
    json.dump(entry, f, ensure_ascii=False, indent=2)
print("\nSaved to today_batch.json")