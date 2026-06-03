from polymarket_us import PolymarketUS
import json
import time
import csv
import os
import random
import re
from datetime import datetime, timedelta

client = PolymarketUS()

# ==============================
# SEARCH SETTINGS
# ==============================

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
    "fifa", "soccer", "mls"
]

# Blocks long-term markets / futures / awards / season markets
BLOCK_WORDS = [
    "mvp",
    "champion",
    "championship",
    "winner",
    "golden boot",
    "rookie of the year",
    "hart",
    "stanley cup",
    "finals mvp",
    "season",
    "trophy",
    "award",
    "league winner",
    "conference winner",
    "division winner",
    "group winner",
    "group a winner",
    "group b winner",
    "group c winner",
    "group d winner",
    "group e winner",
    "group f winner",
    "group g winner",
    "group h winner",
    "group i winner",
    "group j winner",
    "group k winner",
    "group l winner",
    "major league soccer champion",
    "mls champion",
    "world cup winner",
    "fifa world cup winner",
    "fifa world cup golden boot",
    "fifa world cup group"
]

# Only allow markets that look like one game or one match
ALLOW_GAME_WORDS = [
    " vs ",
    " against ",
    "match",
    "game",
    "scheduled for"
]

# ==============================
# SAME-DAY RULE
# ==============================

# Same-day only.
# If the market has a date like "scheduled for Jun 17, 2026",
# the bot only allows it if that date is today.
SAME_DAY_ONLY = True

# ==============================
# BOT SETTINGS
# ==============================

CHECK_SECONDS = 60
PRICE_MOVE_ALERT = 2.0

PAPER_TRADING = True

MAX_OPEN_POSITIONS = 10
MIN_FAKE_TRADE_AMOUNT = 2.00
MAX_FAKE_TRADE_AMOUNT = 3.00

UNDERDOG_MIN_PRICE = 0.25
UNDERDOG_MAX_PRICE = 0.45

# ==============================
# TRAILING SELL SETTINGS
# ==============================

# Must be up at least this much before trailing sell is allowed
MIN_PEAK_PROFIT_TO_TRAIL = 0.10

# Sell if price drops this much from the highest price after buy
# 0.02 = 2 cents / 2 percentage points
TRAILING_DROP_FROM_HIGH = 0.02

# Emergency stop loss
HARD_STOP_LOSS_DOLLARS = 0.75

# ==============================
# FILES
# ==============================

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


def has_blocked_words(market_text):
    return any(word in market_text for word in BLOCK_WORDS)


def looks_like_game_market(market_text):
    return any(word in market_text for word in ALLOW_GAME_WORDS)


def parse_scheduled_date(market_text):
    """
    Looks for dates like:
    scheduled for Jun 17, 2026
    scheduled for June 17, 2026
    """

    pattern = r"scheduled for ([a-zA-Z]+)\s+(\d{1,2}),\s*(\d{4})"
    match = re.search(pattern, market_text)

    if not match:
        return None

    month_name = match.group(1)
    day = match.group(2)
    year = match.group(3)

    date_string = f"{month_name} {day}, {year}"

    for fmt in ["%b %d, %Y", "%B %d, %Y"]:
        try:
            return datetime.strptime(date_string, fmt)
        except:
            pass

    return None


def is_same_day_market(market_text):
    """
    Same-day only filter:
    - If the market has a scheduled date, only allow it if it is today.
    - If there is no scheduled date, allow it only if it still looks like a game/match.
    """

    scheduled_date = parse_scheduled_date(market_text)

    if scheduled_date is None:
        return True

    today = datetime.now().date()

    if scheduled_date.date() != today:
        return False

    return True


def is_allowed_small_term_market(question, slug, market_type):
    market_text = f"{question} {slug} {market_type}".lower()

    if has_blocked_words(market_text):
        return False, "long-term futures / award / winner market"

    if not looks_like_game_market(market_text):
        return False, "not a single-game or match market"

    if SAME_DAY_ONLY and not is_same_day_market(market_text):
        return False, "not a same-day market"

    return True, "allowed"


setup_csv_files()

print("CSV logging enabled.")
print("Watching same-day NBA, NHL, Tennis, Esports, FIFA, soccer, and MLS markets.")
print("Paper trading only.")
print("Rules: SAME-DAY game/match markets only, no champion/winner/futures markets.")
print("Rules: max 10 positions, $2-$3 each, underdog only, trailing cash out, no re-entry.")
print("Short-term filter: same-day markets only when a scheduled date is found.")

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
        blocked_not_game = 0
        blocked_not_same_day = 0
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

            allowed, reason = is_allowed_small_term_market(question, slug, market_type)

            if not allowed:
                if "long-term" in reason:
                    blocked_long_term += 1
                    print("SKIP: long-term futures/award/winner market.")
                elif "not a single-game" in reason:
                    blocked_not_game += 1
                    print("SKIP: not a single-game/match market.")
                elif "same-day" in reason:
                    blocked_not_same_day += 1
                    print("SKIP: not a same-day market.")
                else:
                    print("SKIP:", reason)

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

                    highest_price = position.get("highest_price", buy_price)

                    if price_float > highest_price:
                        highest_price = price_float
                        position["highest_price"] = highest_price
                        position["highest_value"] = shares * highest_price
                        position["peak_profit_loss"] = position["highest_value"] - amount

                    highest_value = position.get("highest_value", shares * highest_price)
                    peak_profit_loss = position.get("peak_profit_loss", highest_value - amount)
                    drop_from_high = highest_price - price_float

                    print("PAPER POSITION:")
                    print(f"  Side: {outcome}")
                    print(f"  Amount in: ${amount:.2f}")
                    print(f"  Bought at: {buy_price * 100:.1f}%")
                    print(f"  Current: {probability:.1f}%")
                    print(f"  Current value: ${current_value:.2f}")
                    print(f"  Fake P/L: ${profit_loss:.2f}")
                    print(f"  High since buy: {highest_price * 100:.1f}%")
                    print(f"  Drop from high: {drop_from_high * 100:.1f} percentage points")
                    print(f"  Peak fake P/L: ${peak_profit_loss:.2f}")

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

                    trailing_sell_ready = peak_profit_loss >= MIN_PEAK_PROFIT_TO_TRAIL
                    price_fell_from_peak = drop_from_high >= TRAILING_DROP_FROM_HIGH

                    hard_stop_hit = (
                        HARD_STOP_LOSS_DOLLARS is not None
                        and profit_loss <= -HARD_STOP_LOSS_DOLLARS
                    )

                    if trailing_sell_ready and price_fell_from_peak:
                        print("PAPER TRAILING CASH OUT:")
                        print(f"  Sold fake position on {outcome}")
                        print(f"  Peak fake profit was: ${peak_profit_loss:.2f}")
                        print(f"  Final fake P/L: ${profit_loss:.2f}")
                        print("  Reason: price started going down after reaching a high.")
                        print("  This market will not be entered again.")

                        log_trade(
                            timestamp,
                            "PAPER_TRAILING_CASH_OUT",
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

                    elif hard_stop_hit:
                        print("PAPER STOP LOSS:")
                        print(f"  Sold fake position on {outcome}")
                        print(f"  Final fake P/L: ${profit_loss:.2f}")
                        print("  Reason: hard stop loss hit.")
                        print("  This market will not be entered again.")

                        log_trade(
                            timestamp,
                            "PAPER_STOP_LOSS",
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
                    "amount": stake,
                    "highest_price": underdog_price,
                    "highest_value": stake,
                    "peak_profit_loss": 0.00
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
        print("Blocked non-game markets:", blocked_not_game)
        print("Blocked not-same-day markets:", blocked_not_same_day)
        print("Game/match style matches:", game_style_matches)
        print("Two-outcome matches:", two_outcome_matches)
        print("Tradable same-day markets found:", found)
        print("Open paper positions:", len(paper_positions))
        print("Completed / blocked markets:", len(completed_markets))

        if found == 0:
            print("No same-day 2-outcome game/match markets found right now.")

        print(f"Waiting {CHECK_SECONDS} seconds...")
        time.sleep(CHECK_SECONDS)

except KeyboardInterrupt:
    print("\nBot stopped safely.")
