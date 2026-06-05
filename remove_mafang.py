import json

print("Loading stocks.json...")
with open('stocks.json', 'r', encoding='utf-8') as f:
    stocks = json.load(f)

print(f"Total stocks before: {len(stocks)}")

# Remove MAFANG
stocks = [s for s in stocks if s.get('ticker') != 'MAFANG']

print(f"Total stocks after: {len(stocks)}")

print("Saving updated stocks.json...")
with open('stocks.json', 'w', encoding='utf-8') as f:
    json.dump(stocks, f, indent=2, ensure_ascii=False)

print("✓ Done! MAFANG removed from stocks.json")
