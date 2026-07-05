import akshare as ak

# THS summary without args
df = ak.stock_board_industry_summary_ths()
print(f"Columns: {df.columns.tolist()}")
print(f"Shape: {df.shape}")
print(df.head(20))
