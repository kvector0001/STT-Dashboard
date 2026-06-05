import json
import pandas as pd

print("Checking prices.json...")
with open('prices.json') as f:
    prices = json.load(f)

print(f"✓ NH in prices.json: {'NH' in prices}")
print(f"✓ Total stocks in prices.json: {len(prices)}")

print("\nChecking Google Sheet portfolio...")
df = pd.read_excel('GoogleSheet_Check.xlsx')
portfolio_symbols = set(df['Symbol'].str.strip())
print(f"✓ Total stocks in portfolio: {len(portfolio_symbols)}")
print(f"✓ NH in portfolio: {'NH' in portfolio_symbols}")

print("\nStocks in prices.json but NOT in portfolio:")
extra_stocks = set(prices.keys()) - portfolio_symbols
if extra_stocks:
    for stock in sorted(extra_stocks):
        print(f"  - {stock}")
else:
    print("  None - all prices match portfolio ✓")
