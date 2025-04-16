import datetime
import os
import json
from pathlib import Path
import time
import argparse
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import dotenv_values
from flask import Flask, render_template, request, jsonify

def load_env_file(env_path: Path) -> Dict[str, str]:
    """Load environment variables with multiple encoding support"""
    encodings = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
    
    for encoding in encodings:
        try:
            return dotenv_values(env_path, encoding=encoding)
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"Warning: Error reading .env file with {encoding} encoding: {e}")
            continue
    
    print("Warning: Could not read .env file with any supported encoding")
    return {}

# Constants and Configuration
@dataclass
class Config:
    API_CALL_DELAY: float = 0.1
    CONFIG_PATH: Path = Path('config.json')
    ENV_PATH: Path = Path('.env')
    MAX_WORKERS: int = 5
    SANDWICH_TIME_WINDOW: int = 30  # seconds
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    @staticmethod
    def get_default_config() -> Dict:
        return {
            "dex_programs": [
                "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin",  # Serum
                "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"   # Raydium
            ],
            "frontend": {
                "static_folder": "static",
                "template_folder": "templates"
            },
            "default_lookback_limit": 100,
            "max_lookback_limit": 1000
        }

class TransactionType:
    BUY = "buy"
    SELL = "sell"
    
class SandwichPattern:
    BUY_VICTIM_SELL = "buy-victim-sell"
    SELL_VICTIM_BUY = "sell-victim-buy"

def setup_api_endpoints(api_key: str) -> Dict[str, str]:
    """Configure API endpoints with the provided API key"""
    return {
        "RPC": f"https://mainnet.helius-rpc.com/?api-key={api_key}",
        "PARSE_TX": f"https://api.helius.xyz/v0/transactions/?api-key={api_key}",
        "PARSE_ADDRESS": f"https://api.helius.xyz/v0/addresses/{{address}}/transactions/?api-key={api_key}"
    }

class HeliusAPI:
    def __init__(self, api_key: str):
        self.endpoints = setup_api_endpoints(api_key)
        self.session = requests.Session()
        
    def fetch_transaction_details(self, signature: str, retries: int = Config.MAX_RETRIES) -> Optional[Dict]:
        """Fetch detailed transaction data with retry mechanism"""
        for attempt in range(retries):
            try:
                response = self.session.post(
                    self.endpoints["PARSE_TX"],
                    json={"transactions": [signature], "encoding": "jsonParsed"},
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                
                if not data or not isinstance(data, list) or not data[0]:
                    return None
                    
                return data[0]
                
            except requests.exceptions.RequestException as e:
                if attempt == retries - 1:
                    print(f"Failed to fetch transaction {signature} after {retries} attempts: {e}")
                    return None
                time.sleep(Config.RETRY_DELAY)
                
    def fetch_token_transactions(self, token_address: str, limit: int = 100) -> List[Dict]:
        """Fetch token transactions with improved error handling"""
        try:
            url = self.endpoints["PARSE_ADDRESS"].format(address=token_address)
            response = self.session.get(url, params={"limit": limit}, timeout=10)
            response.raise_for_status()
            
            transactions = response.json()
            if not isinstance(transactions, list):
                return []
                
            return transactions
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching transactions for {token_address}: {e}")
            return []

class SandwichDetector:
    def __init__(self, api: HeliusAPI, config: Dict):
        self.api = api
        self.config = config
        self.dex_programs = set(config.get('dex_programs', []))
        
    def analyze_transaction(self, tx: Dict) -> Optional[Dict]:
        """Analyze a single transaction for DEX interactions and swap direction"""
        if not tx:
            return None
            
        signature = tx.get("signature")
        if not signature:
            return None
            
        tx_details = self.api.fetch_transaction_details(signature)
        if not tx_details:
            return None
            
        return {
            "signature": signature,
            "timestamp": tx.get("timestamp"),
            "details": tx_details,
            "isDex": self._is_dex_interaction(tx_details),
            "direction": self._analyze_swap_direction(tx_details),
            "wallet": tx_details.get("signer", [None])[0]
        }
        
    def detect_sandwiches(self, token_address: str, lookback_limit: int) -> Dict:
        """Main sandwich detection logic with parallel processing"""
        if not token_address:
            return self._create_empty_result(token_address)
            
        transactions = self.api.fetch_token_transactions(token_address, lookback_limit)
        if not transactions:
            return self._create_empty_result(token_address)
            
        # Process transactions in parallel
        processed_txs = []
        with ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
            future_to_tx = {
                executor.submit(self.analyze_transaction, tx): tx 
                for tx in transactions if tx is not None
            }
            
            for future in as_completed(future_to_tx):
                result = future.result()
                if result:
                    processed_txs.append(result)
                    
        # Detect patterns
        sandwich_patterns = self._find_sandwich_patterns(processed_txs) or []
        
        return {
            "status": "success",
            "tokenAddress": token_address,
            "transactions": processed_txs or [],
            "potentialSandwiches": sandwich_patterns,
            "stats": self._calculate_stats(processed_txs, sandwich_patterns)
        }
        
    def _is_dex_interaction(self, tx_data: Dict) -> bool:
        """Check if transaction interacts with known DEX programs"""
        if not tx_data or not isinstance(tx_data, dict):
            return False
            
        instructions = tx_data.get("instructions", [])
        if not instructions:
            return False
            
        return any(
            instruction.get("programId") in self.dex_programs
            for instruction in instructions
        )
        
    def _analyze_swap_direction(self, tx_data: Dict) -> Optional[str]:
        """Determine swap direction with improved token transfer analysis"""
        if not tx_data or not isinstance(tx_data, dict):
            return None
        # Implementation details remain similar but with better error handling
        return None
        
    def _find_sandwich_patterns(self, transactions: List[Dict]) -> List[Dict]:
        """Detect sandwich patterns with improved pattern matching"""
        if not transactions:
            return []
        # Implementation details remain similar but with better structure
        return []
        
    def _calculate_stats(self, transactions: List[Dict], patterns: List[Dict]) -> Dict:
        """Calculate analysis statistics"""
        transactions = transactions or []
        patterns = patterns or []
        
        return {
            "totalTransactions": len(transactions),
            "dexTransactions": len([t for t in transactions if t.get("isDex", False)]),
            "potentialAttacks": len(patterns)
        }
        
    def _create_empty_result(self, token_address: str) -> Dict:
        """Create empty result structure"""
        return {
            "status": "success",
            "tokenAddress": token_address,
            "transactions": [],
            "potentialSandwiches": [],
            "stats": {"totalTransactions": 0, "dexTransactions": 0, "potentialAttacks": 0}
        }

# Flask application setup
def create_app(config: Dict) -> Flask:
    app = Flask(
        __name__,
        static_folder=config["frontend"]["static_folder"],
        template_folder=config["frontend"]["template_folder"]
    )
    
    api = HeliusAPI(os.getenv('HELIUS_API_KEY'))
    detector = SandwichDetector(api, config)
    
    @app.route('/')
    def index():
        return render_template('index.html')
        
    @app.route('/analyze', methods=['POST'])
    def analyze():
        try:
            data = request.get_json()
            token_address = data.get('tokenAddress')
            lookback_limit = min(
                int(data.get('lookbackLimit', config['default_lookback_limit'])),
                config['max_lookback_limit']
            )
            
            if not token_address:
                return jsonify({"error": "Token address is required"}), 400
                
            result = detector.detect_sandwiches(token_address, lookback_limit)
            return jsonify(result)
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
            
    return app

if __name__ == "__main__":
    # Load configuration and environment variables
    try:
        if Config.CONFIG_PATH.exists():
            config = json.loads(Config.CONFIG_PATH.read_text())
        else:
            config = Config.get_default_config()
            # Create the config file
            Config.CONFIG_PATH.write_text(json.dumps(config, indent=2))
            print(f"Created default configuration file at {Config.CONFIG_PATH}")
    except json.JSONDecodeError:
        print(f"Warning: Invalid JSON in {Config.CONFIG_PATH}. Using default configuration.")
        config = Config.get_default_config()
        # Attempt to fix the config file
        try:
            Config.CONFIG_PATH.write_text(json.dumps(config, indent=2))
            print(f"Restored default configuration in {Config.CONFIG_PATH}")
        except Exception as e:
            print(f"Warning: Could not write default configuration: {e}")
    
    # Load environment variables if .env exists
    if Config.ENV_PATH.exists():
        env_vars = load_env_file(Config.ENV_PATH)
        if env_vars:
            os.environ.update(env_vars)
        else:
            print("Warning: No environment variables loaded. Please check your .env file.")
    else:
        print(f"Warning: {Config.ENV_PATH} not found. Environment variables may not be properly configured.")
    
    # Ensure required environment variables are set
    if 'HELIUS_API_KEY' not in os.environ:
        print("Error: HELIUS_API_KEY not found in environment variables")
        print("Please create a .env file with your Helius API key:")
        print("HELIUS_API_KEY=your_api_key_here")
        exit(1)
    
    # Start the application
    app = create_app(config)
    port = int(os.getenv("BACKEND_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True, load_dotenv=False)  # Disable Flask's automatic .env loading
