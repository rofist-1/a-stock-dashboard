import requests

token = "4377183a3f71a9eda95741cd2eb8e6a944c6fe90"
url = "https://api.cxdy.vip/api/hslb"
params = {"apiToken": token}  # 注意：用 apiToken，不是 apikey

resp = requests.get(url, params=params)
stock_list = resp.json()

print(stock_list[:10])
