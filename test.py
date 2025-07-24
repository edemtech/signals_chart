import requests
r = requests.get("https://api.binance.com/api/v3/time")
print(r.text)