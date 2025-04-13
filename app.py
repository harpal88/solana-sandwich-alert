import datetime
import os
import json
from pathlib import Path
import time
import argparse

import requests
from dotenv import dotenv_values
from flask import Flask, render_template, request, jsonify

# Constants
API_CALL_DELAY = 0.1  # seconds between API calls
CONFIG_PATH = Path('config.json')
ENV_PATH = Path('.env')

def load_env_file(env_path):
    """Load environment variables from a .env file with encoding fallback."""
    if not env_path.exists():
        raise FileNotFoundError(f"{env_path} file not found")
    
    try:
        return dotenv_values(dotenv_path=env_path, encoding='utf-8')
    except UnicodeDecodeError:
        return dotenv_values(dotenv_path=env_path, encoding='utf-16')

def load_config_file(config_path):
    """Load configuration from a JSON file with encoding fallback."""
    if not config_path.exists():
        raise FileNotFoundError(f"{config_path} file not found")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        with open(config_path, 'r', encoding='utf-16') as f:
            return json.load(f)

# Load environment variables
try:
    env_vars = load_env_file(ENV_PATH)
    os.environ.update(env_vars)
except Exception as e:
    raise ValueError(f"Failed to load .env file: {str(e)}")

# Load configuration
try:
    CONFIG = load_config_file(CONFIG_PATH)
except Exception as e:
    raise ValueError(f"Failed to load config.json: {str(e)}")

# Validate required environment variables
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY')
if not HELIUS_API_KEY:
    raise ValueError("Missing HELIUS_API_KEY in .env file")

# Validate required configuration keys
required_keys = ['default_lookback_limit', 'max_lookback_limit', 'dex_programs', 'frontend']
for key in required_keys:
    if key not in CONFIG:
        raise ValueError(f"Missing required config key: {key}")

DEFAULT_LOOKBACK_LIMIT = int(CONFIG['default_lookback_limit'])
MAX_LOOKBACK_LIMIT = int(CONFIG['max_lookback_limit'])
DEX_PROGRAM_IDS = CONFIG['dex_programs']

# Validate configuration values
if not isinstance(DEX_PROGRAM_IDS, list) or not all(isinstance(x, str) for x in DEX_PROGRAM_IDS):
    raise ValueError("dex_programs must be a list of strings in config.json")
if DEFAULT_LOOKBACK_LIMIT > MAX_LOOKBACK_LIMIT:
    raise ValueError("default_lookback_limit cannot be greater than max_lookback_limit")

# API URLs
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
PARSE_TRANSACTION_URL = f"https://api.helius.xyz/v0/transactions/?api-key={HELIUS_API_KEY}"
PARSE_ADDRESS_TRANSACTIONS_URL = f"https://api.helius.xyz/v0/addresses/{{address}}/transactions/?api-key={HELIUS_API_KEY}"

def fetch_transaction_details(signature):
    """Fetch detailed transaction data using Helius API"""
    print(f"  Analyzing transaction: {signature[:10]}...{signature[-10:]}")
    params = {
        "transactions": [signature],
        "encoding": "jsonParsed"
    }
    
    try:
        response = requests.post(PARSE_TRANSACTION_URL, json=params)
        response.raise_for_status()
        data = response.json()
        
        # Ensure we got a dictionary response
        if not data or not isinstance(data, list) or len(data) == 0:
            print(f"    No valid transaction data returned for {signature}")
            return None
            
        tx_data = data[0]
        
        # Additional validation
        if not isinstance(tx_data, dict):
            print(f"    Transaction data is not a dictionary for {signature}")
            return None
            
        return tx_data
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching transaction {signature}: {e}")
        return None



def fetch_token_transactions(token_address, limit=100):
    """Fetch recent transactions for a token using Helius API"""
    print(f"\nFetching last {limit} transactions for token: {token_address}")
    time.sleep(API_CALL_DELAY)
    url = PARSE_ADDRESS_TRANSACTIONS_URL.format(address=token_address)
    params = {"limit": limit}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        transactions = response.json()
        if not isinstance(transactions, list):  # Ensure transactions is a list
            print("Unexpected response format for transactions")
            return []
        print(f"Successfully fetched {len(transactions)} transactions")
        return transactions
    except requests.exceptions.RequestException as e:
        print(f"Error fetching transactions: {e}")
        return []

def is_dex_interaction(tx_data):
    """Check if transaction interacts with a known DEX"""
    if not tx_data or not isinstance(tx_data, dict):
        return False
    
    for instruction in tx_data.get("instructions", []):
        program_id = instruction.get("programId")
        if program_id in DEX_PROGRAM_IDS:
            print(f"    Found DEX interaction with program: {program_id}")
            return True
    return False

def analyze_swap_direction(tx_data, token_address):
    """
    Attempt to determine swap direction for the target token.
    Returns "buy", "sell", or None if not a relevant swap.
    """
    # First ensure tx_data is a dictionary
    if not isinstance(tx_data, dict):
        print("    Transaction data is not a dictionary")
        return None
        
    if not tx_data.get("successful", True):
        print("    Transaction failed, skipping")
        return None
        
    # Safely get token transfers with empty list as default
    token_transfers = tx_data.get("tokenTransfers", [])
    if not isinstance(token_transfers, list):
        print("    Token transfers is not a list")
        return None
        
    input_token = None
    output_token = None
    
    print(f"    Analyzing {len(token_transfers)} token transfers...")
    
    for transfer in token_transfers:
        # Ensure each transfer is a dictionary
        if not isinstance(transfer, dict):
            continue
            
        mint = transfer.get("mint")
        token_amount = transfer.get("tokenAmount", {})
        
        # Handle cases where tokenAmount might be a float or other type
        if isinstance(token_amount, dict):
            amount = token_amount.get("amount", "0")
        else:
            amount = "0"
            
        if mint == token_address:
            if amount == "0":
                continue
            if transfer.get("transferType") in ["transfer", "mintTo"]:
                output_token = token_address
            elif transfer.get("transferType") in ["burn"]:
                output_token = token_address
        else:
            input_token = mint
    
    if input_token and output_token == token_address:
        print(f"    Detected BUY order for target token")
        return "buy"
    elif input_token == token_address and output_token and output_token != token_address:
        print(f"    Detected SELL order for target token")
        return "sell"
    
    print("    Not a relevant swap for target token")
    return None

def detect_sandwich_attacks(token_address, lookback_limit=100):
    """Main function to detect sandwich attacks for a given token"""
    print(f"\nAnalyzing recent transactions for token: {token_address}")
    print(f"Using Helius API with lookback limit: {lookback_limit}")
    
    transactions = fetch_token_transactions(token_address, lookback_limit)
    if not transactions:
        print("No transactions found or error fetching data.")
        return
    
    potential_sandwiches = []
    analyzed_signatures = set()
    dex_transactions = []
    
    print("\nProcessing transactions for DEX interactions...")
    for i, tx in enumerate(transactions, 1):
        signature = tx.get("signature")
        if not signature or signature in analyzed_signatures:
            continue
        
        print(f"\n[{i}/{len(transactions)}] Processing transaction {signature[:10]}...")
        analyzed_signatures.add(signature)
        
        tx_details = fetch_transaction_details(signature)
        if not tx_details:
            continue
           # Ensure timestamp is properly handled
        timestamp = tx.get("timestamp")
        if not isinstance(timestamp, (int, float)):
            print(f"  Invalid timestamp for {signature}, skipping")
            continue
        if is_dex_interaction(tx_details):
            swap_dir = analyze_swap_direction(tx_details, token_address)
            if swap_dir:
                dex_transactions.append({
                    "signature": signature,
                    "direction": swap_dir,
                    "timestamp": tx.get("timestamp"),
                    "details": tx_details
                })
                print(f"  Added to DEX transactions list (direction: {swap_dir})")
            else:
                print("  DEX interaction but not a relevant swap")
        else:
            print("  Not a DEX interaction")
    
    print(f"\nFound {len(dex_transactions)} relevant DEX transactions to analyze")
    
    # Look for sandwich patterns
    print("\nScanning for sandwich patterns...")
    for i in range(1, len(dex_transactions) - 1):
        prev_tx = dex_transactions[i-1]
        curr_tx = dex_transactions[i]
        next_tx = dex_transactions[i+1]
        
        time_diff_prev = abs(curr_tx["timestamp"] - prev_tx["timestamp"])
        time_diff_next = abs(next_tx["timestamp"] - curr_tx["timestamp"])
        
        # Only consider transactions within 30 seconds of each other
        if time_diff_prev > 30 or time_diff_next > 30:
            continue
        
        # Check for buy-victim-sell pattern
        if (prev_tx["direction"] == "buy" and 
            curr_tx["direction"] == "buy" and 
            next_tx["direction"] == "sell"):
            
            print(f"\nPotential sandwich attack detected (buy-victim-sell):")
            print(f"  Buy TX:  {prev_tx['signature']}")
            print(f"  Victim:  {curr_tx['signature']}")
            print(f"  Sell TX: {next_tx['signature']}")
            print(f"  Time between: {time_diff_prev}s and {time_diff_next}s")
            
            potential_sandwiches.append({
                "type": "buy-victim-sell",
                "sandwich_buy": prev_tx["signature"],
                "victim_tx": curr_tx["signature"],
                "sandwich_sell": next_tx["signature"],
                "timestamp": curr_tx["timestamp"],
                "time_diff_prev": time_diff_prev,
                "time_diff_next": time_diff_next
            })
        
        # Check for sell-victim-buy pattern
        elif (prev_tx["direction"] == "sell" and 
              curr_tx["direction"] == "sell" and 
              next_tx["direction"] == "buy"):
            
            print(f"\nPotential sandwich attack detected (sell-victim-buy):")
            print(f"  Sell TX: {prev_tx['signature']}")
            print(f"  Victim:  {curr_tx['signature']}")
            print(f"  Buy TX:  {next_tx['signature']}")
            print(f"  Time between: {time_diff_prev}s and {time_diff_next}s")
            
            potential_sandwiches.append({
                "type": "sell-victim-buy",
                "sandwich_sell": prev_tx["signature"],
                "victim_tx": curr_tx["signature"],
                "sandwich_buy": next_tx["signature"],
                "timestamp": curr_tx["timestamp"],
                "time_diff_prev": time_diff_prev,
                "time_diff_next": time_diff_next
            })
    
    # Final results
    if potential_sandwiches:
        print(f"\nFound {len(potential_sandwiches)} potential sandwich attacks:")
        for attack in potential_sandwiches:
            print(f"\nAttack type: {attack['type']}")
            print(f"Timestamp: {datetime.fromtimestamp(attack['timestamp'])}")
            print(f"Time between transactions: {attack['time_diff_prev']}s and {attack['time_diff_next']}s")
            print(f"Sandwich first TX: {attack.get('sandwich_buy', attack.get('sandwich_sell'))}")
            print(f"Victim TX: {attack['victim_tx']}")
            print(f"Sandwich second TX: {attack.get('sandwich_sell', attack.get('sandwich_buy'))}")
            print(f"Explorer links:")
            print(f" First: https://solscan.io/tx/{attack.get('sandwich_buy', attack.get('sandwich_sell'))}")
            print(f" Victim: https://solscan.io/tx/{attack['victim_tx']}")
            print(f" Second: https://solscan.io/tx/{attack.get('sandwich_sell', attack.get('sandwich_buy'))}")
    else:
        print("\nNo potential sandwich attacks detected in the analyzed transactions.")

# Initialize Flask app
app = Flask(
    __name__,
    static_folder=CONFIG["frontend"]["static_folder"],
    template_folder=CONFIG["frontend"]["template_folder"]
)

@app.route('/')
def index():
    """Serve the index.html template."""
    return render_template('index.html')

# Modify your analyze() route to include actual sandwich detection
@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    token_address = data.get('tokenAddress')
    lookback_limit = data.get('lookbackLimit', DEFAULT_LOOKBACK_LIMIT)

    try:
        lookback_limit = min(int(lookback_limit), MAX_LOOKBACK_LIMIT)
    except ValueError:
        return jsonify({"error": "Invalid lookback limit"}), 400

    if not token_address:
        return jsonify({"error": "Token address is required"}), 400

    try:
        # Get transactions and process them
        transactions = fetch_token_transactions(token_address, lookback_limit) or []
        processed_transactions = []
        potential_sandwiches = []
        
        # Process transactions for DEX interactions
        for tx in transactions:
            signature = tx.get("signature")
            if not signature:
                continue
                
            tx_details = fetch_transaction_details(signature)
            if not tx_details:
                continue
                
            processed_tx = {
                "signature": signature,
                "timestamp": tx.get("timestamp"),
                "details": tx_details,
                "isDex": is_dex_interaction(tx_details),
                "direction": analyze_swap_direction(tx_details, token_address)
            }
            processed_transactions.append(processed_tx)
        
        # Detect sandwich patterns
        potential_sandwiches = detect_sandwich_patterns(processed_transactions)
        
        return jsonify({
            "status": "success",
            "tokenAddress": token_address,
            "transactions": processed_transactions,
            "potentialSandwiches": potential_sandwiches,
            "stats": {
                "totalTransactions": len(transactions),
                "dexTransactions": len([t for t in processed_transactions if t["isDex"]]),
                "potentialAttacks": len(potential_sandwiches)
            }
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def detect_sandwich_patterns(transactions):
    """Detect sandwich attack patterns from processed transactions"""
    potential_sandwiches = []
    dex_transactions = [t for t in transactions if t["isDex"] and t["direction"]]
    
    for i in range(1, len(dex_transactions) - 1):
        prev_tx = dex_transactions[i-1]
        curr_tx = dex_transactions[i]
        next_tx = dex_transactions[i+1]
        
        time_diff_prev = abs(curr_tx["timestamp"] - prev_tx["timestamp"])
        time_diff_next = abs(next_tx["timestamp"] - curr_tx["timestamp"])
        
        if time_diff_prev > 30 or time_diff_next > 30:
            continue
            
        # Check for attack patterns
        if (prev_tx["direction"] == "buy" and 
            curr_tx["direction"] == "buy" and 
            next_tx["direction"] == "sell"):
            
            potential_sandwiches.append({
                "type": "buy-victim-sell",
                "transactions": [prev_tx, curr_tx, next_tx],
                "timeDiffs": [time_diff_prev, time_diff_next]
            })
            
        elif (prev_tx["direction"] == "sell" and 
              curr_tx["direction"] == "sell" and 
              next_tx["direction"] == "buy"):
            
            potential_sandwiches.append({
                "type": "sell-victim-buy",
                "transactions": [prev_tx, curr_tx, next_tx],
                "timeDiffs": [time_diff_prev, time_diff_next]
            })
    
    return potential_sandwiches

if __name__ == "__main__":
    backend_port = int(os.getenv("BACKEND_PORT", 5000))
    print(f"Starting Flask server on port {backend_port}...")
    app.run(host="0.0.0.0", port=backend_port, debug=True, load_dotenv=False)  # Disable Flask's automatic .env loading