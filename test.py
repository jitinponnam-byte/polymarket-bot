from polymarket_us import PolymarketUS
import json
import time
from datetime import datetime

client = PolymarketUS()

# Watch only current game-winner markets, not long-term futures
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

PAPER_TRADING = True
FAKE_BUY_PRICE_LIMIT = 0.35   # fake buy YES only if price is under 35%
FAKE_TRADE_AMOUNT = 10.00     # pretend $10 trade

last_prices = {}
paper_positions = {}

try:
    while True:
        print("\n==============================")
        print("Checking markets at:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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

            # Search only the sports/games we care about
            if not any(word.lower() in market_text for word in SEARCH_WORDS):
                continue

            # Only focus on game winner markets
            # This skips futures like "NBA Champion" or "World Series Champion"
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

                # Skip broken/empty prices
                if price_float <= 0:
                    print(f"{outcome}: {probability:.1f}% -- skipped, price too low/invalid")
                    continue

                key = f"{slug}:{outcome}"
                old_probability = last_prices.get(key)

                print(f"{outcome}: {probability:.1f}%")

                # Alert if price moved
                if old_probability is not None:
                    change = probability - old_probability

                    if abs(change) >= PRICE_MOVE_ALERT:
                        direction = "UP" if change > 0 else "DOWN"
                        print(f"ALERT: {outcome} moved {direction} by {change:.1f}%")

                last_prices[key] = probability

                # PAPER TRADE RULE:
                # Fake buy YES when price is below 35%
                # This does NOT use real money.
                if PAPER_TRADING and outcome == "Yes" and price_float <= FAKE_BUY_PRICE_LIMIT:
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
                        print(f"  Bought fake ${FAKE_TRADE_AMOUNT:.2f} of YES at {probability:.1f}%")
                        print(f"  Fake shares: {shares:.2f}")

                # Show fake profit/loss
                if key in paper_positions:
                    position = paper_positions[key]
                    buy_price = position["buy_price"]
                    shares = position["shares"]

                    current_value = shares * price_float
                    profit_loss = current_value - FAKE_TRADE_AMOUNT

                    print("PAPER POSITION:")
                    print(f"  Bought at: {buy_price * 100:.1f}%")
                    print(f"  Current: {probability:.1f}%")
                    print(f"  Fake P/L: ${profit_loss:.2f}")

            found += 1

        print("----------------------")
        print("Markets found:", found)
        print("Paper positions:", len(paper_positions))

        if found == 0:
            print("No matching NBA/NHL moneyline markets found right now.")
            print("Try again later or update SEARCH_WORDS with market names from find_markets.py.")

        print(f"Waiting {CHECK_SECONDS} seconds...")

        time.sleep(CHECK_SECONDS)

except KeyboardInterrupt:
    print("\nBot stopped safely.")