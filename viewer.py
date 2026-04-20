from flask import Flask, render_template_string
import requests

app = Flask(__name__)

wallet = "0xa4b366ad22fc0d06f1e934ff468e8922431a87b8"

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Polymarket Live Trades</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { font-family: Arial; background: #111; color: white; }
        .trade { padding: 10px; margin: 10px; border-radius: 8px; }
        .buy { background: #1e7e34; }
        .sell { background: #a71d2a; }
    </style>
</head>
<body>
    <h1>📊 Live Trades</h1>
    {% for trade in trades %}
        <div class="trade {{ 'buy' if trade.side == 'BUY' else 'sell' }}">
            <b>{{ trade.side }} {{ trade.outcome }}</b><br>
            {{ trade.title }}<br>
            Price: {{ trade.price }} | Size: {{ trade.size }}
        </div>
    {% endfor %}
</body>
</html>
"""

@app.route("/")
def home():
    url = f"https://data-api.polymarket.com/trades?user={wallet}"
    res = requests.get(url)
    trades = res.json()[:20]  # latest 20 trades
    return render_template_string(HTML, trades=trades)

app.run(debug=True)