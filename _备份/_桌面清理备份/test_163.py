import requests as req

# Try NetEase/163 stock API
# Individual stock page  
r = req.get("http://quotes.money.163.com/1003007.html", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
r.encoding = "utf-8"
with open("netease_test.txt", "w", encoding="utf-8") as f:
    f.write(r.text[:3000])
print(f"Status: {r.status_code}, len: {len(r.text)}")

# Look for industry info
import re
for m in re.finditer(r"(行业|板块|industry).{0,60}", r.text):
    print(m.group())
