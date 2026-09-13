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

### Two-way (DRUID) payments

DRUID-based dual double-entry trades: two parties each pay an asset to the
other, atomically correlated by a shared DRUID, and coordinated out-of-band
through a plaintext valence mailbox host (`valenceHost`, see Configuration
below).

```python
# Party A offers to pay sending_asset to payment_address in exchange for
# receiving_asset delivered to receive_keypair's address. Persist the
# returned pending half until fetch_pending_2way_payment reports it settled.
result = wallet_a.make_2way_payment(
    payment_address,   # B's address
    sending_asset,      # e.g. {'Item': {'amount': 50, 'genesis_hash': genesis_hash, 'metadata': None}}
    receiving_asset,    # e.g. {'Token': 100}
    all_keypairs,        # A's keypairs that fund sending_asset
    receive_keypair,      # A's keypair that should receive receiving_asset
)
pending_half = result.get_ok()

# Both parties poll their own mailboxes: incoming offers are surfaced under
# 'pending'; offers this wallet made that the counterparty has accepted are
# submitted and reported under 'settled'.
result = wallet_b.fetch_pending_2way_payment(stored_pending_halves, all_keypairs)
pending, settled = result.get_ok()['pending'], result.get_ok()['settled']

# Party B accepts (submits its half and notifies valence) or rejects
# (notifies valence only) an offer found in `pending`.
wallet_b.accept_2way_payment(details, all_keypairs)
wallet_b.reject_2way_payment(details, all_keypairs)
```

`make_2way_payment` is stateless on this side: it builds and encrypts this
party's transaction half, posts the plaintext offer to valence, and hands the
pending half back to the caller - it does not keep it anywhere itself. The
caller must persist that return value (e.g. to disk, a database) and pass it
back in as one of `stored_pending_halves` on a later
`fetch_pending_2way_payment` call, which is what actually submits and settles
it once the counterparty has accepted.

Because the plaintext valence protocol, the DRUID expectation shapes, and the
transaction halves are all wire-identical across SDKs, a trade offered by
this SDK's `make_2way_payment` can be discovered and accepted by
[`sdk-js`](https://github.com/lineage-foundation/sdk-js)'s,
[`sdk-go`](https://github.com/lineage-foundation/sdk-go)'s, or
[`sdk-php`](https://github.com/lineage-foundation/sdk-php)'s
`fetchPending2WayPayment`/`accept2WayPayment` (and vice versa) - neither side
needs to know which SDK the other party is running.

**BREAKING CHANGE:** this replaces the previous sdk-python 2-way
implementation entirely, and the two are not interoperable. The old scheme
NaCl-`Box`-encrypted each offer and posted it to a `/valence_set` endpoint
(with matching `/fetch_pending_2way_payment(s)`, `/accept_2way_payment`,
`/reject_2way_payment` routes) that no other SDK ever implemented. It has
been removed and replaced by the canonical plaintext `/messages` mailbox
transport (`lineage/valence.py`) that sdk-go and sdk-php also speak, where
every request authenticates by signing the raw mailbox address string with
the caller's own keypair. Any offer created with the old sdk-python 2-way
code cannot be read or settled by this version - there is no migration path
for in-flight offers, only for new trades made after upgrading.

### Live end-to-end script

`scripts/e2e_2way.py` drives a full two-wallet 2-way (DRUID) swap against the
live production hosts (`mempool.lineage.to` / `storage.lineage.to` /
`valence.lineage.to`): wallet A mints an item and offers it in exchange for
tokens from wallet B, B accepts, A settles, and both final balances are
polled to confirm the swap landed atomically.

```bash
python scripts/e2e_2way.py                        # local wallet/keypair setup only
LINEAGE_E2E_WRITE=1 python scripts/e2e_2way.py     # + miner funding and the live swap
```

Wallet/keypair creation is a local operation and always runs;
`LINEAGE_E2E_WRITE=1` additionally funds both wallets from the miner faucet
and drives `make_2way_payment`/`fetch_pending_2way_payment`/
`accept_2way_payment` against the live network. This live e2e is
intentionally kept out of the default test run (see Development below).

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
`fetch_pending_2way_payment`, `accept_2way_payment`, `reject_2way_payment`)
is unrelated to `/v1` for its offer/accept/reject transport - it talks to the
valence node's plaintext `/messages` mailbox directly - though the settled
transaction half is still submitted through `/v1/transactions` like any other
payment. See "Two-way (DRUID) payments" above: this transport is a breaking
change from the previous sdk-python 2-way implementation.

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
