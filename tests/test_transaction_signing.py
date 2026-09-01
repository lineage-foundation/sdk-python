"""Gate test: prove lineage/transaction.py matches sdk-js byte-for-byte.

All expected values below are copied verbatim from the golden vector in
`fleet/tasks/sdk-python-tx-signing-spec.md`, which was produced by running
compiled sdk-js against fixed keypairs taken from sdk-js's own test fixtures.
If any assertion here fails, the port is wrong - do not adjust the expected
values, fix the implementation (or stop and report a blocker).
"""

import hashlib
import json

from lineage.interfaces import IKeypair
from lineage.transaction import (
    construct_address,
    construct_signature,
    construct_tx_in_out_signable_hash,
    construct_tx_in_signable_asset_hash,
    create_payment_tx,
    update_signatures,
)

# --- Item-creation fixed keypair (from sdk-js's item.mgmt.test.ts) ---

ITEM_PUBLIC_KEY_HEX = "69fee81c9045b35eaf04b74bfa7983618a08acb719ef8d3749a4f004a293cadf"
ITEM_SECRET_KEY_HEX = (
    "fcba9969899335500359aa45ae7008c7dd8b16883dfe8ea39a799259e70f985a"
    "69fee81c9045b35eaf04b74bfa7983618a08acb719ef8d3749a4f004a293cadf"
)
ITEM_ADDRESS = "a0b08e623c6800bb27dddb5d6f6956939be674cfc63399dcc7b9f2e6733c02e5"

# --- 3-address wallet fixed keypairs (from sdk-js's tests/constants.ts) ---

ADDR1_ADDRESS = "cf0067d6c42463b2c1e4236e9669df546c74b16c0e2ef37114549b2944e05b7c"
ADDR1_PUBLIC_KEY_HEX = "5e6d463ec66d7999769fa4de56f690dfb62e685b97032f5926b0cb6c93ba83c6"
ADDR1_SECRET_KEY_HEX = (
    "787072763976443650373355356b444a7164326d344b64525335466f6654456e"
    "5e6d463ec66d7999769fa4de56f690dfb62e685b97032f5926b0cb6c93ba83c6"
)
ADDR2_ADDRESS = "f226b92e6868e178f722e9cf71ad2a0c16d864c5d8fcadc70153bbd021f11ea0"
ADDR2_PUBLIC_KEY_HEX = "58272ba93c1e79df280d4c417de47dbf6a7e330ba52793d7baa8e00ae5c34e59"
ADDR2_SECRET_KEY_HEX = (
    "787072763976443650373355356b444a7346385875626f4e5667526a4472366"
    "358272ba93c1e79df280d4c417de47dbf6a7e330ba52793d7baa8e00ae5c34e59"
)
ADDR3_ADDRESS = "9b28bf45e5e5285a8eb10003046f5ed48571903ea767915acf0fe77e257b43fa"
ADDR3_PUBLIC_KEY_HEX = "efa9dcba0f3282b3ed4a6aa1ccdb169d6685a30d7b2af7a2171a5682f3112359"
ADDR3_SECRET_KEY_HEX = (
    "787072763976443650373355356b444a7545555a35434479585a535038417558"
    "efa9dcba0f3282b3ed4a6aa1ccdb169d6685a30d7b2af7a2171a5682f3112359"
)
PAYMENT_ADDRESS = "a0b08e623c6800bb27dddb5d6f6956939be674cfc63399dcc7b9f2e6733c02e5"
EXCESS_ADDRESS = "f226b92e6868e178f722e9cf71ad2a0c16d864c5d8fcadc70153bbd021f11ea0"


def _seed(secret_key_hex: str) -> bytes:
    return bytes.fromhex(secret_key_hex)[:32]


def _keypair(address: str, public_key_hex: str, secret_key_hex: str) -> IKeypair:
    return IKeypair(
        address=address,
        secret_key=_seed(secret_key_hex),
        public_key=bytes.fromhex(public_key_hex),
        version=1,
    )


def _wallet_keypairs():
    return {
        ADDR1_ADDRESS: _keypair(ADDR1_ADDRESS, ADDR1_PUBLIC_KEY_HEX, ADDR1_SECRET_KEY_HEX),
        ADDR2_ADDRESS: _keypair(ADDR2_ADDRESS, ADDR2_PUBLIC_KEY_HEX, ADDR2_SECRET_KEY_HEX),
        ADDR3_ADDRESS: _keypair(ADDR3_ADDRESS, ADDR3_PUBLIC_KEY_HEX, ADDR3_SECRET_KEY_HEX),
    }


def _fetch_balance_response():
    """Fixed 3-address UTXO set from sdk-js's `src/tests/constants.ts`."""
    return {
        "total": {"tokens": 1060, "items": {"default_genesis_hash_spec": 3}},
        "address_list": {
            ADDR1_ADDRESS: [
                {"out_point": {"t_hash": "000000", "n": 0}, "value": {"Token": 10}},
                {
                    "out_point": {"t_hash": "000000", "n": 1},
                    "value": {
                        "Item": {
                            "amount": 3,
                            "genesis_hash": "default_genesis_hash_spec",
                            "metadata": "{'test': 'test'}",
                        }
                    },
                },
            ],
            ADDR2_ADDRESS: [
                {"out_point": {"t_hash": "000001", "n": 0}, "value": {"Token": 50}},
            ],
            ADDR3_ADDRESS: [
                {"out_point": {"t_hash": "000002", "n": 0}, "value": {"Token": 1000}},
            ],
        },
    }


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


def test_create_payment_tx_scenario_a_exact_payment_matches_golden_vector():
    """createPaymentTx({Token: 60}, locktime=0) - exact payment, no excess.

    Expected `ICreateTransaction` copied verbatim from the spec's golden
    vector (Scenario A), not computed from the implementation.
    """
    result = create_payment_tx(
        PAYMENT_ADDRESS,
        {"Token": 60},
        EXCESS_ADDRESS,
        _fetch_balance_response(),
        _wallet_keypairs(),
        0,
    )

    expected_create_tx = {
        "inputs": [
            {
                "previous_out": {"t_hash": "000000", "n": 0},
                "script_signature": {
                    "Pay2PkH": {
                        "signable_data": (
                            "41b8515c80bbe065cebcfeae1e1487eec1cd8506a9119030669b8d646a9a568e"
                        ),
                        "signature": (
                            "8c0e700361647f1cb2f5918e97fd3f085dc406d7d776da976438eb423f5bcef1"
                            "9a4f9020342423467bd60d438307046c2f2d099e91eaba70c19064b68c7a6406"
                        ),
                        "public_key": ADDR1_PUBLIC_KEY_HEX,
                        "address_version": None,
                    }
                },
            },
            {
                "previous_out": {"t_hash": "000001", "n": 0},
                "script_signature": {
                    "Pay2PkH": {
                        "signable_data": (
                            "728eb0ea255c492736667c6c61d56cf54534c35b2027f967f4a5cbe649059d32"
                        ),
                        "signature": (
                            "b5cde58d3f85fcde78432fa436cfd520e25bcf217612600d2cf5419db02798cc"
                            "7b5ed1082350778b56b60806642c180f5348ce35fb5353b443e2969b88bcd00a"
                        ),
                        "public_key": ADDR2_PUBLIC_KEY_HEX,
                        "address_version": None,
                    }
                },
            },
        ],
        "outputs": [
            {
                "value": {"Token": 60},
                "locktime": 0,
                "script_public_key": PAYMENT_ADDRESS,
            }
        ],
        "version": 2,
        "druid_info": None,
    }

    assert result["create_tx"] == expected_create_tx
    assert result["excess_address_used"] is False
    assert result["used_addresses"] == [ADDR1_ADDRESS, ADDR2_ADDRESS]


def test_create_payment_tx_scenario_b_with_excess_matches_golden_vector():
    """createPaymentTx({Token: 5}, locktime=99) - excess output present.

    Confirms the excess output always uses locktime 0 regardless of the
    caller-supplied locktime on the payment output (hazard 8). Expected
    values copied verbatim from the spec's golden vector (Scenario B).
    """
    result = create_payment_tx(
        PAYMENT_ADDRESS,
        {"Token": 5},
        EXCESS_ADDRESS,
        _fetch_balance_response(),
        _wallet_keypairs(),
        99,
    )

    expected_create_tx = {
        "inputs": [
            {
                "previous_out": {"t_hash": "000000", "n": 0},
                "script_signature": {
                    "Pay2PkH": {
                        "signable_data": (
                            "a952cbc26b023f7fa8e6d9c937af1a6ef2b128eaceda4335513966046c73046f"
                        ),
                        "signature": (
                            "89f1eb338e0d994c8389f3739bd181f5675b8f40cb4e6d3d8a9097a7a6963619"
                            "f4a6d864be00e5400b26b6136877ce65c076073f8ac5b2e979e6fdc39d5fbd0b"
                        ),
                        "public_key": ADDR1_PUBLIC_KEY_HEX,
                        "address_version": None,
                    }
                },
            },
        ],
        "outputs": [
            {
                "value": {"Token": 5},
                "locktime": 99,
                "script_public_key": PAYMENT_ADDRESS,
            },
            {
                "value": {"Token": 5},
                "locktime": 0,
                "script_public_key": EXCESS_ADDRESS,
            },
        ],
        "version": 2,
        "druid_info": None,
    }

    assert result["create_tx"] == expected_create_tx
    assert result["excess_address_used"] is True
    assert result["used_addresses"] == [ADDR1_ADDRESS]
