from flask import Flask, render_template_string
import threading
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os
import json

load_dotenv(override=True)

# ── Wallets ──────────────────────────────────────────────────────────────────
WHALES = {
    "1": {
        "name": "HolyMoses7",
        "address": "0xa4b366ad22fc0d06f1e934ff468e8922431a87b8"
    },
    "2": {
        "name": "ColdMath",
        "address": "0x594edb9112f526fa6a80b8f858a6379c8a2c1c11"
    }
}

# ── Persistence ───────────────────────────────────────────────────────────────
SUBSCRIBERS_FILE = "subscribers.json"

def load_subscribers():
    """Load {chat_id: ['1', '2'] or 'all'} from file."""
    s = {}
    # Always add owner from .env tracking all
    owner = os.getenv("TELEGRAM_CHAT_ID")
    if owner:
        s[int(owner)] = "all"
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r") as f:
                data = json.load(f)
            for k, v in data.items():
                s[int(k)] = v
        except Exception as e:
            print(f"Error loading subscribers: {e}")
    return s

def save_subscribers():
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump({str(k): v for k, v in subscribers.items()}, f)

subscribers = load_subscribers()  # {chat_id (int): "all" | ["1"] | ["1","2"]}
print(f"Loaded {len(subscribers)} subscriber(s)")

seen_trades = {"1": set(), "2": set()}
cet = timezone(timedelta(hours=1))

# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(message, whale_id):
    """Send to all subscribers tracking this whale."""
    token = os.getenv("TELEGRAM_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chat_id, prefs in list(subscribers.items()):
        if prefs == "all" or whale_id in prefs:
            try:
                requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=5)
            except Exception as e:
                print(f"Telegram error for {chat_id}: {e}")


def send_msg(chat_id, text, reply_markup=None):
    token = os.getenv("TELEGRAM_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"send_msg error: {e}")


def poll_telegram():
    token = os.getenv("TELEGRAM_TOKEN")
    url = f"https://api.telegram.org/bot{token}"
    offset = None
    # pending_choice: chat_ids waiting to pick a whale
    pending_choice = set()
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
                text = msg.get("text", "").strip()
                chat_id = msg.get("chat", {}).get("id")
                first_name = msg.get("chat", {}).get("first_name", "there")
                if not chat_id:
                    continue

                if text == "/start":
                    pending_choice.add(chat_id)
                    send_msg(chat_id,
                        f"👋 Hey {first_name}! Which whale do you want to track?",
                        reply_markup={
                            "keyboard": [
                                [{"text": "🐋 HolyMoses7"}, {"text": "🐋 ColdMath"}],
                                [{"text": "🐋 Track All"}]
                            ],
                            "one_time_keyboard": True,
                            "resize_keyboard": True
                        }
                    )

                elif text == "/stop":
                    if chat_id in subscribers:
                        del subscribers[chat_id]
                        save_subscribers()
                    pending_choice.discard(chat_id)
                    send_msg(chat_id, "🔕 Unsubscribed. Send /start to resubscribe.")
                    print(f"Unsubscribed: {chat_id}")

                elif chat_id in pending_choice:
                    if text == "🐋 HolyMoses7":
                        subscribers[chat_id] = ["1"]
                        save_subscribers()
                        pending_choice.discard(chat_id)
                        send_msg(chat_id, "✅ You\'ll receive alerts for HolyMoses7.")
                        print(f"Subscribed {chat_id} to HolyMoses7")
                    elif text == "🐋 ColdMath":
                        subscribers[chat_id] = ["2"]
                        save_subscribers()
                        pending_choice.discard(chat_id)
                        send_msg(chat_id, "✅ You\'ll receive alerts for ColdMath.")
                        print(f"Subscribed {chat_id} to ColdMath")
                    elif text == "🐋 Track All":
                        subscribers[chat_id] = "all"
                        save_subscribers()
                        pending_choice.discard(chat_id)
                        send_msg(chat_id, "✅ You\'ll receive alerts for all whales.")
                        print(f"Subscribed {chat_id} to all whales")
                    else:
                        send_msg(chat_id, "Please use the buttons below 👇", reply_markup={
                            "keyboard": [
                                [{"text": "🐋 HolyMoses7"}, {"text": "🐋 ColdMath"}],
                                [{"text": "🐋 Track All"}]
                            ],
                            "one_time_keyboard": True,
                            "resize_keyboard": True
                        })

        except Exception as e:
            print(f"Polling error: {e}")
            import time; time.sleep(5)


# ── Flask ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Live Trades</title>
    <meta http-equiv="refresh" content="2">
    <style>
        body { font-family: Arial; background: #111; color: white; padding: 20px; }
        .whale-section { margin-bottom: 30px; }
        .whale-title { font-size: 18px; font-weight: bold; color: #f0c040; margin-bottom: 8px; }
        .trade { padding: 12px; margin: 8px 0; border-radius: 8px; }
        .buy { background: #1e7e34; }
        .sell { background: #a71d2a; }
        .time { font-size: 12px; color: #ccc; }
        .error { color: #ff6b6b; padding: 10px; }
    </style>
</head>
<body>
    <h1>📊 Last 3 Trades (CET)</h1>
    <p style="color:#aaa; font-size:13px;">🕒 Page loaded at: {{ now }}</p>

    {% for whale in whales %}
        <div class="whale-section">
            <div class="whale-title">🐋 {{ whale.name }}</div>
            {% if whale.error %}
                <div class="error">⚠️ {{ whale.error }}</div>
            {% endif %}
            {% if not whale.trades %}
                <p style="color:#aaa">No trades found.</p>
            {% endif %}
            {% for trade in whale.trades %}
                <div class="trade {{ 'buy' if trade.side == 'BUY' else 'sell' }}">
                    <b>{{ trade.side }} — {{ trade.outcome }}</b><br>
                    {{ trade.title }}<br>
                    Price: <b>{{ trade.price }}</b> | Shares: <b>{{ trade.shares }}</b> | Value: <b>${{ trade.size }}</b><br>
                    <span class="time">🕒 {{ trade.time }} &nbsp;·&nbsp; <b>{{ trade.time_ago }}</b></span>
                </div>
            {% endfor %}
        </div>
    {% endfor %}
</body>
</html>
"""


def safe_timestamp(trade):
    try:
        return float(trade.get("timestamp", 0))
    except (ValueError, TypeError):
        return 0


def format_trade(trade):
    try:
        raw_ts = float(trade["timestamp"])
        if raw_ts > 1e12:
            raw_ts /= 1000
        dt = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
        local_time = dt.astimezone(cet)
        trade["time"] = local_time.strftime("%d %b %H:%M:%S")
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
        trade["time"] = "Unknown"
        trade["time_ago"] = ""
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
    return trade


def fetch_trades_for_whale(whale_id):
    whale = WHALES[whale_id]
    address = whale["address"]
    error = None
    try:
        res = requests.get(
            f"https://data-api.polymarket.com/activity?user={address}&limit=50",
            timeout=5
        )
        res.raise_for_status()
        raw = res.json()
        trades = raw if isinstance(raw, list) else raw.get("data", raw.get("activities", []))
        trades = [t for t in trades if t.get("type", "").upper() in ("BUY", "SELL", "TRADE") or t.get("side") in ("BUY", "SELL")]
    except Exception as e:
        print(f"Fetch error for {whale['name']}: {e}")
        trades = []
        error = str(e)
    trades.sort(key=safe_timestamp, reverse=True)
    return trades, error


@app.route("/test")
def test():
    for whale_id in WHALES:
        send_telegram(f"🚀 Test alert from {WHALES[whale_id]['name']}", whale_id)
    return "Test sent to all whales!"


@app.route("/")
def home():
    whale_sections = []

    for whale_id, whale in WHALES.items():
        trades, error = fetch_trades_for_whale(whale_id)

        # Init seen_trades on first load
        if not seen_trades[whale_id]:
            for t in trades:
                seen_trades[whale_id].add(t.get("transactionHash", ""))

        # Check for new trades and alert
        for trade in trades:
            format_trade(trade)
            trade_id = trade.get("transactionHash", "")
            if trade_id and trade_id not in seen_trades[whale_id]:
                seen_trades[whale_id].add(trade_id)
                size = 0
                try:
                    size = float(trade.get("size", 0))
                except (ValueError, TypeError):
                    pass
                if size > 0:
                    wname = whale['name']
                    side = trade.get('side', '?')
                    outcome = trade.get('outcome', '?')
                    title = trade.get('title', 'Unknown market')
                    message = (
                        f"🚨 NEW TRADE — {wname}\n\n"
                        f"{side} {outcome}\n"
                        f"{title}\n\n"
                        f"💰 Price: {trade['price']}\n"
                        f"📊 Shares: {trade['shares']} (${trade['size']})\n"
                        f"🕒 {trade['time']}"
                    )
                    print(f"Sending alert for {whale['name']}...")
                    send_telegram(message, whale_id)

        whale_sections.append({
            "name": whale["name"],
            "trades": trades[:3],
            "error": error
        })

    return render_template_string(HTML, whales=whale_sections,
                                  now=datetime.now(tz=cet).strftime("%d %b %H:%M:%S"))


print("TOKEN:", os.getenv("TELEGRAM_TOKEN"))

t = threading.Thread(target=poll_telegram, daemon=True)
t.start()

app.run(debug=True, use_reloader=False)