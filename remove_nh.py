import json

print("Loading prices.json...")
with open('prices.json', 'r', encoding='utf-8') as f:
    prices = json.load(f)

print(f"Before: {len(prices)} stocks")
print(f"NH in prices: {'NH' in prices}")

# Remove NH
if 'NH' in prices:
    del prices['NH']
    print("✓ Removed NH")

print(f"After: {len(prices)} stocks")

print("Saving...")
with open('prices.json', 'w', encoding='utf-8') as f:
    json.dump(prices, f, indent=2, ensure_ascii=False)

print("✓ Done!")
