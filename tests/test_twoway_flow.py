"""Gate tests for the rewritten 2-way payment TRANSPORT + flow methods.

These exercise `lineage/valence.py` (the plaintext `/messages` mailbox
client) and the four `Wallet` flow methods (`make_2way_payment`,
`fetch_pending_2way_payment`, `accept_2way_payment`, `reject_2way_payment`)
against a mocked HTTP layer (`requests_mock`, matching this repo's existing
test style - see `tests/test_wallet.py`).

The valence auth-header/body shape is checked against
`tests/fixtures/twoway.json`'s `valenceAuth`/`pending2WTxDetailsOffer`
vectors - the same fixture sdk-go/sdk-php are gated against - so a pass there
proves interop, not just internal self-consistency. The flow-method tests use
ad-hoc (non-vector) keypairs/balances since they exercise plumbing (mailbox
routing, submission shape, partial-error handling), not signature bytes.
"""

import json
from pathlib import Path

import pytest

from lineage.interfaces import IKeypair
from lineage.key_handler import generate_keypair
from lineage.transaction import create_2w_tx_half
from lineage.valence import ValenceClient
from lineage.wallet import Wallet

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "twoway.json"


def _load_vector():
    with open(FIXTURE_PATH, "r") as f:
        return json.load(f)


def _seed(secret_key_hex: str) -> bytes:
    return bytes.fromhex(secret_key_hex)[:32]


def _vector_keypair(entry: dict) -> IKeypair:
    return IKeypair(
        address=entry["address"],
        secret_key=_seed(entry["secret_key"]),
        public_key=bytes.fromhex(entry["public_key"]),
        version=1,
    )


def _fresh_keypair() -> IKeypair:
    result = generate_keypair()
    assert result.is_ok
    return result.get_ok()


def _make_wallet() -> Wallet:
    w = Wallet(debug=True)
    w.network_config = {
        "mempoolHost": "https://mempool.lineage.to",
        "valenceHost": "https://valence.lineage.to",
    }
    w.routes_initialized = True
    w.passphrase_key = b"unit-test-passphrase-key-32bytes"
    return w


# --------------------------------------------------------------------------
# (a) valence POST auth headers + plaintext body match the golden vector
# --------------------------------------------------------------------------

def test_valence_post_auth_headers_and_body_match_vector(requests_mock):
    vector = _load_vector()
    kp = _vector_keypair(vector["fixedKeypairs"]["ours"][0])
    expected_auth = vector["valenceAuth"]
    offer = vector["pending2WTxDetailsOffer"]

    assert kp.address == expected_auth["address"]

    requests_mock.post("https://valence.lineage.to/messages", json={})

    vc = ValenceClient("https://valence.lineage.to")
    result = vc.post(expected_auth["address"], kp, offer)
    assert result.is_ok

    req = requests_mock.last_request
    assert req.headers["address"] == expected_auth["address"]
    assert req.headers["public_key"] == expected_auth["public_key"]
    assert req.headers["signature"] == expected_auth["signature"]

    body = req.json()
    assert body == {"id": offer["druid"], "data": offer}


def test_valence_get_and_delete_use_same_auth_scheme(requests_mock):
    kp = _fresh_keypair()
    requests_mock.get("https://valence.lineage.to/messages", json={})
    requests_mock.delete("https://valence.lineage.to/messages/DRUID0xabc", json={})

    vc = ValenceClient("https://valence.lineage.to")

    get_result = vc.get(kp.address, kp)
    assert get_result.is_ok
    get_req = requests_mock.request_history[-1]
    assert get_req.method == "GET"
    assert get_req.headers["address"] == kp.address
    assert get_req.headers["public_key"] == kp.public_key.hex()

    delete_result = vc.delete("DRUID0xabc", kp.address, kp)
    assert delete_result.is_ok
    delete_req = requests_mock.request_history[-1]
    assert delete_req.method == "DELETE"
    assert delete_req.url == "https://valence.lineage.to/messages/DRUID0xabc"
    assert delete_req.headers["address"] == kp.address


# --------------------------------------------------------------------------
# (b) ACCEPTOR discovery: no stored halves, offer in own mailbox -> pending
# --------------------------------------------------------------------------

def test_fetch_pending_discovers_incoming_offer(requests_mock):
    w = _make_wallet()
    kp = _fresh_keypair()
    offer = {
        "druid": "DRUID0xincoming00000000000000000000000",
        "senderExpectation": {"from": "counterparty-from", "to": kp.address, "asset": {"Token": 10}},
        "receiverExpectation": {"from": "", "to": "counterparty-addr", "asset": {"Token": 20}},
        "status": "pending",
        "mempoolHost": "https://mempool.lineage.to",
    }
    requests_mock.get("https://valence.lineage.to/messages", json={offer["druid"]: offer})

    result = w.fetch_pending_2way_payment([], [kp])
    assert result.is_ok

    content = result.get_ok()
    assert content["pending"] == {offer["druid"]: offer}
    assert content["settled"] == []
    assert not content.get("errors")


# --------------------------------------------------------------------------
# (c) INITIATOR settle: accepted stored half -> submitted (version 2, fees
#     null, genesis_hash null), deleted, and reported settled.
# --------------------------------------------------------------------------

def test_fetch_pending_settles_accepted_stored_half(requests_mock):
    w = _make_wallet()
    kp = _fresh_keypair()
    counterparty_addr = "counterparty-addr-settle"

    balance = {
        "total": {"tokens": 100, "items": {}},
        "address_list": {
            kp.address: [{"out_point": {"t_hash": "tx0", "n": 0}, "value": {"Token": 100}}],
        },
    }
    druid = "DRUID0xsettleme000000000000000000000000"
    sender_expectation = {"from": "", "to": kp.address, "asset": {"Token": 10}}
    receiver_expectation = {"from": "", "to": counterparty_addr, "asset": {"Token": 50}}

    create_tx = create_2w_tx_half(
        druid, sender_expectation, receiver_expectation, balance,
        {kp.address: kp}, kp.address, 0,
    )["create_tx"]

    encrypted_half = w._encrypt_2w_half(create_tx)
    stored = [{
        "druid": druid,
        "encryptedHalf": encrypted_half,
        "senderExpectation": sender_expectation,
        "receiverExpectation": receiver_expectation,
    }]

    filled_sender_expectation = dict(sender_expectation)
    filled_sender_expectation["from"] = "counterparty-inputs-hash"

    requests_mock.get("https://valence.lineage.to/messages", json={
        druid: {
            "druid": druid,
            "senderExpectation": filled_sender_expectation,
            "receiverExpectation": receiver_expectation,
            "status": "accepted",
            "mempoolHost": "https://mempool.lineage.to",
        }
    })
    requests_mock.post(
        "https://mempool.lineage.to/v1/transactions",
        status_code=201,
        json={"transactions": {"txhash": {"address": counterparty_addr, "asset": {"Token": 50}}}},
    )
    requests_mock.delete(f"https://valence.lineage.to/messages/{druid}", json={})

    result = w.fetch_pending_2way_payment(stored, [kp])
    assert result.is_ok

    content = result.get_ok()
    assert content["settled"] == [druid]
    assert content["pending"] == {}

    submit_req = next(
        r for r in requests_mock.request_history
        if r.method == "POST" and r.url == "https://mempool.lineage.to/v1/transactions"
    )
    submitted_tx = submit_req.json()["transactions"][0]
    assert submitted_tx["version"] == 2
    assert submitted_tx["fees"] is None
    assert submitted_tx["druid_info"]["genesis_hash"] is None
    assert submitted_tx["druid_info"]["expectations"][0] == filled_sender_expectation

    delete_req = next(r for r in requests_mock.request_history if r.method == "DELETE")
    assert delete_req.url == f"https://valence.lineage.to/messages/{druid}"


# --------------------------------------------------------------------------
# (d) accept_2way_payment submits to details.mempoolHost (not the wallet's
#     own configured mempool host) and posts the accepted status to valence.
# --------------------------------------------------------------------------

def test_accept_2way_payment_submits_to_details_mempool_host(requests_mock):
    w = _make_wallet()
    kp = _fresh_keypair()
    counterparty_addr = "counterparty-addr-accept"

    details = {
        "druid": "DRUID0xaccept0000000000000000000000000",
        "senderExpectation": {"from": "", "to": counterparty_addr, "asset": {"Token": 30}},
        "receiverExpectation": {"from": "", "to": kp.address, "asset": {"Token": 15}},
        "status": "pending",
        "mempoolHost": "https://custom-mempool.example.com",
    }

    requests_mock.post(
        "https://mempool.lineage.to/v1/balances/query",
        json={"balance": {
            "total": {"tokens": 100, "items": {}},
            "address_list": {
                kp.address: [{"out_point": {"t_hash": "tx1", "n": 0}, "value": {"Token": 100}}],
            },
        }},
    )
    requests_mock.post(
        "https://custom-mempool.example.com/v1/transactions",
        status_code=201,
        json={"transactions": {"txhash": {"address": counterparty_addr, "asset": {"Token": 30}}}},
    )
    requests_mock.post("https://valence.lineage.to/messages", json={})

    result = w.accept_2way_payment(details, [kp])
    assert result.is_ok

    submit_reqs = [
        r for r in requests_mock.request_history
        if r.method == "POST" and r.url == "https://custom-mempool.example.com/v1/transactions"
    ]
    assert len(submit_reqs) == 1
    assert not any(
        r.url == "https://mempool.lineage.to/v1/transactions" for r in requests_mock.request_history
    )

    valence_req = next(
        r for r in requests_mock.request_history
        if r.method == "POST" and r.url == "https://valence.lineage.to/messages"
    )
    posted = valence_req.json()
    assert posted["id"] == details["druid"]
    assert posted["data"]["status"] == "accepted"
    assert posted["data"]["senderExpectation"]["from"] != ""


# --------------------------------------------------------------------------
# (e) reject posts status "rejected" and never submits a transaction.
# --------------------------------------------------------------------------

def test_reject_2way_payment_posts_rejected_without_submit(requests_mock):
    w = _make_wallet()
    kp = _fresh_keypair()

    details = {
        "druid": "DRUID0xreject00000000000000000000000000",
        "senderExpectation": {"from": "", "to": "counterparty-addr-reject", "asset": {"Token": 5}},
        "receiverExpectation": {"from": "", "to": kp.address, "asset": {"Token": 5}},
        "status": "pending",
        "mempoolHost": "https://custom-mempool.example.com",
    }
    requests_mock.post("https://valence.lineage.to/messages", json={})

    result = w.reject_2way_payment(details, [kp])
    assert result.is_ok
    assert result.get_ok()["status"] == "rejected"

    assert not any(
        r.url.startswith("https://custom-mempool.example.com") for r in requests_mock.request_history
    )

    valence_req = requests_mock.last_request
    assert valence_req.url == "https://valence.lineage.to/messages"
    body = valence_req.json()
    assert body["data"]["status"] == "rejected"


# --------------------------------------------------------------------------
# (f) A failed mailbox mid-loop doesn't discard progress made on the others.
# --------------------------------------------------------------------------

def test_fetch_pending_partial_failure_preserves_other_results(requests_mock):
    w = _make_wallet()
    kp_good = _fresh_keypair()
    kp_bad = _fresh_keypair()

    good_offer = {
        "druid": "DRUID0xgood000000000000000000000000000",
        "senderExpectation": {"from": "", "to": kp_good.address, "asset": {"Token": 1}},
        "receiverExpectation": {"from": "", "to": "counterparty-addr-good", "asset": {"Token": 1}},
        "status": "pending",
        "mempoolHost": "https://mempool.lineage.to",
    }

    requests_mock.get(
        "https://valence.lineage.to/messages",
        request_headers={"address": kp_good.address},
        json={good_offer["druid"]: good_offer},
    )
    requests_mock.get(
        "https://valence.lineage.to/messages",
        request_headers={"address": kp_bad.address},
        status_code=500,
        json={"type": "about:blank", "title": "Internal Server Error", "status": 500, "detail": "mailbox down"},
    )

    result = w.fetch_pending_2way_payment([], [kp_good, kp_bad])
    assert result.is_ok

    content = result.get_ok()
    assert content["pending"] == {good_offer["druid"]: good_offer}
    assert content["settled"] == []
    assert content.get("errors")
