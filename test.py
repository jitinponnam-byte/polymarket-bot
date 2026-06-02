from polymarket_us import PolymarketUS
import json
import time
import csv
import os
import random
from datetime import datetime

client = PolymarketUS()

SEARCH_WORDS = [
    "nba", "nhl",
    "tennis", "atp", "wta",
    "valorant", "vct",
    "counter-strike", "cs2", "csgo",
    "league of legends", "lol",
    "dota", "dota 2",
    "call of duty", "cod",
    "overwatch",
    "rocket league",
    "fifa", "world cup", "soccer"
]

BLOCK_WORDS = [
    "mvp",
    "champion",
    "championship",
    "winner",
    "rookie of the year",
    "hart",
    "stanley cup",
    "finals mvp",
    "season",
    "trophy",
    "award",
    "league winner",
    "conference winner",
    "division winner"
]

ALLOW_GAME_WORDS = [
    " vs ",
    " against ",
    "match",
    "game",
    "scheduled for"
]

CHECK_SECONDS = 60
PRICE_MOVE_ALERT = 2.0

PAPER_TRADING = True

MAX_OPEN_POSITIONS = 10
MIN_FAKE_TRADE_AMOUNT = 2.00
MAX_FAKE_TRADE_AMOUNT = 3.00

UNDERDOG_MIN_PRICE = 0.25
UNDERDOG_MAX_PRICE = 0.45

PROFIT_TARGET_DOLLARS = 0.25

PRICE_LOG_FILE = "price_log.csv"
TRADE_LOG_FILE = "paper_trades.csv"

last_prices = {}
paper_positions = {}
completed_markets = set()


def setup_csv_files():
    if not os.path.exists(PRICE_LOG_FILE):
        with open(PRICE_LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp", "question", "slug", "market_type",
                "outcome", "price", "probability_percent"
            ])

    if not os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp", "action", "question", "slug", "outcome",
                "buy_price", "current_price", "shares", "amount",
                "paper_profit_loss"
            ])


def log_price(timestamp, question, slug, market_type, outcome, price_float, probability):
    with open(PRICE_LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            timestamp, question, slug, market_type,
            outcome, price_float, probability
        ])


def log_trade(timestamp, action, question, slug, outcome, buy_price, current_price, shares, amount, profit_loss):
    with open(TRADE_LOG_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            timestamp, action, question, slug, outcome,
            buy_price, current_price, shares, amount, profit_loss
        ])


def get_underdog(outcomes, prices):
    valid = []

    for outcome, price in zip(outcomes, prices):
        try:
            price_float = float(price)
        except:
            continue

        if price_float > 0:
            valid.append((outcome, price_float))

    if len(valid) != 2:
        return None, None

    return min(valid, key=lambda x: x[1])


def is_fast_game_market(market_text):
    if any(word in market_text for word in BLOCK_WORDS):
        return False

    if not any(word in market_text for word in ALLOW_GAME_WORDS):
        return False

    return True


setup_csv_files()

print("CSV logging enabled.")
print("Watching NBA, NHL, Tennis, Esports, FIFA, and soccer.")
print("Paper trading only.")
print("Rules: max 10 positions, $2-$3 each, underdog only, cash out in profit, no re-entry.")
print("Updated: filters out futures/long-term markets and focuses on same-day style games/matches.")

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

        total_markets_seen = len(markets)
        keyword_matches = 0
        blocked_long_term = 0
        game_style_matches = 0
        two_outcome_matches = 0
        found = 0

        for market in markets:
            question = market.get("question", "")
            slug = market.get("slug", "")
            market_type = market.get("marketType", "unknown")
            market_text = f"{question} {slug} {market_type}".lower()

            if not any(word.lower() in market_text for word in SEARCH_WORDS):
                continue

            keyword_matches += 1

            if any(word in market_text for word in BLOCK_WORDS):
                blocked_long_term += 1
                print("SKIP: long-term futures market.")
                print("Question:", question)
                continue

            if not any(word in market_text for word in ALLOW_GAME_WORDS):
                print("SKIP: not a single-game/match market.")
                print("Question:", question)
                continue

            game_style_matches += 1

            outcomes_raw = market.get("outcomes")
            prices_raw = market.get("outcomePrices")

            try:
                outcomes = json.loads(outcomes_raw)
                prices = json.loads(prices_raw)
            except:
                continue

            if len(outcomes) != 2 or len(prices) != 2:
                print("SKIP: not a 2-outcome market.")
                print("Question:", question)
                print("Market Type:", market_type)
                continue

            two_outcome_matches += 1
            found += 1

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
                    continue

                key = f"{slug}:{outcome}"
                old_probability = last_prices.get(key)

                print(f"{outcome}: {probability:.1f}%")

                log_price(
                    timestamp,
                    question,
                    slug,
                    market_type,
                    outcome,
                    price_float,
                    probability
                )

                if old_probability is not None:
                    change = probability - old_probability

                    if abs(change) >= PRICE_MOVE_ALERT:
                        direction = "UP" if change > 0 else "DOWN"
                        print(f"ALERT: {outcome} moved {direction} by {change:.1f}%")

                last_prices[key] = probability

                if key in paper_positions:
                    position = paper_positions[key]
                    buy_price = position["buy_price"]
                    shares = position["shares"]
                    amount = position["amount"]

                    current_value = shares * price_float
                    profit_loss = current_value - amount

                    print("PAPER POSITION:")
                    print(f"  Side: {outcome}")
                    print(f"  Amount in: ${amount:.2f}")
                    print(f"  Bought at: {buy_price * 100:.1f}%")
                    print(f"  Current: {probability:.1f}%")
                    print(f"  Current value: ${current_value:.2f}")
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

                    if profit_loss >= PROFIT_TARGET_DOLLARS:
                        print("PAPER CASH OUT:")
                        print(f"  Sold fake position on {outcome}")
                        print(f"  Fake profit: ${profit_loss:.2f}")
                        print("  This market will not be entered again.")

                        log_trade(
                            timestamp,
                            "PAPER_CASH_OUT",
                            question,
                            slug,
                            outcome,
                            buy_price,
                            price_float,
                            shares,
                            amount,
                            profit_loss
                        )

                        del paper_positions[key]
                        completed_markets.add(slug)

            if PAPER_TRADING:
                if slug in completed_markets:
                    print("SKIP: already completed this market before.")
                    continue

                if len(paper_positions) >= MAX_OPEN_POSITIONS:
                    print("SKIP: max open paper positions reached.")
                    continue

                already_in_market = any(pos["slug"] == slug for pos in paper_positions.values())
                if already_in_market:
                    print("SKIP: already holding a position in this market.")
                    continue

                underdog_outcome, underdog_price = get_underdog(outcomes, prices)

                if underdog_outcome is None:
                    continue

                if not (UNDERDOG_MIN_PRICE <= underdog_price <= UNDERDOG_MAX_PRICE):
                    print("SKIP: underdog price outside target range.")
                    continue

                stake = round(random.uniform(MIN_FAKE_TRADE_AMOUNT, MAX_FAKE_TRADE_AMOUNT), 2)
                shares = stake / underdog_price
                key = f"{slug}:{underdog_outcome}"

                paper_positions[key] = {
                    "question": question,
                    "slug": slug,
                    "outcome": underdog_outcome,
                    "buy_price": underdog_price,
                    "shares": shares,
                    "amount": stake
                }

                print("PAPER BUY:")
                print(f"  Bought fake ${stake:.2f} of {underdog_outcome}")
                print(f"  Entry price: {underdog_price * 100:.1f}%")
                print(f"  Fake shares: {shares:.2f}")

                log_trade(
                    timestamp,
                    "PAPER_BUY",
                    question,
                    slug,
                    underdog_outcome,
                    underdog_price,
                    underdog_price,
                    shares,
                    stake,
                    0.00
                )

        print("----------------------")
        print("Total active markets seen:", total_markets_seen)
        print("Keyword matches:", keyword_matches)
        print("Blocked long-term/futures markets:", blocked_long_term)
        print("Game/match style matches:", game_style_matches)
        print("Two-outcome matches:", two_outcome_matches)
        print("Tradable markets found:", found)
        print("Open paper positions:", len(paper_positions))
        print("Completed / blocked markets:", len(completed_markets))

        if found == 0:
            print("No fast NBA/NHL/Tennis/Esports/FIFA 2-outcome markets found right now.")

        print(f"Waiting {CHECK_SECONDS} seconds...")
        time.sleep(CHECK_SECONDS)

except KeyboardInterrupt:
    print("\nBot stopped safely.")
