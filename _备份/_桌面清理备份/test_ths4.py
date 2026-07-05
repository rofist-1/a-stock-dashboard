import akshare as ak
import time

# Try THS industry info with name (not code)
try:
    df = ak.stock_board_industry_info_ths(symbol="半导体")
    print(f"\n半导体 info via name: {len(df)}")
    print(df.to_string())
except Exception as e:
    print(f"THS industry info via name failed: {e}")

time.sleep(2)

# Try to get industry constitution via a different approach
# Check if there's a stock_individual function that gives THS industry
try:
    # Try stock_info_a_code_name - already have this
    pass
except:
    pass

# Let's also try the cninfo approach for individual stocks
try:
    df = ak.stock_industry_category_cninfo()
    print(f"\nCNINFO: {len(df)} rows")
    print(df.columns.tolist())
    print(df.head())
except Exception as e:
    print(f"CNINFO failed: {e}")
