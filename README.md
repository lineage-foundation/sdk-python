# Lineage Python SDK

Python SDK for the Lineage `/v1` REST API: a keyless read client and a key-holding wallet that signs transactions locally.

## Installation

```bash
pip install lineage-sdk
```

The distribution is published as `lineage-sdk`; the import name is `lineage`:

```python
import lineage
```

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

## Quickstart

```python
from lineage.blockchain import BlockchainClient
from lineage.wallet import Wallet

# Keyless reads
client = BlockchainClient(
    storage_host='https://storage.lineage.to',
    mempool_host='https://mempool.lineage.to',
)
latest_block = client.get_latest_block()
if latest_block.is_ok:
    print(latest_block.get_ok()['content']['block_num'])

# Open a wallet from a seed phrase
wallet = Wallet()
seed_phrase = wallet.generate_seed_phrase()
result = wallet.from_seed(seed_phrase, {
    'passphrase': 'your-secure-passphrase',
    'mempoolHost': 'https://mempool.lineage.to',
    'storageHost': 'https://storage.lineage.to',
    'valenceHost': 'https://valence.lineage.to',
})
if result.is_err:
    print(result.error, result.error_message)

# Send a token payment: builds and signs a UTXO transaction client-side
# and submits it via POST /v1/transactions
payment = wallet.create_transactions(
    destination_address='recipient-address',
    amount=100,
)
if payment.is_ok:
    print(payment.get_ok()['transaction_hash'])
```

## Two-way (DRUID) payments

DRUID-based dual double-entry trades: two parties each pay an asset to the
other, atomically correlated by a shared DRUID, and coordinated out-of-band
through a plaintext valence mailbox host (`valenceHost`).

```python
# A offers to pay sending_asset to payment_address for receiving_asset
# delivered to receive_keypair's address. Persist the returned pending
# half until fetch_pending_2way_payment reports it settled.
result = wallet_a.make_2way_payment(
    payment_address,    # B's address
    sending_asset,       # e.g. {'Item': {'amount': 50, 'genesis_hash': genesis_hash, 'metadata': None}}
    receiving_asset,     # e.g. {'Token': 100}
    all_keypairs,        # A's keypairs that fund sending_asset
    receive_keypair,     # A's keypair that should receive receiving_asset
)
pending_half = result.get_ok()

# Both parties poll their own mailboxes: incoming offers surface under
# 'pending'; offers this wallet made that were accepted settle and report
# under 'settled'.
result = wallet_b.fetch_pending_2way_payment(stored_pending_halves, all_keypairs)
pending, settled = result.get_ok()['pending'], result.get_ok()['settled']

# B accepts (submits its half, notifies valence) or rejects (notifies
# valence only) an offer found in `pending`.
wallet_b.accept_2way_payment(details, all_keypairs)
wallet_b.reject_2way_payment(details, all_keypairs)
```

Two-way trades interoperate across all the SDKs and settle atomically through the mempool's DRUID pool, so either party can be on any SDK.

## Wire compatibility

Keys and signatures are byte-for-byte compatible across every Lineage SDK — a wallet (mnemonic) created in one derives the same addresses and produces the same signatures in all of them. sdk-js is the reference implementation; BIP39/BIP32 derivation, SHA3-256 addresses, ed25519 signing, and the `/v1` transaction serialization (field order is load-bearing — you sign exactly what you submit) all match it exactly.

## Testing

```bash
uv pip install -q pytest requests-mock && uv run pytest -q
```

The suite is offline by default; tests marked `integration` talk to a live network and are excluded from the default run. `scripts/e2e_2way.py` drives a full two-wallet 2-way swap against live hosts and only writes with `LINEAGE_E2E_WRITE=1`.

## Documentation

- [API Reference](docs/api-reference.md)
- [Examples](docs/examples.md)
- [Troubleshooting](docs/troubleshooting.md)

## Lineage SDKs

- [JavaScript / TypeScript](https://github.com/lineage-foundation/sdk-js)
- [Python](https://github.com/lineage-foundation/sdk-python)
- [Go](https://github.com/lineage-foundation/sdk-go)
- [Rust](https://github.com/lineage-foundation/sdk-rust)
- [PHP](https://github.com/lineage-foundation/sdk-php)
- [Laravel](https://github.com/lineage-foundation/sdk-laravel)

## License

MIT — see [LICENSE](LICENSE).
