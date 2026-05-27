from polymarket_us import PolymarketUS
import json
import time
import csv
import os
from datetime import datetime

client = PolymarketUS()

# Markets to watch
SEARCH_WORDS = [
    "nba",
    "nhl",
    "san antonio",
    "oklahoma city",
    "colorado avalanche",
    "vegas golden knights",
    "carolina hurricanes",
    "montreal canadiens"
]

CHECK_SECONDS = 60
PRICE_MOVE_ALERT = 2.0

# Paper trading only — this does NOT use real money
PAPER_TRADING = True
FAKE_BUY_PRICE_LIMIT = 0.50
FAKE_TRADE_AMOUNT = 10.00

PRICE_LOG_FILE = "price_log.csv"
TRADE_LOG_FILE = "paper_trades.csv"

last_prices = {}
paper_positions = {}


def setup_csv_files():
    if not os.path.exists(PRICE_LOG_FILE):
        with open(PRICE_LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp",
                "question",
                "slug",
                "market_type",
                "outcome",
                "price",
                "probability_percent"
            ])

    if not os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp",
                "action",
                "question",
                "slug",
                "outcome",
                "buy_price",
                "current_price",
                "shares",
                "amount",
                "paper_profit_loss"
            ])


def log_price(timestamp, question, slug, market_type, outcome, price_float, probability):
    with open(PRICE_LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            timestamp,
            question,
            slug,
            market_type,
            outcome,
            price_float,
            probability
        ])


def log_trade(timestamp, action, question, slug, outcome, buy_price, current_price, shares, amount, profit_loss):
    with open(TRADE_LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            timestamp,
            action,
            question,
            slug,
            outcome,
            buy_price,
            current_price,
            shares,
            amount,
            profit_loss
        ])


setup_csv_files()
print("CSV logging enabled: price_log.csv and paper_trades.csv")

try:
    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print("\n==============================")
        print("Checking markets at:", timestamp)
        print("==============================")

        markets_data = client.markets.list({
            "limit": 500,
            "active": True,
            "closed": False
        })

        markets = markets_data.get("markets", [])
        found = 0

        for market in markets:
            question = market.get("question", "")
            slug = market.get("slug", "")
            market_type = market.get("marketType", "")
            market_text = f"{question} {slug}".lower()

            # Only check markets matching our search words
            if not any(word.lower() in market_text for word in SEARCH_WORDS):
                continue

            # Only focus on game winner markets
            # This skips long-term futures like "NBA Champion"
            if market_type != "moneyline":
                continue

            outcomes_raw = market.get("outcomes")
            prices_raw = market.get("outcomePrices")

            try:
                outcomes = json.loads(outcomes_raw)
                prices = json.loads(prices_raw)
            except:
                continue

            print("----------------------")
            print("Question:", question)
            print("Slug:", slug)
            print("Market Type:", market_type)

            for outcome, price in zip(outcomes, prices):
                try:
                    price_float = float(price)
                    probability = price_float * 100
                except:
                    continue

                if price_float <= 0:
                    print(f"{outcome}: {probability:.1f}% -- skipped, price too low/invalid")
                    continue

                key = f"{slug}:{outcome}"
                old_probability = last_prices.get(key)

                print(f"{outcome}: {probability:.1f}%")

                # Save every price check to CSV
                log_price(
                    timestamp,
                    question,
                    slug,
                    market_type,
                    outcome,
                    price_float,
                    probability
                )

                # Alert if price moved enough
                if old_probability is not None:
                    change = probability - old_probability

                    if abs(change) >= PRICE_MOVE_ALERT:
                        direction = "UP" if change > 0 else "DOWN"
                        print(f"ALERT: {outcome} moved {direction} by {change:.1f}%")

                last_prices[key] = probability

                # PAPER TRADE RULE:
                # Fake buy any outcome when price is below 35%
                # This does NOT place a real order.
                if PAPER_TRADING and price_float <= FAKE_BUY_PRICE_LIMIT:
                    if key not in paper_positions:
                        shares = FAKE_TRADE_AMOUNT / price_float

                        paper_positions[key] = {
                            "question": question,
                            "slug": slug,
                            "outcome": outcome,
                            "buy_price": price_float,
                            "shares": shares,
                            "amount": FAKE_TRADE_AMOUNT
                        }

                        print("PAPER BUY:")
                        print(f"  Bought fake ${FAKE_TRADE_AMOUNT:.2f} of {outcome} at {probability:.1f}%")
                        print(f"  Fake shares: {shares:.2f}")

                        log_trade(
                            timestamp,
                            "PAPER_BUY",
                            question,
                            slug,
                            outcome,
                            price_float,
                            price_float,
                            shares,
                            FAKE_TRADE_AMOUNT,
                            0.00
                        )

                # Show fake profit/loss if we have a paper position
                if key in paper_positions:
                    position = paper_positions[key]
                    buy_price = position["buy_price"]
                    shares = position["shares"]
                    amount = position["amount"]

                    current_value = shares * price_float
                    profit_loss = current_value - amount

                    print("PAPER POSITION:")
                    print(f"  Bought at: {buy_price * 100:.1f}%")
                    print(f"  Current: {probability:.1f}%")
                    print(f"  Fake P/L: ${profit_loss:.2f}")

                    log_trade(
                        timestamp,
                        "PAPER_UPDATE",
                        question,
                        slug,
                        outcome,
                        buy_price,
                        price_float,
                        shares,
                        amount,
                        profit_loss
                    )

            found += 1

        print("----------------------")
        print("Markets found:", found)
        print("Paper positions:", len(paper_positions))

        if found == 0:
            print("No matching NBA/NHL moneyline markets found right now.")

        print(f"Waiting {CHECK_SECONDS} seconds...")

        time.sleep(CHECK_SECONDS)

except KeyboardInterrupt:
    print("\nBot stopped safely.")
