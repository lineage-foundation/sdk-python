# AIBlock SDK API Reference

## Installation

```bash
pip install aiblock
```

## Configuration

The SDK requires a configuration dictionary for connecting to the AIBlock network:

```python
config = {
    'passphrase': 'your-secure-passphrase',
    'storageHost': 'https://storage.aiblock.dev',
    'mempoolHost': 'https://mempool.aiblock.dev',
    'valenceHost': 'https://valence.aiblock.dev'
}
```

## BlockchainClient

The `BlockchainClient` class provides methods for interacting with the AIBlock blockchain.

### Initialization

```python
from aiblock.blockchain import BlockchainClient

client = BlockchainClient(
    storage_host='https://storage.aiblock.dev',
    mempool_host='https://mempool.aiblock.dev'  # Optional, required for supply methods
)
```

**Parameters:**
- `storage_host` (str): URL of the storage node (required)
- `mempool_host` (str, optional): URL of the mempool node (required for `get_total_supply` and `get_issued_supply`)

### Methods

All methods return `IResult` objects. Check success with `result.is_ok` and get data with `result.get_ok()` or error with `result.error` and `result.error_message`.

#### get_latest_block()

Get the latest block from the blockchain.

```python
result = client.get_latest_block()
if result.is_ok:
    block_data = result.get_ok()
    print(f"Block number: {block_data['content']['block_num']}")
    print(f"Block hash: {block_data['content']['block_hash']}")
```

**Returns:** Block information including `block_num`, `block_hash`, and `timestamp`.

#### get_block_by_num(block_num)

Get a specific block by its number.

```python
result = client.get_block_by_num(1)
if result.is_ok:
    block_data = result.get_ok()
    print(f"Block: {block_data['content']}")
```

**Parameters:**
- `block_num` (int): Block number to retrieve (must be non-negative)

**Returns:** Block information including `block_num`, `block_hash`, `timestamp`, and `transactions`.

#### get_blockchain_entry(block_hash)

Get blockchain entry by hash.

```python
result = client.get_blockchain_entry('some_block_hash')
if result.is_ok:
    entry_data = result.get_ok()
    print(f"Entry: {entry_data['content']}")
```

**Parameters:**
- `block_hash` (str): Block hash to look up

**Returns:** Blockchain entry information including `block_num`, `block_hash`, `previous_hash`, and `timestamp`.

#### get_transaction_by_hash(tx_hash)

Get transaction details by hash.

```python
result = client.get_transaction_by_hash('transaction_hash')
if result.is_ok:
    tx_data = result.get_ok()
    print(f"Transaction: {tx_data['content']}")
```

**Parameters:**
- `tx_hash` (str): Transaction hash to look up (must be non-empty string)

**Returns:** Transaction information from the blockchain.

#### fetch_transactions(transaction_hashes)

Get multiple transactions by their hashes.

```python
result = client.fetch_transactions(['hash1', 'hash2', 'hash3'])
if result.is_ok:
    transactions_data = result.get_ok()
    print(f"Transactions: {transactions_data['content']}")
```

**Parameters:**
- `transaction_hashes` (list[str]): List of transaction hashes to fetch (must be non-empty, all hashes must be non-empty strings)

**Returns:** Multiple transaction information from the blockchain.

#### get_total_supply()

Get the total token supply. **Requires mempool host.**

```python
result = client.get_total_supply()
if result.is_ok:
    supply_data = result.get_ok()
    print(f"Total supply: {supply_data['content']['total_supply']}")
```

**Returns:** Total supply information.

#### get_issued_supply()

Get the issued token supply. **Requires mempool host.**

```python
result = client.get_issued_supply()
if result.is_ok:
    supply_data = result.get_ok()
    print(f"Issued supply: {supply_data['content']['issued_supply']}")
```

**Returns:** Issued supply information.

## Wallet

The `Wallet` class manages cryptographic keys and blockchain addresses.

### Initialization

```python
from aiblock.wallet import Wallet

# Create new wallet
wallet = Wallet()

# Generate seed phrase
seed_phrase = wallet.generate_seed_phrase()
print(f"Seed phrase: {seed_phrase}")
```

### Configuration

```python
config = {
    'passphrase': 'your-secure-passphrase',
    'mempoolHost': 'https://mempool.aiblock.dev',
    'storageHost': 'https://storage.aiblock.dev',
    'valenceHost': 'https://valence.aiblock.dev'
}

# Initialize wallet from seed
result = wallet.from_seed(seed_phrase, config)
if result.is_ok:
    print(f"Wallet initialized successfully")
    print(f"Address: {wallet.get_address()}")
else:
    print(f"Error: {result.error_message}")
```

### Key Methods

#### generate_seed_phrase()
Generate a new BIP39 seed phrase.

```python
seed_phrase = wallet.generate_seed_phrase()
```

#### from_seed(seed_phrase, config, init_offline=False)
Initialize wallet from seed phrase.

**Parameters:**
- `seed_phrase` (str): BIP39 seed phrase
- `config` (dict): Configuration dictionary with hosts and passphrase
- `init_offline` (bool): Initialize in offline mode (default: False)

#### get_address()
Get the wallet's blockchain address.

```python
address = wallet.get_address()
```

## Error Handling

All methods return `IResult` objects with consistent error handling:

```python
result = client.get_latest_block()

if result.is_ok:
    # Success - get the data
    data = result.get_ok()
    print(f"Success: {data}")
else:
    # Error - get error information
    print(f"Error type: {result.error}")
    print(f"Error message: {result.error_message}")
```

### Common error mappings

- NotFound: 404 responses from nodes
- BadRequest: 400/405 invalid requests
- InvalidParametersProvided: invalid inputs or 202 pending
- NetworkError: connection/timeouts
- InternalServerError/ServiceUnavailable/GatewayTimeout: 5xx errors
- NetworkNotInitialized: required host missing for endpoint

## Environment Variables

You can use environment variables for configuration:

```bash
# .env file
AIBLOCK_PASSPHRASE=your-secure-passphrase
AIBLOCK_STORAGE_HOST=https://storage.aiblock.dev
AIBLOCK_MEMPOOL_HOST=https://mempool.aiblock.dev
AIBLOCK_VALENCE_HOST=https://valence.aiblock.dev
```

```python
from aiblock.config import get_config

config = get_config()  # Loads from environment variables
```

## Response Format

All successful API responses follow this format:

```python
{
    'id': 'unique-response-id',
    'status': 'success',
    'reason': 'Operation completed successfully',
    'content': {
        # Method-specific data here
    }
}
```

## Host Requirements

- **Storage Host**: Required for all blockchain query methods
- **Mempool Host**: Required only for `get_total_supply()` and `get_issued_supply()`
- **Valence Host**: Required for wallet operations involving the network

<!-- Type-specific response classes are not exposed; use dicts returned in IResult content -->

## Best Practices

1. Always check IResult:
```python
result = client.get_latest_block()
if result.is_ok:
    data = result.get_ok()
else:
    print(result.error, result.error_message)
```

2. Validate inputs before sending:
```python
def validate_metadata(metadata: dict) -> bool:
    try:
        # Ensure metadata is JSON serializable
        json.dumps(metadata)
        return True
    except Exception:
        return False
```