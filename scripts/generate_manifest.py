import os
import json

def generate_file_list():
    files = [f for f in os.listdir('.') if f.startswith('stocks') and f.endswith('.json')]
    # also check for Stocks_Fundamentals*.json as requested
    files += [f for f in os.listdir('.') if f.startswith('Stocks_Fundamentals') and f.endswith('.json')]
    
    # Remove duplicates and sort
    files = sorted(list(set(files)))
    
    with open('manifest.json', 'w', encoding='utf-8') as f:
        json.dump({"stock_files": files}, f, indent=2)
    print(f"Generated manifest.json with {len(files)} files.")

if __name__ == "__main__":
    generate_file_list()
