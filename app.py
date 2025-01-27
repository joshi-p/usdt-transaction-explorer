from flask import Flask, request, jsonify, render_template
import requests
import json
import os
import time
from threading import Thread
from collections import defaultdict
from ai import google_ai
app = Flask(__name__)

# Etherscan API Configuration
ETHERSCAN_API_KEY = [YOUR API KEY]

# TRON API Configuration
TRONSCAN_API_KEY = [YOUR API KEY]

# Path to the stub JSON file
STUB_FILE_PATH = "response.json"
USE_STUB = False  # Enable stub mode

# In-memory progress tracking
request_progress = {}

# In-memory result storage
request_results = {}

# Maximum number of requests allowed per second (5 requests per second for Etherscan API)
API_RATE_LIMIT = 5
last_request_time = time.time()  # Track last request time to enforce rate limit
wallet_count = defaultdict(int)  # Track number of wallets processed per request


def fetch_erc20_transactions(address, request_id):
    """Fetch ERC20 transactions for a wallet using Etherscan API or the stub JSON file."""
    global last_request_time
    try:
        if USE_STUB:
            with open(STUB_FILE_PATH, "r") as f:
                data = json.load(f)
            return data
            
        url = f"https://api.etherscan.io/api"
        params = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "apikey": ETHERSCAN_API_KEY,
            "sort": "desc",  # Get most recent transactions first
        }
        
        # Handle rate limiting
        while time.time() - last_request_time < 1 / API_RATE_LIMIT:
            time.sleep(0.1)
        
        last_request_time = time.time()

        response = requests.get(url, params=params)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch transactions: {response.text}")
        
        data = response.json()
        if "status" in data and data["status"] == "1" and "result" in data:
            wallet_count[request_id] += 1
            request_progress[request_id] = {
                "progress": min(30, 70),
                "wallets_processed": wallet_count[request_id]
            }
            
            # Filter transactions where the amount is greater than 0 (convert 'value' to integer)
            filtered_transactions = [
                tx for tx in data["result"]
                if int(tx.get("value", "0")) > 0  # Ensure the value is greater than 0
            ]

            # Process each transaction
            for tx in filtered_transactions:
                # Get the raw value from the transaction (this is in wei)
                raw_value = int(tx.get("value", "0"))  # value is in wei
                
                # Convert from wei to ETH (1 ETH = 10^18 wei)
                eth_value = raw_value / 10**18  # Divide by 10^18 to convert to ETH

                # Format the value to 6 decimal places for display
                formatted_value = f"{eth_value:.6f}"

                # Add the formatted value to the transaction data
                tx["formatted_amount"] = formatted_value

            # Return the first 2 most recent transactions with human-readable values
            return filtered_transactions[:2]  # Only return the first 2 transactions
        else:
            return []
    except Exception as e:
        request_progress[request_id] = {"progress": 100, "error": str(e)}
        return {"error": str(e)}



def fetch_tron_transactions(address, request_id):
    """Fetch TRC20 transactions for a wallet using Tronscan API or the stub JSON file."""
    global last_request_time
    try:
        if USE_STUB:
            with open(STUB_FILE_PATH, "r") as f:
                data = json.load(f)
            return data
        
        # Tronscan API URL and parameters
        url = "https://apilist.tronscan.org/api/transaction"
        params = {
            "address": address,
            "limit": 40,  # Limit to 2 most recent transactions per request
            "start": 0,  # Start from the most recent transaction
            "sort": "-timestamp",  # Sort by descending timestamp to get the latest transactions
            "count": "true",  # Include the total count of transactions
            "start_timestamp": 0,  # Optional: Start timestamp for filter (can be set to 0 for no filter)
            # "end_timestamp": int(time.time() * 1000)  # Current time in milliseconds for end timestamp
        }
        
        # Handle rate limiting
        while time.time() - last_request_time < 1 / API_RATE_LIMIT:
            time.sleep(0.1)
        
        last_request_time = time.time()

        # Send GET request to Tronscan API
        response = requests.get(url, params=params)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch transactions: {response.text}")
        
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            wallet_count[request_id] += 1
            request_progress[request_id] = {
                "progress": min(30, 70),
                "wallets_processed": wallet_count[request_id]
            }
            
            # Filter transactions where the amount is greater than 0
            filtered_transactions = [
                tx for tx in data["data"]
                if int(tx.get("amount", "0")) > 0  # Convert amount from string to integer and check if it's greater than 0
            ]

            # Convert the 'amount' to TRX (1 TRX = 1,000,000 "sun")
            for tx in filtered_transactions:
                # Get raw amount from Tronscan (assuming 'amount' is in 'sun', the smallest unit)
                raw_amount = int(tx.get("amount", "0"))

                # Convert to TRX by dividing by 1 million (since 1 TRX = 1,000,000 sun)
                trx_amount = raw_amount / 1_000_000  # 1,000,000 sun = 1 TRX

                # Optionally, format the amount with a reasonable number of decimals
                formatted_trx = f"{trx_amount:.6f}"  # Format to 6 decimal places

                # Add the formatted TRX amount to the transaction data
                tx["formatted_amount"] = str(formatted_trx)

            # Return the first 2 most recent transactions with the human-readable TRX amounts
            return filtered_transactions[:2]  # Tronscan's response "data" contains the transactions
        else:
            return []


    except Exception as e:
        request_progress[request_id] = {"progress": 100, "error": str(e)}
        return {"error": str(e)}



def build_transaction_tree(address, level=7, current_level=0, request_id=None, processed_addresses=None, root_wallet=None, chain="ERC20"):
    """
    Recursively build a transaction tree, traversing both incoming and outgoing transactions
    up to the specified level.
    """
    try:
        # Initialize tracking sets and variables
        if processed_addresses is None:
            processed_addresses = set()
        if root_wallet is None:
            root_wallet = address  

        # Normalize current address
        address = address

        # Create a base node for the current address
        tree = {"address": address, "transactions": []}

        # Stop conditions
        if current_level >= level:
            return tree

        # Mark address as processed for this branch
        current_branch = processed_addresses.copy()
        current_branch.add(address)

        # Fetch transactions
        if chain == "ERC20":
            transactions = fetch_erc20_transactions(address, request_id)
        elif chain == "TRON":
            transactions = fetch_tron_transactions(address, request_id)

        if isinstance(transactions, dict) and "error" in transactions:
            return {"error": transactions["error"]}

        # Process each transaction
        for tx in transactions:
            # Safely parse the transaction value for TRON

            value = 0

            try:
                if chain == "ERC20":
                    tx_value = tx["formatted_amount"]
                    value = tx_value
                elif chain == "TRON":
                    tx_value = tx["formatted_amount"]
                    value = tx_value
                
                if value == 0:
                    continue

            except (ValueError, TypeError):
                continue

            # Normalize addresses
            if chain == "ERC20":
                from_addr = tx["from"]
                to_addr = tx["to"]
            elif chain == "TRON":
                from_addr = tx["ownerAddress"]
                to_addr = tx["toAddress"]


            # Always explore both directions from the current address
            if address == from_addr and to_addr not in current_branch:
                next_address = to_addr
            elif address == to_addr and from_addr not in current_branch:
                next_address = from_addr
            else:
                next_address = None

            # Build subtree if we have a valid next address
            if next_address:
                subtree = build_transaction_tree(
                    next_address,
                    level,
                    current_level + 1,
                    request_id,
                    current_branch,  # Pass the current branch's processed addresses
                    root_wallet,
                    chain
                )
            else:
                subtree = {"address": to_addr, "transactions": []}

            # Add transaction to tree
            tree["transactions"].append({
                "from": from_addr,
                "to": to_addr,
                "value": value,
                "hash": tx["hash"],
                "subtree": subtree
            })

        # Update progress
        total_possible = min(3 ** (level + 1), 100)
        current_progress = int((len(processed_addresses) / total_possible) * 100)
        request_progress[request_id] = {
            "progress": min(30, 70),
            "wallets_processed": len(processed_addresses),
        }

        if USE_STUB:
            return transactions
        else:
            return tree

    except Exception as e:
        return {"error": f"Error building tree at level {current_level}: {str(e)}"}




def process_request(address, request_id):
    """Handles the long-running process of building the transaction tree."""
    # Initialize progress tracking
    request_progress[request_id] = {"progress": 0, "wallets_processed": 0}
    
    # Calculate the total number of addresses to process
    wallet_count[request_id] = 0  # Reset wallet count for the request
    
    chain = ""
    # Determine which chain to use based on the address
    if address.startswith("T"):
        chain = "TRON"
    else:
        chain = "ERC20"
    
    # Call the transaction tree building function
    tree = build_transaction_tree(address, request_id=request_id, chain=chain)
    
    # Store the final result in the in-memory result storage
    request_results[request_id] = tree

    # Mark request as complete (100%)
    request_progress[request_id] = {
        "progress": 100,
        "wallets_processed": wallet_count[request_id]
    }
    
    return tree

@app.route('/transaction-tree/erc20', methods=['GET'])
def transaction_tree_erc20():
    """API endpoint to generate transaction tree for ERC20."""
    try:
        wallet_address = request.args.get('address')
        if not wallet_address:
            return jsonify({"error": "Missing required parameter: address"}), 400
        
        # Generate a unique request ID for tracking
        request_id = str(time.time())
        
        # Start the processing in a separate thread so the API remains responsive
        thread = Thread(target=process_request, args=(wallet_address, request_id))
        thread.start()
        
        return jsonify({"request_id": request_id, "status": "Processing started"}), 202
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/transaction-tree/progress', methods=['GET'])
def check_progress():
    """API endpoint to check the progress of a specific request."""
    request_id = request.args.get('request_id')
    
    if not request_id:
        return jsonify({"error": "Missing required parameter: request_id"}), 400
    
    # Check the progress of the request
    progress = request_progress.get(request_id, None)
    if progress is None:
        return jsonify({"error": "Request ID not found or not started"}), 404
    
    return jsonify({
        "request_id": request_id, 
        "progress": f"{progress['progress']}%",
        "wallets_processed": progress["wallets_processed"]
    })

@app.route('/transaction-tree/result', methods=['GET'])
def get_result():
    """API endpoint to fetch the final result of a specific request."""
    request_id = request.args.get('request_id')
    
    if not request_id:
        return jsonify({"error": "Missing required parameter: request_id"}), 400
    
    # Check if the result is available
    result = request_results.get(request_id, None)
    if result is None:
        return jsonify({"error": "Result not available yet or invalid request_id"}), 404
    
    return jsonify(result)

@app.route('/transaction-tree/get-ai-analysis', methods=['GET'])
def get_ai_analysis():
    """API endpoint to fetch the final result of a specific request."""
    request_id = request.args.get('request_id')
    
    if not request_id:
        return jsonify({"error": "Missing required parameter: request_id"}), 400
    
    # Check if the result is available
    result = request_results.get(request_id, None)
    if result is None:
        return jsonify({"error": "Result not available yet or invalid request_id"}), 404

    # Getting AI opinion on the wallet    
    ai_opinion = google_ai(result)
    
    return jsonify({
        "request_id": request_id, 
        "ai_opinion": f"{ai_opinion}",
    })

@app.route('/')
def index():
    """Serve the HTML form for user input."""
    return render_template('graph.html')  # Serve your HTML file

if __name__ == "__main__":
    app.run(debug=True)
