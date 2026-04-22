from flask import Flask, render_template_string
import threading
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os

load_dotenv(override=True)

def send_telegram(message):
    token = os.getenv("TELEGRAM_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat_id in list(subscribers):
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=5)
        except Exception as e:
            print(f"Telegram error for {chat_id}: {e}")


def poll_telegram():
    """Background thread: listens for /start messages and registers subscribers."""
    token = os.getenv("TELEGRAM_TOKEN")
    url = f"https://api.telegram.org/bot{token}"
    offset = None
    print("Telegram polling started...")
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset
            res = requests.get(f"{url}/getUpdates", params=params, timeout=35)
            updates = res.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                first_name = msg.get("chat", {}).get("first_name", "there")
                if chat_id and text.strip() == "/start":
                    if chat_id not in subscribers:
                        subscribers.add(chat_id)
                        save_subscribers()
                        print(f"New subscriber: {chat_id} ({first_name})")
                        requests.post(f"{url}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": f"👋 Hey {first_name}! You're now subscribed to trade alerts. You'll get notified every time a new trade is detected."
                        }, timeout=5)
                    else:
                        requests.post(f"{url}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": "✅ You're already subscribed!"
                        }, timeout=5)
                elif chat_id and text.strip() == "/stop":
                    subscribers.discard(chat_id)
                    save_subscribers()
                    print(f"Unsubscribed: {chat_id}")
                    requests.post(f"{url}/sendMessage", json={
                        "chat_id": chat_id,
                        "text": "🔕 You've been unsubscribed. Send /start to resubscribe."
                    }, timeout=5)
        except Exception as e:
            print(f"Polling error: {e}")
            import time; time.sleep(5)


app = Flask(__name__)

wallet = "0x2a2c53bd278c04da9962fcf96490e17f3dfb9bc1"
seen_trades = set()
cet = timezone(timedelta(hours=1))  # Fixed CET = UTC+1, no DST

# Subscribers: everyone who sent /start to the bot
SUBSCRIBERS_FILE = "subscribers.txt"

def load_subscribers():
    s = set()
    if os.getenv("TELEGRAM_CHAT_ID"):
        s.add(int(os.getenv("TELEGRAM_CHAT_ID")))
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    s.add(int(line))
    return s

def save_subscribers():
    with open(SUBSCRIBERS_FILE, "w") as f:
        for chat_id in subscribers:
            f.write(str(chat_id) + "\n")

subscribers = load_subscribers()
print(f"Loaded {len(subscribers)} subscriber(s)")

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Live Trades</title>
    <meta http-equiv="refresh" content="2">
    <style>
        body { font-family: Arial; background: #111; color: white; padding: 20px; }
        .trade { padding: 12px; margin: 10px; border-radius: 8px; }
        .buy { background: #1e7e34; }
        .sell { background: #a71d2a; }
        .time { font-size: 12px; color: #ccc; }
        .error { color: #ff6b6b; padding: 10px; }
        .meta { font-size: 11px; color: #aaa; margin-top: 4px; }
    </style>
</head>
<body>
    <h1>📊 Last 3 Trades (CET)</h1>
    <p style="color:#aaa; font-size:13px;">🕒 Page loaded at: {{ now }}</p>

    {% if error %}
        <div class="error">⚠️ {{ error }}</div>
    {% endif %}

    {% if not trades %}
        <p>No trades found.</p>
    {% endif %}

    {% for trade in trades %}
        <div class="trade {{ 'buy' if trade.side == 'BUY' else 'sell' }}">
            <b>{{ trade.side }} — {{ trade.outcome }}</b><br>
            {{ trade.title }}<br>
            Price: <b>{{ trade.price }}</b> | Shares: <b>{{ trade.shares }}</b> | Value: <b>${{ trade.size }}</b><br>
            <span class="time">🕒 {{ trade.time }} &nbsp;·&nbsp; <b>{{ trade.time_ago }}</b></span>
            {% if trade.spread %}
                <div class="meta">Spread: {{ trade.spread }} | Mid: {{ trade.mid }}</div>
            {% endif %}
        </div>
    {% endfor %}

</body>
</html>
"""


def get_clob_info(token_id):
    """Fetch spread and midpoint from CLOB API for a given token."""
    if not token_id:
        return None, None
    try:
        # Get spread
        spread_res = requests.get(
            f"https://clob.polymarket.com/spread?token_id={token_id}",
            timeout=3
        )
        mid_res = requests.get(
            f"https://clob.polymarket.com/midpoint?token_id={token_id}",
            timeout=3
        )
        spread = spread_res.json().get("spread") if spread_res.ok else None
        mid = mid_res.json().get("mid") if mid_res.ok else None
        return spread, mid
    except Exception as e:
        print(f"CLOB API error: {e}")
        return None, None


def safe_timestamp(trade):
    """Safely extract and cast timestamp for sorting."""
    try:
        return float(trade.get("timestamp", 0))
    except (ValueError, TypeError):
        return 0


def format_trade(trade):
    """Convert timestamp and normalize fields on a trade dict."""
    try:
        raw_ts = float(trade["timestamp"])
        # Polymarket timestamps can be in seconds or milliseconds
        if raw_ts > 1e12:
            raw_ts /= 1000
        dt = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
        local_time = dt.astimezone(cet)
        trade["time"] = local_time.strftime("%d %b %H:%M:%S")
        # Time ago
        seconds_ago = int((datetime.now(tz=timezone.utc) - dt).total_seconds())
        if seconds_ago < 60:
            trade["time_ago"] = f"{seconds_ago}s ago"
        elif seconds_ago < 3600:
            trade["time_ago"] = f"{seconds_ago // 60}m ago"
        elif seconds_ago < 86400:
            trade["time_ago"] = f"{seconds_ago // 3600}h {(seconds_ago % 3600) // 60}m ago"
        else:
            trade["time_ago"] = f"{seconds_ago // 86400}d ago"
    except Exception as e:
        print(f"Timestamp error: {e}")
        trade["time"] = "Unknown"
        trade["time_ago"] = ""

    # Normalize price/size to 2 decimal places safely
    try:
        trade["price"] = round(float(trade.get("price", 0)), 4)
    except (ValueError, TypeError):
        trade["price"] = trade.get("price", "?")

    try:
        trade["shares"] = round(float(trade.get("size", 0)), 2)
        trade["size"] = round(float(trade.get("usdcSize", trade.get("size", 0))), 2)
    except (ValueError, TypeError):
        trade["shares"] = trade.get("size", "?")
        trade["size"] = trade.get("usdcSize", trade.get("size", "?"))

    trade.setdefault("spread", None)
    trade.setdefault("mid", None)
    return trade


@app.route("/test")
def test():
    send_telegram("🚀 Manual test message")
    return "Test sent!"


@app.route("/")
def home():
    global seen_trades

    error = None
    # /activity returns the same data Polymarket UI uses — more real-time than /trades
    url_wallet = f"https://data-api.polymarket.com/activity?user={wallet}&limit=50"

    try:
        res = requests.get(url_wallet, timeout=5)
        res.raise_for_status()
        raw = res.json()
        # /activity returns a list directly or wrapped — handle both
        wallet_trades = raw if isinstance(raw, list) else raw.get("data", raw.get("activities", []))
        if not isinstance(wallet_trades, list):
            raise ValueError(f"Unexpected response format: {type(wallet_trades)}")
        # Filter out non-trade entries like liquidity rewards
        wallet_trades = [t for t in wallet_trades if t.get("type", "").upper() in ("BUY", "SELL", "TRADE") or t.get("side") in ("BUY", "SELL")]
        print(f"Fetched {len(wallet_trades)} trades from /activity")
    except Exception as e:
        print(f"/activity failed ({e}), falling back to /trades")
        error = None
        try:
            res = requests.get(f"https://data-api.polymarket.com/trades?user={wallet}&limit=50", timeout=5)
            res.raise_for_status()
            wallet_trades = res.json()
            if not isinstance(wallet_trades, list):
                raise ValueError(f"Unexpected format: {type(wallet_trades)}")
            print(f"Fallback: fetched {len(wallet_trades)} trades from /trades")
        except Exception as e2:
            print(f"Fetch error: {e2}")
            wallet_trades = []
            error = f"Could not fetch trades: {e2}"

    # ✅ Sort by timestamp descending — cast to float to avoid string sort bugs
    wallet_trades.sort(key=safe_timestamp, reverse=True)

    # Initialize seen_trades on first load (no alerts for existing trades)
    if not seen_trades:
        for t in wallet_trades:
            seen_trades.add(t.get("transactionHash", ""))

    # Process all trades: format + check for new ones
    for trade in wallet_trades:
        format_trade(trade)
        trade_id = trade.get("transactionHash", "")

        if trade_id and trade_id not in seen_trades:
            seen_trades.add(trade_id)

            size = trade.get("size", 0)
            try:
                size = float(size)
            except (ValueError, TypeError):
                size = 0

            if size > 0:
                message = (
                    f"🚨 NEW TRADE\n\n"
                    f"{trade.get('side', '?')} {trade.get('outcome', '?')}\n"
                    f"{trade.get('title', 'Unknown market')}\n\n"
                    f"💰 Price: {trade['price']}\n"
                    f"📊 Shares: {trade['shares']} (${trade['size']})\n"
                    f"🕒 {trade['time']}"
                )
                print("Sending alert...")
                send_telegram(message)

    # ✅ Grab the 3 most recent trades AFTER sorting
    top3 = wallet_trades[:3]

    # Enrich with CLOB spread/mid data (optional — comment out if too slow)
    for trade in top3:
        token_id = trade.get("asset_id") or trade.get("tokenId") or trade.get("token_id")
        spread, mid = get_clob_info(token_id)
        if spread is not None:
            trade["spread"] = spread
            trade["mid"] = mid

    return render_template_string(HTML, trades=top3, error=error,
                                   now=datetime.now(tz=cet).strftime("%d %b %H:%M:%S"))


print("TOKEN:", os.getenv("TELEGRAM_TOKEN"))

# Start Telegram polling in background thread
t = threading.Thread(target=poll_telegram, daemon=True)
t.start()

app.run(debug=True, use_reloader=False)  # use_reloader=False prevents double thread on reload