import requests
import time

wallet = "0xa4b366ad22fc0d06f1e934ff468e8922431a87b8"

last_timestamp = 0  # track latest trade

while True:
    url = f"https://data-api.polymarket.com/trades?user={wallet}"
    res = requests.get(url)
    trades = res.json()

    # sort newest first
    trades = sorted(trades, key=lambda x: x["timestamp"])

    for trade in trades:
        if trade["timestamp"] > last_timestamp:
            print("\n🚀 NEW TRADE DETECTED:")
            print(trade)

            last_timestamp = trade["timestamp"]

    time.sleep(5)  # check every 5 seconds