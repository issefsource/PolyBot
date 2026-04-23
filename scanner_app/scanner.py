from flask import Flask, Response, render_template
import requests
import time
import json
from datetime import datetime, timezone

app = Flask(__name__)

CATEGORIES = {
    "Politics": ["election", "president", "congress", "senate", "vote", "trump", "biden", "harris",
                 "republican", "democrat", "parliament", "prime minister", "governor", "political"],
    "Crypto":   ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol", "coin", "token",
                 "defi", "nft", "blockchain", "binance", "coinbase", "doge", "xrp"],
    "Macro":    ["gdp", "inflation", "recession", "fed", "ecb", "unemployment", "cpi", "ppi",
                 "interest", "rate cut", "rate hike", "economic", "oil", "gold", "s&p", "nasdaq"],
}

def detect_category(title):
    title_lower = title.lower()
    scores = {cat: 0 for cat in CATEGORIES}
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in title_lower:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Other"


def fetch_open_positions(address):
    """
    Fetch a wallet's current open positions.
    Returns a list of position dicts. We use these to compute unrealised PnL
    so that traders who closed winners but are sitting on open losers get
    accurately penalised in win_pct.
    """
    try:
        r = requests.get(
            "https://data-api.polymarket.com/positions",
            params={"user": address, "sizeThreshold": "0.01"},
            timeout=5
        )
        if r.status_code != 200:
            return []
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("data", [])
    except Exception as e:
        print(f"Open positions fetch error for {address}: {e}")
        return []


def compute_win_pct(pnl, vol, open_positions):
    """
    Compute a realistic win percentage that factors in open (unrealised) positions.

    - Start from the realised PnL.
    - For each open position compute unrealised PnL = currentValue - costBasis.
    - Add unrealised PnL to realised PnL so losers held open drag the metric down.
    - Normalise against total volume traded.
    """
    vol_float = float(vol or 0)
    pnl_float = float(pnl or 0)

    unrealised_pnl = 0.0
    for pos in open_positions:
        try:
            cur_val    = float(pos.get("currentValue") or pos.get("value") or 0)
            avg_price  = float(pos.get("avgPrice") or pos.get("averagePrice") or 0)
            size       = float(pos.get("size") or pos.get("shares") or 0)
            cost_basis = float(pos.get("initialValue") or pos.get("cashInvested") or 0)

            if cost_basis == 0 and avg_price > 0 and size > 0:
                cost_basis = avg_price * size

            if cost_basis > 0:
                unrealised_pnl += cur_val - cost_basis
        except Exception:
            continue

    adjusted_pnl = pnl_float + unrealised_pnl

    if vol_float <= 0:
        return 0.0

    win_pct = min(max((adjusted_pnl / vol_float) * 1000, 0), 100)
    return round(win_pct, 1)


def score_wallet(address, trades, username, pnl, vol, open_positions):
    if not trades:
        return None

    total_usdc = sum(float(t.get("usdcSize", 0)) for t in trades)
    avg_size = total_usdc / len(trades)

    cat_counts = {}
    for t in trades:
        cat = detect_category(t.get("title", ""))
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    dominant_cat = max(cat_counts, key=cat_counts.get)
    dominance_ratio = cat_counts[dominant_cat] / len(trades)

    market_counts = {}
    for t in trades:
        slug = t.get("slug", t.get("title", ""))
        market_counts[slug] = market_counts.get(slug, 0) + 1
    repeat_trades = sum(v - 1 for v in market_counts.values() if v > 1)
    repeat_score = min(repeat_trades / max(len(trades), 1), 1.0)

    prices = [float(t.get("price", 0.5)) for t in trades if t.get("price")]
    avg_price = sum(prices) / len(prices) if prices else 0.5
    early_score = max(0, 1 - avg_price) if avg_price < 0.5 else max(0, avg_price - 0.5)

    size_score = min(avg_size / 5000, 1.0)
    insider_score = round((size_score * 40 + early_score * 30 + repeat_score * 30) * 100, 1)

    win_pct = compute_win_pct(pnl, vol, open_positions)

    # Tally open positions by direction for the UI badge
    open_losing = 0
    open_winning = 0
    for pos in open_positions:
        try:
            cur_val    = float(pos.get("currentValue") or pos.get("value") or 0)
            avg_price2 = float(pos.get("avgPrice") or pos.get("averagePrice") or 0)
            size2      = float(pos.get("size") or pos.get("shares") or 0)
            cost_basis = float(pos.get("initialValue") or pos.get("cashInvested") or 0)
            if cost_basis == 0 and avg_price2 > 0 and size2 > 0:
                cost_basis = avg_price2 * size2
            if cost_basis > 0:
                if cur_val < cost_basis:
                    open_losing += 1
                else:
                    open_winning += 1
        except Exception:
            continue

    signals = []
    if avg_size > 500:
        signals.append("Large positions")
    if early_score > 0.2:
        signals.append("Early entry")
    if repeat_score > 0.2:
        signals.append("Repeated behavior")
    if dominance_ratio > 0.5:
        signals.append(dominant_cat + " specialist")
    if open_losing > 2:
        signals.append(f"{open_losing} losing open pos")

    return {
        "address": address,
        "username": username,
        "pnl": round(float(pnl or 0), 2),
        "vol": round(float(vol or 0), 2),
        "total_usdc": round(total_usdc, 2),
        "avg_size": round(avg_size, 2),
        "trade_count": len(trades),
        "dominant_category": dominant_cat,
        "dominance_ratio": round(dominance_ratio * 100, 1),
        "repeat_score": round(repeat_score * 100, 1),
        "early_score": round(early_score * 100, 1),
        "insider_score": insider_score,
        "win_pct": win_pct,
        "open_losing": open_losing,
        "open_winning": open_winning,
        "signals": signals,
    }

def fetch_leaderboard():
    url = "https://data-api.polymarket.com/v1/leaderboard"
    attempts = [
        {"timePeriod": "ALL", "limit": 50},
        {"timePeriod": "MONTH", "limit": 50},
        {"timePeriod": "WEEK", "limit": 50},
    ]
    for params in attempts:
        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            print(f"Leaderboard attempt error: {e}")
    return []


def fetch_wallets_from_trades():
    print("Falling back to scraping wallets from recent trades...")
    wallets = {}
    try:
        res = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"active": "true", "closed": "false", "limit": 10,
                    "order": "volume24hr", "ascending": "false"},
            timeout=10
        )
        markets = res.json()
        if isinstance(markets, dict):
            markets = markets.get("markets", markets.get("data", []))
        if not isinstance(markets, list):
            markets = []
        print(f"Got {len(markets)} markets")
        for market in markets[:5]:
            condition_id = market.get("conditionId", "")
            if not condition_id:
                continue
            try:
                r = requests.get(
                    "https://data-api.polymarket.com/trades",
                    params={"market": condition_id, "limit": 50},
                    timeout=5
                )
                trades = r.json()
                if not isinstance(trades, list):
                    continue
                for t in trades:
                    wallet = t.get("proxyWallet", "")
                    if wallet:
                        wallets[wallet] = wallets.get(wallet, 0) + float(t.get("usdcSize", 0))
            except Exception as e:
                print(f"Market trades error: {e}")
            time.sleep(0.2)
    except Exception as e:
        print(f"Markets fetch error: {e}")

    sorted_wallets = sorted(wallets.items(), key=lambda x: x[1], reverse=True)
    return [{"proxyWallet": w, "userName": "", "pnl": 0, "vol": v}
            for w, v in sorted_wallets[:40]]


def stream_scan():
    def emit(obj):
        return json.dumps(obj) + "\n"

    yield emit({"type": "progress", "text": "Fetching top traders from leaderboard...", "pct": 5})

    leaders = fetch_leaderboard()
    if not leaders:
        yield emit({"type": "progress", "text": "Leaderboard unavailable, scanning active markets for whales...", "pct": 8})
        leaders = fetch_wallets_from_trades()

    if not leaders:
        yield emit({"type": "progress", "text": "Could not find any traders to analyze.", "pct": 5})
        yield emit({"type": "done", "count": 0})
        return

    leaders = leaders[:40]
    yield emit({"type": "progress", "text": "Found " + str(len(leaders)) + " traders. Analyzing...", "pct": 10})

    now = datetime.now(timezone.utc)
    current_month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    analyzed = 0
    for i, leader in enumerate(leaders):
        address = leader.get("proxyWallet", "")
        username = leader.get("userName") or leader.get("pseudonym") or ""
        pnl = leader.get("pnl", 0)
        vol = leader.get("vol", 0)
        if not address:
            continue

        pct = 10 + int((i / len(leaders)) * 85)
        label = username if username else address[:10] + "..."
        yield emit({"type": "progress", "text": "Analyzing " + label + " (" + str(i+1) + "/" + str(len(leaders)) + ")", "pct": pct})

        try:
            r = requests.get(
                "https://data-api.polymarket.com/activity?user=" + address + "&limit=50",
                timeout=5
            )
            raw = r.json()
            trades = raw if isinstance(raw, list) else raw.get("data", [])
            trades = [t for t in trades if
                      t.get("type", "").upper() in ("BUY", "SELL", "TRADE") or
                      t.get("side") in ("BUY", "SELL")]

            is_active_this_month = False
            for t in trades:
                timestamp = t.get("timestamp")
                if timestamp:
                    try:
                        if isinstance(timestamp, str):
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        else:
                            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                        if dt >= current_month_start:
                            is_active_this_month = True
                            break
                    except Exception:
                        continue

            if not is_active_this_month:
                continue

            # Fetch open positions to compute accurate win %
            open_positions = fetch_open_positions(address)

            if len(trades) >= 3:
                result = score_wallet(address, trades, username, pnl, vol, open_positions)
                if result and result["insider_score"] > 5:
                    yield emit({"type": "result", "data": result})
                    analyzed += 1

        except Exception:
            trades = []

        time.sleep(0.15)

    yield emit({"type": "done", "count": analyzed})

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/scan")
def api_scan():
    return Response(
        stream_scan(),
        mimetype="text/plain",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    )

if __name__ == "__main__":
    print("Insider Scanner running on http://127.0.0.1:5001")
    app.run(debug=True, port=5001, threaded=True)