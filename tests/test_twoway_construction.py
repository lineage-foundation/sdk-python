"""Gate test: prove the 2-way (DRUID) construction path matches the shared
golden vector byte-for-byte.

The vector at `tests/fixtures/twoway.json` is copied verbatim from sdk-go's
`internal/testvectors/twoway.json` - the same fixture sdk-go and sdk-php are
gated against - so a pass here proves interop with those siblings, not just
internal self-consistency. If any assertion here fails, the implementation is
wrong - do not adjust the expected values, fix `lineage/transaction.py` or
`lineage/key_handler.py` (or stop and report a blocker).

A 2-way (DDE) half is an ORDINARY P2PKH transaction: `druid_info` is
unsigned, and each input is signed with exactly the same per-input signable
hash as a plain 1-way payment (see `test_transaction_signing.py`). This test
only checks the construction shape (`druid_info`, per-input
`signable_data`/`signature`, `outputs`) and the DRUID/tx-ins-address helpers;
it does not cover submission (genesis_hash/version are added later, at
submit time).
"""

import json
import re
from pathlib import Path

from lineage.interfaces import IKeypair
from lineage.key_handler import generate_druid
from lineage.transaction import construct_tx_ins_address, create_2w_tx_half

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "twoway.json"


def _load_vector():
    with open(FIXTURE_PATH, "r") as f:
        return json.load(f)


def _seed(secret_key_hex: str) -> bytes:
    return bytes.fromhex(secret_key_hex)[:32]


def _keypair(entry: dict) -> IKeypair:
    return IKeypair(
        address=entry["address"],
        secret_key=_seed(entry["secret_key"]),
        public_key=bytes.fromhex(entry["public_key"]),
        version=1,
    )


def _keypairs_map(vector: dict) -> dict:
    return {entry["address"]: _keypair(entry) for entry in vector["fixedKeypairs"]["ours"]}


def _canon(value) -> str:
    """Compact-JSON canonicalization for byte-for-byte comparison."""
    return json.dumps(value, separators=(",", ":"), sort_keys=False)


def test_generate_druid_matches_shape():
    druid = generate_druid()
    assert re.match(r"^DRUID0x[0-9a-f]{32}$", druid), druid


def test_construct_tx_ins_address_matches_vector():
    vector = _load_vector()
    case = vector["constructTxInsAddress"]
    result = construct_tx_ins_address(case["input"])
    assert result == case["address"]


def test_create_2w_tx_half_matches_vector():
    vector = _load_vector()
    case = vector["create2WTxHalf"]
    tx_input = case["input"]
    expected_output = case["output"]

    keypairs = _keypairs_map(vector)

    result = create_2w_tx_half(
        vector["druid"],
        tx_input["senderExpectation"],
        tx_input["receiverExpectation"],
        tx_input["fetchBalanceResponse"],
        keypairs,
        tx_input["excessAddress"],
        tx_input["locktime"],
    )

    create_tx = result["create_tx"]

    # druid_info: unsigned, {druid, participants, expectations: [thisExpectation]}
    assert _canon(create_tx["druid_info"]) == _canon(expected_output["druid_info"])

    # outputs: [pay counterExpectation.asset to counterExpectation.to, +excess]
    assert _canon(create_tx["outputs"]) == _canon(expected_output["outputs"])

    # inputs: per-input signable_data/signature/public_key/address_version
    assert _canon(create_tx["inputs"]) == _canon(expected_output["inputs"])

    assert result["used_addresses"] == expected_output["usedAddresses"]
    assert result["excess_address_used"] == expected_output["excessAddressUsed"]
