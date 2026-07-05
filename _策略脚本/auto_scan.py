import akshare as ak
import pandas as pd
from datetime import datetime
import time
import os

print("正在抓取A股行情数据...")
print("============================")

# 设置重试次数
MAX_RETRIES = 3

for attempt in range(1, MAX_RETRIES + 1):
    try:
        print(f"第 {attempt} 次尝试连接数据源...")
        
        # 获取A股实时行情数据
        stock_zh_a_spot = ak.stock_zh_a_spot_em()
        
        # 筛选需要的列
        columns_to_keep = ['代码', '名称', '最新价', '涨跌幅', '涨跌额', '成交量', '成交额', '今开', '最高', '最低', '换手率']
        stock_spot = stock_zh_a_spot[columns_to_keep]
        
        # 获取今日日期
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 保存为CSV文件
        filename = f"今日数据_{today}.csv"
        stock_spot.to_csv(filename, index=False, encoding='utf-8-sig')
        
        print(f"✅ 抓取成功！")
        print(f"数据已保存到桌面：{filename}")
        print(f"共抓取 {len(stock_spot)} 只股票数据")
        print("============================")
        break  # 如果成功，跳出循环

    except Exception as e:
        print(f"❌ 第 {attempt} 次尝试失败：{e}")
        if attempt < MAX_RETRIES:
            print("正在等待 2 秒后重试...")
            time.sleep(2)
        else:
            print("\n⚠️ 重试次数已用完。建议尝试以下方法：")
            print("1. 关闭 Clash Verge 后，等一分钟再试")
            print("2. 断开当前网络，用手机热点连接电脑再试")
            print("============================")

input("\n按回车键退出...")