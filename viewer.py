from flask import Flask, render_template_string
import requests
from datetime import datetime, timezone
import pytz

# 🔔 TELEGRAM FUNCTION
def send_telegram(message):
    token = "8717498794:AAEvZPgqF2Vko2-_A3dRsbvUhXpabFt-T0I"   # ⚠️ replace this
    chat_id = "5042086050"

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    requests.post(url, json={
        "chat_id": chat_id,
        "text": message
    })


app = Flask(__name__)

wallet = "0xEbcd052A92fDB40644Ebd844e58722955E1dd2EF"

# store seen trades
seen_trades = set()

# CET timezone
cet = pytz.timezone("Europe/Paris")


HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Live Trades</title>
    <meta http-equiv="refresh" content="3.14">
    <style>
        body { font-family: Arial; background: #111; color: white; }
        .trade { padding: 12px; margin: 10px; border-radius: 8px; }
        .buy { background: #1e7e34; }
        .sell { background: #a71d2a; }
        .time { font-size: 12px; color: #ccc; }
    </style>
</head>
<body>
    <h1>📊 Last 3 Trades (CET)</h1>

    {% for trade in trades %}
        <div class="trade {{ 'buy' if trade.side == 'BUY' else 'sell' }}">
            <b>{{ trade.side }} {{ trade.outcome }}</b><br>
            {{ trade.title }}<br>
            Price: {{ trade.price }} | Size: {{ trade.size }}<br>
            <span class="time">Time: {{ trade.time }}</span>
        </div>
    {% endfor %}

</body>
</html>
"""


@app.route("/test")
def test():
    send_telegram("🚀 Manual test message")
    return "Test sent!"

@app.route("/")
def home():
    global seen_trades

    url = f"https://data-api.polymarket.com/trades?user={wallet}"
    res = requests.get(url)
    trades = res.json()

    # sort newest first
    trades = sorted(trades, key=lambda x: x["timestamp"], reverse=True)

    # 🔥 initialize once (avoid spam)
    if not seen_trades:
        for t in trades:
            seen_trades.add(t["transactionHash"])

    # convert time + detect new trades
    for trade in trades:
        dt = datetime.fromtimestamp(trade["timestamp"], timezone.utc)
        local_time = dt.astimezone(cet)
        trade["time"] = local_time.strftime("%d %b %H:%M:%S")

        trade_id = trade["transactionHash"]

        # 🚨 NEW TRADE
        if trade_id not in seen_trades:
            seen_trades.add(trade_id)

            # 🎯 filter (only big trades)
            if trade["size"] > 0:
                message = f"""
🚨 NEW TRADE

{trade['side']} {trade['outcome']}
{trade['title']}

💰 Price: {trade['price']}
📊 Size: {trade['size']}
🕒 {trade['time']}
"""
                send_telegram(message)

    # show only last 3 trades
    trades = trades[:3]

    return render_template_string(HTML, trades=trades)

app.run(debug=True)