# AIBlock SDK Examples

This document provides practical examples of using the AIBlock SDK for various blockchain operations.

## Setup

First, install the SDK and set up your environment:

```bash
pip install aiblock
```

Create a `.env` file:
```bash
AIBLOCK_STORAGE_HOST=https://storage.aiblock.dev
AIBLOCK_MEMPOOL_HOST=https://mempool.aiblock.dev
AIBLOCK_VALENCE_HOST=https://valence.aiblock.dev
AIBLOCK_PASSPHRASE=your-secure-passphrase
```

## Basic Blockchain Queries

### Getting Latest Block Information

```python
from aiblock.blockchain import BlockchainClient

# Initialize client
client = BlockchainClient(
    storage_host='https://storage.aiblock.dev',
    mempool_host='https://mempool.aiblock.dev'
)

# Get latest block
result = client.get_latest_block()
if result.is_ok:
    block_data = result.get_ok()
    print(f"Latest block number: {block_data['content']['block_num']}")
    print(f"Block hash: {block_data['content']['block_hash']}")
    print(f"Timestamp: {block_data['content']['timestamp']}")
else:
    print(result.error, result.error_message)
```

### Querying Historical Blocks

```python
def get_block_info(client, block_number):
    """Get information about a specific block"""
    result = client.get_block_by_num(block_number)
    
    if result.is_ok:
        block_data = result.get_ok()
        content = block_data['content']
        
        print(f"Block {block_number}:")
        print(f"  Hash: {content['block_hash']}")
        print(f"  Timestamp: {content['timestamp']}")
        print(f"  Transactions: {len(content.get('transactions', []))}")
        
        return content
    else:
        print(f"Error getting block {block_number}: {result.error_message}")
        return None

# Example usage
block_info = get_block_info(client, 1)
```

### Supply Information

```python
def get_supply_info(client):
    """Get total and issued supply information"""
    
    # Get total supply
    total_result = client.get_total_supply()
    if total_result.is_ok:
        total_data = total_result.get_ok()
        print(f"Total supply: {total_data['content']['total_supply']}")
    else:
        print(total_result.error, total_result.error_message)
    
    # Get issued supply
    issued_result = client.get_issued_supply()
    if issued_result.is_ok:
        issued_data = issued_result.get_ok()
        print(f"Issued supply: {issued_data['content']['issued_supply']}")
    else:
        print(issued_result.error, issued_result.error_message)

# Example usage
get_supply_info(client)
```

## Transaction Queries

### Getting Transaction by Hash

```python
def get_transaction_details(client, tx_hash):
    """Get detailed information about a transaction"""
    if not tx_hash or not tx_hash.strip():
        print("Error: Transaction hash cannot be empty")
        return None
    
    result = client.get_transaction_by_hash(tx_hash)
    
    if result.is_ok:
        tx_data = result.get_ok()
        print(f"Transaction {tx_hash}:")
        print(f"  Status: {tx_data['status']}")
        print(f"  Content: {tx_data['content']}")
        return tx_data
    else:
        print(result.error, result.error_message)
        return None

# Example usage
tx_hash = "your_transaction_hash_here"
transaction = get_transaction_details(client, tx_hash)
```

### Batch Transaction Queries

```python
def fetch_multiple_transactions(client, tx_hashes):
    """Fetch multiple transactions in a single request"""
    if not tx_hashes:
        print("Error: Transaction hash list cannot be empty")
        return None
    
    # Validate all hashes are non-empty
    valid_hashes = [h for h in tx_hashes if h and h.strip()]
    if len(valid_hashes) != len(tx_hashes):
        print("Error: All transaction hashes must be non-empty strings")
        return None
    
    result = client.fetch_transactions(valid_hashes)
    
    if result.is_ok:
        transactions_data = result.get_ok()
        print(f"Retrieved {len(valid_hashes)} transactions")
        return transactions_data
    else:
        print(result.error, result.error_message)
        return None

# Example usage
tx_hashes = ["hash1", "hash2", "hash3"]
transactions = fetch_multiple_transactions(client, tx_hashes)
```

## Wallet Operations

### Creating and Initializing a Wallet

```python
from aiblock.wallet import Wallet

def create_new_wallet():
    """Create a new wallet with a generated seed phrase"""
    wallet = Wallet()
    
    # Generate a new seed phrase
    seed_phrase = wallet.generate_seed_phrase()
    print(f"Generated seed phrase: {seed_phrase}")
    print("⚠️  Store this seed phrase securely!")
    
    # Configuration
    config = {
        'passphrase': 'your-secure-passphrase',
        'mempoolHost': 'https://mempool.aiblock.dev',
        'storageHost': 'https://storage.aiblock.dev',
        'valenceHost': 'https://valence.aiblock.dev'
    }
    
    # Initialize wallet from seed
    result = wallet.from_seed(seed_phrase, config)
    
    if result.is_ok:
        print("✅ Wallet initialized successfully")
        print(f"Address: {wallet.get_address()}")
        return wallet, seed_phrase
    else:
        print("❌", result.error, result.error_message)
        return None, None

# Example usage
wallet, seed = create_new_wallet()
```

### Restoring a Wallet from Seed

```python
def restore_wallet_from_seed(seed_phrase):
    """Restore a wallet from an existing seed phrase"""
    wallet = Wallet()
    
    config = {
        'passphrase': 'your-secure-passphrase',
        'mempoolHost': 'https://mempool.aiblock.dev',
        'storageHost': 'https://storage.aiblock.dev',
        'valenceHost': 'https://valence.aiblock.dev'
    }
    
    result = wallet.from_seed(seed_phrase, config)
    
    if result.is_ok:
        print("✅ Wallet restored successfully")
        print(f"Address: {wallet.get_address()}")
        return wallet
    else:
        print("❌", result.error, result.error_message)
        return None

# Example usage
existing_seed = "your twelve word seed phrase goes here like this example"
restored_wallet = restore_wallet_from_seed(existing_seed)
```

### Offline Wallet Operations

```python
def create_offline_wallet(seed_phrase):
    """Create a wallet for offline operations (key generation, signing)"""
    wallet = Wallet()
    
    config = {
        'passphrase': 'your-secure-passphrase',
        # Hosts not required for offline operations
        'mempoolHost': '',
        'storageHost': '',
        'valenceHost': ''
    }
    
    # Initialize in offline mode
    result = wallet.from_seed(seed_phrase, config, init_offline=True)
    
    if result.is_ok:
        print("✅ Offline wallet initialized successfully")
        print(f"Address: {wallet.get_address()}")
        return wallet
    else:
        print("❌", result.error, result.error_message)
        return None

# Example usage
offline_wallet = create_offline_wallet("your seed phrase here")
```

## Error Handling Patterns

### Robust Error Handling

```python
def robust_blockchain_query(client):
    """Example of comprehensive error handling"""
    
    try:
        # Attempt to get latest block
        result = client.get_latest_block()
        
        if result.is_ok:
            block_data = result.get_ok()
            print(f"✅ Success: Got block {block_data['content']['block_num']}")
            return block_data
        else:
            print("❌", result.error, result.error_message)
            
            # Handle specific error types
            if "Connection" in error_msg:
                print("🔄 Retrying with different host...")
                # Could implement retry logic here
            elif "timeout" in error_msg.lower():
                print("⏱️  Request timed out, try again later")
            
            return None
            
    except Exception as e:
        print(f"💥 Unexpected error: {str(e)}")
        return None

# Example usage
block_data = robust_blockchain_query(client)
```

### Input Validation

```python
def validate_and_query_block(client, block_num):
    """Example of input validation before API calls"""
    
    # Validate input
    if not isinstance(block_num, int):
        print("❌ Block number must be an integer")
        return None
    
    if block_num < 0:
        print("❌ Block number must be non-negative")
        return None
    
    # Make the API call
    result = client.get_block_by_num(block_num)
    
    if result.is_ok:
        return result.get_ok()
    else:
        print("❌", result.error, result.error_message)
        return None

# Example usage
block_data = validate_and_query_block(client, 1)
```

## Configuration Management

### Using Environment Variables

```python
import os
from aiblock.config import get_config

def setup_from_environment():
    """Setup client using environment variables"""
    
    # Load configuration from environment
    config = get_config()
    
    # Initialize client
    client = BlockchainClient(
        storage_host=config.get('storageHost'),
        mempool_host=config.get('mempoolHost')
    )
    
    print("✅ Client configured from environment variables")
    return client

# Example usage
client = setup_from_environment()
```

### Configuration Validation

```python
def validate_configuration(config):
    """Validate configuration before using"""
    required_keys = ['storageHost', 'passphrase']
    optional_keys = ['mempoolHost', 'valenceHost']
    
    # Check required keys
    for key in required_keys:
        if key not in config or not config[key]:
            print(f"❌ Missing required configuration: {key}")
            return False
    
    # Validate URLs
    for key in ['storageHost', 'mempoolHost', 'valenceHost']:
        if key in config and config[key]:
            if not config[key].startswith(('http://', 'https://')):
                print(f"❌ Invalid URL format for {key}: {config[key]}")
                return False
    
    print("✅ Configuration is valid")
    return True

# Example usage
config = {
    'passphrase': 'secure-passphrase',
    'storageHost': 'https://storage.aiblock.dev',
    'mempoolHost': 'https://mempool.aiblock.dev'
}

if validate_configuration(config):
    # Proceed with initialization
    pass
```

## Best Practices

### 1. Always Check Results

```python
# ✅ Good
result = client.get_latest_block()
if result.is_ok:
    data = result.get_ok()
    # Process data
else:
    print(f"Error: {result.error_message}")

# ❌ Bad - don't assume success
data = client.get_latest_block().get_ok()  # Could raise exception
```

### 2. Validate Inputs

```python
# ✅ Good
def safe_get_transaction(client, tx_hash):
    if not tx_hash or not isinstance(tx_hash, str) or not tx_hash.strip():
        return None
    return client.get_transaction_by_hash(tx_hash.strip())

# ❌ Bad - no validation
def unsafe_get_transaction(client, tx_hash):
    return client.get_transaction_by_hash(tx_hash)
```

### 3. Handle Network Issues

```python
import time

def retry_request(client, operation, max_retries=3, delay=1):
    """Retry failed requests with exponential backoff"""
    for attempt in range(max_retries):
        result = operation()
        
        if result.is_ok:
            return result
        
        if "Connection" in result.error_message and attempt < max_retries - 1:
            wait_time = delay * (2 ** attempt)
            print(f"Retry {attempt + 1}/{max_retries} in {wait_time}s...")
            time.sleep(wait_time)
        else:
            break
    
    return result

# Example usage
result = retry_request(client, lambda: client.get_latest_block())
```

### 4. Secure Seed Phrase Handling

```python
import getpass

def secure_seed_input():
    """Securely input seed phrase without echoing to terminal"""
    print("Enter your seed phrase (input will be hidden):")
    seed_phrase = getpass.getpass("Seed phrase: ")
    return seed_phrase.strip()

# Example usage
seed = secure_seed_input()
```

This documentation provides practical, working examples that align with the current AIBlock SDK implementation. 