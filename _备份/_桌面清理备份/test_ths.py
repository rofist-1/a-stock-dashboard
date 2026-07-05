import akshare as ak
import time

# Try THS (同花顺) industry board - different source, might not be rate limited
try:
    df = ak.stock_board_industry_name_ths()
    print(f"THS industry boards: {len(df)}")
    print(df.head())
except Exception as e:
    print(f"THS industry name failed: {e}")

time.sleep(2)

# Try cninfo industry category
try:
    df = ak.stock_industry_category_cninfo()
    print(f"CNINFO industry categories: {len(df)}")
    print(df.head())
except Exception as e:
    print(f"CNINFO failed: {e}")

time.sleep(2)

# Try Shenwan industry classification
try:
    df = ak.stock_industry_clf_hist_sw()
    print(f"SW industry: {len(df)}")
    print(df.head())
except Exception as e:
    print(f"SW failed: {e}")
