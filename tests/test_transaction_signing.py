"""Gate test: prove lineage/transaction.py matches sdk-js byte-for-byte.

All expected values below are copied verbatim from the golden vector in
`fleet/tasks/sdk-python-tx-signing-spec.md`, which was produced by running
compiled sdk-js against fixed keypairs taken from sdk-js's own test fixtures.
If any assertion here fails, the port is wrong - do not adjust the expected
values, fix the implementation (or stop and report a blocker).
"""

import hashlib
import json

from lineage.transaction import (
    construct_address,
    construct_signature,
    construct_tx_in_out_signable_hash,
    construct_tx_in_signable_asset_hash,
)

# --- Item-creation fixed keypair (from sdk-js's item.mgmt.test.ts) ---

ITEM_PUBLIC_KEY_HEX = "69fee81c9045b35eaf04b74bfa7983618a08acb719ef8d3749a4f004a293cadf"
ITEM_SECRET_KEY_HEX = (
    "fcba9969899335500359aa45ae7008c7dd8b16883dfe8ea39a799259e70f985a"
    "69fee81c9045b35eaf04b74bfa7983618a08acb719ef8d3749a4f004a293cadf"
)
ITEM_ADDRESS = "a0b08e623c6800bb27dddb5d6f6956939be674cfc63399dcc7b9f2e6733c02e5"

# --- 3-address wallet fixed keypairs (from sdk-js's tests/constants.ts) ---

ADDR1_SECRET_KEY_HEX = (
    "787072763976443650373355356b444a7164326d344b64525335466f6654456e"
    "5e6d463ec66d7999769fa4de56f690dfb62e685b97032f5926b0cb6c93ba83c6"
)
ADDR2_SECRET_KEY_HEX = (
    "787072763976443650373355356b444a7346385875626f4e5667526a4472366"
    "358272ba93c1e79df280d4c417de47dbf6a7e330ba52793d7baa8e00ae5c34e59"
)
PAYMENT_ADDRESS = "a0b08e623c6800bb27dddb5d6f6956939be674cfc63399dcc7b9f2e6733c02e5"


def _seed(secret_key_hex: str) -> bytes:
    return bytes.fromhex(secret_key_hex)[:32]


def test_construct_address_matches_golden_vector():
    public_key = bytes.fromhex(ITEM_PUBLIC_KEY_HEX)
    assert construct_address(public_key) == ITEM_ADDRESS


def test_construct_tx_in_signable_asset_hash_token():
    asset_hash = construct_tx_in_signable_asset_hash({"Token": 1})
    assert asset_hash == "a5b2f5e8dcf824aee45b81294ff8049b680285b976cc6c8fa45eb070acfc5974"


def test_construct_tx_in_signable_asset_hash_item():
    asset = {"Item": {"amount": 1000, "genesis_hash": "", "metadata": None}}
    asset_hash = construct_tx_in_signable_asset_hash(asset)
    assert asset_hash == "db8358a1215bbedd3c0489e85afa65cd555bbec83e34502d26b2fbbb0eb1a2d1"


def test_item_creation_signature_matches_golden_vector():
    asset_hash = construct_tx_in_signable_asset_hash(
        {"Item": {"amount": 1000, "genesis_hash": "", "metadata": None}}
    )
    signature = construct_signature(asset_hash, _seed(ITEM_SECRET_KEY_HEX))
    expected = (
        "277d56770697ba1f6cec5e859aa4dcdff0ec4a261c75408092d44a38e768461"
        "a45fc0a7964ecb4714eb2849b0cd4c43e107db76f8a62c6b783342a895889b80c"
    )
    assert signature == expected


def test_tx_in_out_signable_hash_and_signature_scenario_a():
    """createPaymentTx({Token: 60}, locktime=0) - exact payment, no excess."""
    outputs = [
        {
            "value": {"Token": 60},
            "locktime": 0,
            "script_public_key": PAYMENT_ADDRESS,
        }
    ]

    # First input: address 1, previous_out (t_hash=000000, n=0).
    previous_out_1 = {"t_hash": "000000", "n": 0}
    signable_hash_1 = construct_tx_in_out_signable_hash(previous_out_1, outputs)
    assert signable_hash_1 == (
        "41b8515c80bbe065cebcfeae1e1487eec1cd8506a9119030669b8d646a9a568e"
    )
    signature_1 = construct_signature(signable_hash_1, _seed(ADDR1_SECRET_KEY_HEX))
    assert signature_1 == (
        "8c0e700361647f1cb2f5918e97fd3f085dc406d7d776da976438eb423f5bcef1"
        "9a4f9020342423467bd60d438307046c2f2d099e91eaba70c19064b68c7a6406"
    )

    # Second input: address 2, previous_out (t_hash=000001, n=0).
    previous_out_2 = {"t_hash": "000001", "n": 0}
    signable_hash_2 = construct_tx_in_out_signable_hash(previous_out_2, outputs)
    assert signable_hash_2 == (
        "728eb0ea255c492736667c6c61d56cf54534c35b2027f967f4a5cbe649059d32"
    )
    signature_2 = construct_signature(signable_hash_2, _seed(ADDR2_SECRET_KEY_HEX))
    assert signature_2 == (
        "b5cde58d3f85fcde78432fa436cfd520e25bcf217612600d2cf5419db02798cc"
        "7b5ed1082350778b56b60806642c180f5348ce35fb5353b443e2969b88bcd00a"
    )


def test_tx_in_out_signable_hash_null_previous_out():
    """previous_out=None must serialize to the literal string 'null'."""
    outputs = [
        {
            "value": {"Token": 60},
            "locktime": 0,
            "script_public_key": PAYMENT_ADDRESS,
        }
    ]
    # Independently build the expected preimage with the literal string "null"
    # (not by calling the implementation), so this pins None -> "null" rather
    # than asserting the function equals itself.
    outputs_json = "".join(json.dumps(o, separators=(",", ":")) for o in outputs)
    expected = hashlib.sha3_256((outputs_json + "null").encode("utf-8")).hexdigest()
    assert construct_tx_in_out_signable_hash(None, outputs) == expected

    # Guard against None being serialized as "" or "None" instead of "null".
    wrong = hashlib.sha3_256((outputs_json + "").encode("utf-8")).hexdigest()
    assert construct_tx_in_out_signable_hash(None, outputs) != wrong
