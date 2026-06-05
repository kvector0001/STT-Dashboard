import json

with open('prices.json') as f:
    prices = json.load(f)

with open('stocks.json') as f:
    stocks = json.load(f)

mafang_in_prices = "MAFANG" in prices
mafang_in_stocks = any(stock["ticker"] == "MAFANG" for stock in stocks)

print(f"✓ MAFANG in prices.json: {mafang_in_prices}")
print(f"✓ MAFANG in stocks.json: {mafang_in_stocks}")

if mafang_in_prices:
    print(f"\nMAFANG price data: {prices['MAFANG']}")
