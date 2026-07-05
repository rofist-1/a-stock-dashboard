import akshare as ak
import time

# Try THS industry info
try:
    df = ak.stock_board_industry_info_ths(symbol="881121")
    print(f"\n半导体 info: {len(df)}")
    print(df.to_string())
except Exception as e:
    print(f"THS industry info failed: {e}")
    import traceback
    traceback.print_exc()

time.sleep(1)

# Try THS concept info
try:
    df = ak.stock_board_concept_info_ths(symbol="881121")
    print(f"\n概念 info: {len(df)}")
    print(df.to_string())
except Exception as e:
    print(f"THS concept info failed: {e}")
