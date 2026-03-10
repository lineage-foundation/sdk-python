# Lineage Python SDK

Python SDK for interacting with the Lineage blockchain. This SDK provides a simple interface for wallet operations and blockchain queries.

## Installation

```bash
pip install lineage
```

## Quick Start

### Basic Blockchain Queries

```python
from lineage.blockchain import BlockchainClient

# Initialize blockchain client
client = BlockchainClient(
    storage_host='https://storage.aiblock.dev',
    mempool_host='https://mempool.aiblock.dev'
)

# Query blockchain
latest_block = client.get_latest_block()
if latest_block.is_ok:
    print(f"Latest block: {latest_block.get_ok()['content']['block_num']}")

# Get specific block by number
block = client.get_block_by_num(1)
if block.is_ok:
    print(f"Block 1: {block.get_ok()['content']}")

# Get blockchain entry by hash
entry = client.get_blockchain_entry('some_hash')

# Get transaction by hash
transaction = client.get_transaction_by_hash('tx_hash')

# Get multiple transactions
transactions = client.fetch_transactions(['hash1', 'hash2'])

# Get supply information (requires mempool host)
total_supply = client.get_total_supply()
issued_supply = client.get_issued_supply()
```

### Wallet Operations

```python
from lineage.wallet import Wallet

# Create wallet
wallet = Wallet()

# Generate seed phrase
seed_phrase = wallet.generate_seed_phrase()
print(f"Seed phrase: {seed_phrase}")

# Initialize wallet from seed
config = {
    'passphrase': 'your-secure-passphrase',
    'mempoolHost': 'https://mempool.aiblock.dev',
    'storageHost': 'https://storage.aiblock.dev',
    'valenceHost': 'https://valence.aiblock.dev'
}

result = wallet.from_seed(seed_phrase, config)
if result.is_ok:
    print(f"Wallet address: {wallet.get_address()}")
else:
    print(result.error, result.error_message)
```

## Features

### Blockchain Client
- **get_latest_block()** - Get the latest block information
- **get_block_by_num(block_num)** - Get a specific block by number
- **get_blockchain_entry(hash)** - Get blockchain entry by hash
- **get_transaction_by_hash(tx_hash)** - Get transaction details
- **fetch_transactions(tx_hashes)** - Get multiple transactions
- **get_total_supply()** - Get total token supply
- **get_issued_supply()** - Get issued token supply

### Wallet Operations
- Generate and manage seed phrases
- Create and manage keypairs
- Create and sign transactions
- Create item assets
- Check balances
- Two-way payment protocol support

## Configuration

The SDK uses environment variables for configuration. Create a `.env` file:

```bash
LINEAGE_PASSPHRASE="your-secure-passphrase"
LINEAGE_STORAGE_HOST="https://storage.aiblock.dev"
LINEAGE_MEMPOOL_HOST="https://mempool.aiblock.dev"
LINEAGE_VALENCE_HOST="https://valence.aiblock.dev"
```

## Error Handling

All methods return `IResult` objects with proper error handling:

```python
result = client.get_latest_block()
if result.is_ok:
    data = result.get_ok()
    print(f"Success: {data}")
else:
    print(result.error, result.error_message)
```

## Development

1. Clone the repository
2. Install uv (https://docs.astral.sh/uv/)
3. Run tests: `uv pip install -q pytest requests-mock && uv run pytest -q`

All 68 tests pass, ensuring reliability and compatibility.

## Documentation

- [API Reference](docs/api-reference.md) - Complete API documentation
- [Examples](docs/examples.md) - Usage examples and patterns
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions

## Links

- [Lineage Foundation](https://lineage.foundation)
- [Other SDKs](https://github.com/lineage-foundation) – sdk-python, sdk-php, sdk-js, sdk-laravel

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT – see [LICENSE](LICENSE).
