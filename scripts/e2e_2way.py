#!/usr/bin/env python3
"""Live end-to-end two-wallet 2-way (DRUID) swap against the deployed /v1
Lineage network + valence mailbox relay.

Wallet A mints an item and offers it in exchange for tokens from wallet B;
B accepts; A settles. Both wallets' final balances are polled to confirm
the swap landed atomically (A ends up with the tokens, B ends up with the
item). Mirrors sdk-go's TestTwoWaySwap_Live (twoway_e2e_test.go) and
sdk-php's scripts/e2e-2way.php.

Wallet/keypair creation is a local crypto operation only, so it always
runs. Set LINEAGE_E2E_WRITE=1 to also fund both wallets from the miner
faucet and drive the swap itself against the live network.

Usage:
    python scripts/e2e_2way.py                        # local setup only
    LINEAGE_E2E_WRITE=1 python scripts/e2e_2way.py     # + full live swap
"""

import os
import sys
import time
from typing import Any, Callable, Optional

import requests

# Allow running directly out of a checkout (`python scripts/e2e_2way.py`)
# without requiring the package to be installed first.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineage.key_handler import generate_keypair  # noqa: E402
from lineage.wallet import Wallet  # noqa: E402

MEMPOOL_HOST = "https://mempool.lineage.to"
STORAGE_HOST = "https://storage.lineage.to"
VALENCE_HOST = "https://valence.lineage.to"
MINER_HOST = "https://miner.lineage.to"

ITEM_AMOUNT = 50  # items A mints and offers
TOKEN_AMOUNT = 100  # tokens B pays and A receives
FUND_TOKENS_A = 1000  # just enough for A to exist as a funded address
FUND_TOKENS_B = 1000  # must cover TOKEN_AMOUNT

failures = 0


def step(name: str, fn: Callable[[], Any]) -> Optional[Any]:
    """Run `fn`, print "<name> ... ok" or "<name> ... ERR: <message>", and
    return `fn`'s result (or None on failure)."""
    global failures

    print(name.ljust(42, "."), end="", flush=True)
    try:
        result = fn()
        print(" ok")
        return result
    except Exception as e:  # noqa: BLE001 - report and continue, like the PHP/Go e2e
        failures += 1
        print(f" ERR: {e}")
        return None


def poll_until(label: str, check: Callable[[], bool], attempts: int = 24, delay_seconds: int = 5) -> bool:
    """Poll `check` up to `attempts` times (sleeping `delay_seconds` between
    each) until it returns True. A transient exception from `check` counts
    as "not yet" rather than aborting the poll. Prints whether/when it was
    confirmed."""
    for i in range(attempts):
        try:
            if check():
                print(f"  {label}: confirmed after {i + 1} poll(s)")
                return True
        except Exception as e:  # noqa: BLE001
            print(f"  {label}: poll error ({e}), retrying")
        time.sleep(delay_seconds)

    print(f"  {label}: NOT confirmed after {attempts} polls")
    return False


def fund_from_miner(address: str, amount: int) -> dict:
    response = requests.post(
        f"{MINER_HOST}/v1/payments",
        json={"kind": "address", "address": address, "amount": amount, "passphrase": ""},
        timeout=30,
    )
    if not (200 <= response.status_code < 300):
        raise RuntimeError(f"miner funding failed: HTTP {response.status_code} {response.text}")
    return response.json()


def make_wallet(passphrase: str) -> Wallet:
    """Build a `Wallet` wired up to the live hosts. Matches the shape
    `tests/test_twoway_flow.py`'s `_make_wallet()` helper uses to drive the
    2-way flow methods directly, without going through `init_new`/`from_seed`.
    """
    wallet = Wallet(debug=False)
    wallet.network_config = {
        "mempoolHost": MEMPOOL_HOST,
        "storageHost": STORAGE_HOST,
        "valenceHost": VALENCE_HOST,
    }
    wallet.routes_initialized = True
    wallet.passphrase_key = passphrase.encode("utf-8")
    return wallet


def unwrap(result, message: str):
    """Raise with `result`'s error message if it's an error `IResult`,
    otherwise return its value."""
    if result.is_err:
        raise RuntimeError(f"{message}: {result.error_message}")
    return result.get_ok()


def balance_tokens(wallet: Wallet, address: str) -> int:
    balance = unwrap(wallet.fetch_balance([address]), "fetch_balance")
    return balance.get("total", {}).get("tokens", 0)


def balance_items(wallet: Wallet, address: str, genesis_hash: str) -> int:
    balance = unwrap(wallet.fetch_balance([address]), "fetch_balance")
    return balance.get("total", {}).get("items", {}).get(genesis_hash, 0)


print("== Lineage sdk-python 2-way (DRUID) e2e ==")
print(f"mempool: {MEMPOOL_HOST}")
print(f"storage: {STORAGE_HOST}")
print(f"valence: {VALENCE_HOST}\n")

print("-- local setup --")

wallet_a = make_wallet("lineage-e2e-2way-a-" + os.urandom(4).hex())
wallet_b = make_wallet("lineage-e2e-2way-b-" + os.urandom(4).hex())

kp_a = step("A: generate_keypair", lambda: unwrap(generate_keypair(), "generate_keypair"))
kp_b = step("B: generate_keypair", lambda: unwrap(generate_keypair(), "generate_keypair"))

if kp_a is None or kp_b is None:
    print("cannot continue without keypairs")
    sys.exit(1)

print(f"A address: {kp_a.address}")
print(f"B address: {kp_b.address}\n")

if os.environ.get("LINEAGE_E2E_WRITE") != "1":
    print("LINEAGE_E2E_WRITE not set to 1 - skipping the live swap.")
    sys.exit(1 if failures else 0)

print("-- wallet A: fund + mint item --")

step("A: fund from miner", lambda: fund_from_miner(kp_a.address, FUND_TOKENS_A))

poll_until("A funded", lambda: balance_tokens(wallet_a, kp_a.address) > 0)

item_result = step(
    "A: create_item_asset",
    lambda: unwrap(
        wallet_a.create_item_asset(
            secret_key=kp_a.secret_key,
            public_key=kp_a.public_key,
            version=kp_a.version,
            amount=ITEM_AMOUNT,
        ),
        "create_item_asset",
    ),
)

genesis_hash = (item_result or {}).get("asset", {}).get("genesis_hash")

if not genesis_hash:
    print("cannot continue without a genesis hash from create_item_asset")
    sys.exit(1)

poll_until("A item minted", lambda: balance_items(wallet_a, kp_a.address, genesis_hash) >= ITEM_AMOUNT)

print("\n-- wallet B: fund with tokens --")

step("B: fund from miner", lambda: fund_from_miner(kp_b.address, FUND_TOKENS_B))

poll_until("B funded", lambda: balance_tokens(wallet_b, kp_b.address) >= TOKEN_AMOUNT)

print("\n-- A: make_2way_payment (offer item, want tokens) --")

sending_asset = {"Item": {"amount": ITEM_AMOUNT, "genesis_hash": genesis_hash, "metadata": None}}
receiving_asset = {"Token": TOKEN_AMOUNT}

half = step(
    "A: make_2way_payment",
    lambda: unwrap(
        wallet_a.make_2way_payment(kp_b.address, sending_asset, receiving_asset, [kp_a], kp_a),
        "make_2way_payment",
    ),
)

if half is None:
    print("cannot continue without a pending half")
    sys.exit(1)

# The caller is responsible for persisting the pending half returned by
# make_2way_payment until fetch_pending_2way_payment reports it settled;
# here that's simply this local variable, since both parties run in this
# one script/process.
stored_half = half

print("\n-- B: fetch_pending_2way_payment sees the offer, then accept_2way_payment --")


def b_discovers_offer():
    result = unwrap(wallet_b.fetch_pending_2way_payment([], [kp_b]), "fetch_pending_2way_payment")
    if half["druid"] not in result["pending"]:
        raise RuntimeError(f"B did not see A's offer for druid {half['druid']}")
    return result["pending"][half["druid"]]


offer = step("B: fetch_pending_2way_payment (sees offer)", b_discovers_offer)

if offer is None:
    print("cannot continue without B having seen the offer")
    sys.exit(1)

step(
    "B: accept_2way_payment",
    lambda: unwrap(wallet_b.accept_2way_payment(offer, [kp_b]), "accept_2way_payment"),
)

print("\n-- A: fetch_pending_2way_payment settles the swap --")


def a_settles():
    result = unwrap(wallet_a.fetch_pending_2way_payment([stored_half], [kp_a]), "fetch_pending_2way_payment")
    if stored_half["druid"] not in result["settled"]:
        raise RuntimeError(f"druid {stored_half['druid']} was not settled (settled={result['settled']})")


step("A: fetch_pending_2way_payment (settle)", a_settles)

print("\n-- poll final balances: A should hold the tokens, B should hold the item --")

a_settled = poll_until("A tokens landed", lambda: balance_tokens(wallet_a, kp_a.address) >= TOKEN_AMOUNT)
b_settled = poll_until("B item landed", lambda: balance_items(wallet_b, kp_b.address, genesis_hash) >= ITEM_AMOUNT)

if not a_settled:
    failures += 1
    print(f"A: expected >= {TOKEN_AMOUNT} tokens after the swap, but they never landed")

if not b_settled:
    failures += 1
    print(f"B: expected >= {ITEM_AMOUNT} items after the swap, but they never landed")

print(f"\ndone. failures: {failures}")
sys.exit(1 if failures else 0)
