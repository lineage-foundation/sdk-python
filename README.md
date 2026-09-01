# Lineage Python SDK

Python SDK for interacting with the Lineage blockchain. This SDK provides a simple interface for wallet operations and blockchain queries.

## Installation

```bash
pip install lineage-sdk
```

The distribution is published as `lineage-sdk`; the import name is `lineage`:

```python
import lineage
```

## Quick Start

### Basic Blockchain Queries

```python
from lineage.blockchain import BlockchainClient

# Initialize blockchain client. api_key is optional and, when set, is sent
# as the x-api-key header on every request.
client = BlockchainClient(
    storage_host='https://storage.lineage.to',
    mempool_host='https://mempool.lineage.to',
    api_key='your-api-key'
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

# Get supply information (requires mempool host) - returns {total, issued}
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

# Initialize wallet from seed. apiKey is optional and, when set, is sent
# as the x-api-key header on every mempool request.
config = {
    'passphrase': 'your-secure-passphrase',
    'mempoolHost': 'https://mempool.lineage.to',
    'storageHost': 'https://storage.lineage.to',
    'valenceHost': 'https://valence.lineage.to',
    'apiKey': 'your-api-key'
}

result = wallet.from_seed(seed_phrase, config)
if result.is_ok:
    print(f"Wallet address: {wallet.get_address()}")
else:
    print(result.error, result.error_message)

# Check balance - fetch_balance returns {balance: {address: {...}}}
balance_result = wallet.fetch_balance([wallet.current_keypair.address])
if balance_result.is_ok:
    print(balance_result.get_ok())

# Create an item asset via POST /v1/items. On success this returns
# {asset, to_address, tx_hash}.
item_result = wallet.create_item_asset(
    secret_key=wallet.current_keypair.secret_key,
    public_key=wallet.current_keypair.public_key,
    amount=1
)
if item_result.is_ok:
    print(item_result.get_ok())

# Send a payment. This builds and signs a real UTXO transaction client-side
# (the same construction as sdk-js) and submits it via POST /v1/transactions.
# On success this returns {transaction_hash, payment_address, asset, used_addresses}.
payment_result = wallet.create_transactions(
    destination_address='recipient-address',
    amount=100
)
if payment_result.is_ok:
    print(payment_result.get_ok())
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
- Construct and submit real, client-signed transactions (payments)
- Create item assets
- Check balances
- Two-way payment protocol support (via the separate valence service)

All of the above talk to the `/v1` REST API on the mempool/storage hosts.
Reads and writes go through `lineage/blockchain.py`'s shared transport,
which maps `application/problem+json` error bodies onto the SDK's
`IResult` error types. The 2-way payment flow (`make_2way_payment`,
`fetch_pending_2way_payments`, `accept_2way_payment`, `reject_2way_payment`)
is unrelated to `/v1` - it talks to the valence node directly and its
wire format hasn't changed.

`create_transactions` now does real work: it fetches the current balance
for the spending addresses, selects UTXOs, builds and signs a
`CreateTransaction` the same way sdk-js does, and submits it to
`POST /v1/transactions`. Previously this only produced a signed payload
without ever confirming it reached the network - callers who relied on
the old behaviour should check `payment_result.get_ok()['transaction_hash']`
to confirm the payment was actually accepted.

## Configuration

The SDK uses environment variables for configuration. Create a `.env` file:

```bash
LINEAGE_PASSPHRASE="your-secure-passphrase"
LINEAGE_STORAGE_HOST="https://storage.lineage.to"
LINEAGE_MEMPOOL_HOST="https://mempool.lineage.to"
LINEAGE_VALENCE_HOST="https://valence.lineage.to"

# Optional - sent as the x-api-key header on every /v1 request
LINEAGE_API_KEY="your-api-key"
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

The suite is offline by default; tests marked `integration` talk to a live network and are excluded from the default run.

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
