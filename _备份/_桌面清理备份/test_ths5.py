import akshare as ak
import time

# Try THS industry summary - might give top stocks in each board
try:
    df = ak.stock_board_industry_summary_ths(symbol="半导体")
    print(f"半导体 summary: {len(df)} rows")
    print(df.columns.tolist())
    print(df.head())
except Exception as e:
    print(f"THS summary failed: {e}")

time.sleep(2)

# Try to get concept/industry constituents from THS
try:
    df = ak.stock_board_concept_name_ths()
    print(f"\nTHS concept boards: {len(df)}")
    print(df.head())
except Exception as e:
    print(f"THS concept name failed: {e}")
