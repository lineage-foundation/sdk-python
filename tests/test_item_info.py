"""Tests for item genesis-metadata resolution (get_item_info)."""

import pytest
import requests

from lineage.wallet import Wallet
from lineage.interfaces import IErrorInternal

STORAGE_HOST = "https://storage.lineage.to"
GH = "genesis0abc"
INFO = {
    "genesis_hash": GH,
    "metadata": "ticket #1",
    "total_amount": 1000,
    "created": {"block_num": 42, "tx_hash": GH},
    "creator_address": "addr_creator",
}


def test_get_item_info_returns_genesis_facts_on_200(wallet: Wallet, mock_api):
    """A 200 returns the full genesis-facts object, unrenamed."""
    item_mock = mock_api.get(f"{STORAGE_HOST}/v1/items/{GH}", json=INFO)
    result = wallet.get_item_info(GH)
    assert result.is_ok
    assert result.get_ok() == INFO
    assert item_mock.call_count == 1
    assert mock_api.last_request.url == f"{STORAGE_HOST}/v1/items/{GH}"


def test_get_item_info_caches_success(wallet: Wallet, mock_api):
    """A second call for the same hash issues no further HTTP request."""
    item_mock = mock_api.get(f"{STORAGE_HOST}/v1/items/{GH}", json=INFO)
    first = wallet.get_item_info(GH)
    second = wallet.get_item_info(GH)
    assert first.is_ok and second.is_ok
    assert second.get_ok() == INFO
    assert item_mock.call_count == 1  # cached, not re-fetched


def test_get_item_info_404_is_error_and_not_cached(wallet: Wallet, mock_api):
    """404 -> NotFound error; the failure is NOT cached, so a later success re-fetches."""
    not_found = mock_api.get(
        f"{STORAGE_HOST}/v1/items/{GH}",
        status_code=404,
        json={"type": "about:blank", "title": "Not Found", "status": 404, "detail": "unknown item"},
    )
    miss = wallet.get_item_info(GH)
    assert miss.is_err
    assert miss.error == IErrorInternal.NotFound
    assert not_found.call_count == 1

    ok_mock = mock_api.get(f"{STORAGE_HOST}/v1/items/{GH}", json=INFO)
    hit = wallet.get_item_info(GH)
    assert hit.is_ok
    assert hit.get_ok() == INFO
    assert ok_mock.call_count == 1  # failure was retried, not served from cache


def test_get_item_info_without_storage_host_errors(mock_api):
    """With no storage host configured, get_item_info reports StorageNotInitialized."""
    w = Wallet()
    seed = w.generate_seed_phrase()
    result = w.from_seed(seed, {"mempoolHost": "https://mempool.lineage.to"})
    assert result.is_ok
    res = w.get_item_info(GH)
    assert res.is_err
    assert res.error == IErrorInternal.StorageNotInitialized


def test_get_item_info_rejects_empty_hash(wallet: Wallet):
    """An empty genesis_hash is rejected before any network call."""
    res = wallet.get_item_info("")
    assert res.is_err
    assert res.error == IErrorInternal.InvalidParametersProvided


def _balance_with(genesis_hash, metadata=None, second_address=False):
    """Build a balances/query response holding item UTXO(s)."""
    address_list = {
        "addr1": [
            {
                "out_point": {"t_hash": "t0", "n": 0},
                "value": {"Item": {"amount": 5, "genesis_hash": genesis_hash, "metadata": metadata}},
            },
        ],
    }
    if second_address:
        address_list["addr2"] = [
            {
                "out_point": {"t_hash": "t1", "n": 0},
                "value": {"Item": {"amount": 3, "genesis_hash": genesis_hash, "metadata": None}},
            },
        ]
    return {"total": {"tokens": 0, "items": {genesis_hash: 5}}, "address_list": address_list}


def _item(balance, address, index=0):
    return balance["address_list"][address][index]["value"]["Item"]


def test_fetch_balance_enriches_item_metadata_by_default(wallet: Wallet, mock_api):
    """A transferred item (metadata=None) is enriched from the resolver."""
    mock_api.post(
        "https://mempool.lineage.to/v1/balances/query",
        json={"balance": _balance_with(GH, metadata=None)},
    )
    item_mock = mock_api.get(f"{STORAGE_HOST}/v1/items/{GH}", json=INFO)

    result = wallet.fetch_balance(["addr1"])
    assert result.is_ok
    assert item_mock.call_count == 1
    balance = result.get_ok()
    assert _item(balance, "addr1")["metadata"] == "ticket #1"


def test_fetch_balance_dedups_distinct_hashes(wallet: Wallet, mock_api):
    """Two addresses sharing one genesis_hash trigger exactly one resolver call."""
    mock_api.post(
        "https://mempool.lineage.to/v1/balances/query",
        json={"balance": _balance_with(GH, metadata=None, second_address=True)},
    )
    item_mock = mock_api.get(f"{STORAGE_HOST}/v1/items/{GH}", json=INFO)

    result = wallet.fetch_balance(["addr1", "addr2"])
    assert result.is_ok
    assert item_mock.call_count == 1  # deduped, not one-per-utxo
    balance = result.get_ok()
    assert _item(balance, "addr1")["metadata"] == "ticket #1"
    assert _item(balance, "addr2")["metadata"] == "ticket #1"


def test_repeat_listing_uses_cache_no_further_calls(wallet: Wallet, mock_api):
    """A second fetch_balance for the same hash issues no further resolver call."""
    mock_api.post(
        "https://mempool.lineage.to/v1/balances/query",
        json={"balance": _balance_with(GH, metadata=None)},
    )
    item_mock = mock_api.get(f"{STORAGE_HOST}/v1/items/{GH}", json=INFO)

    first = wallet.fetch_balance(["addr1"])
    second = wallet.fetch_balance(["addr1"])
    assert first.is_ok and second.is_ok
    assert item_mock.call_count == 1  # cached across listings
    assert _item(second.get_ok(), "addr1")["metadata"] == "ticket #1"


def test_fetch_balance_graceful_degrade_on_resolver_error(wallet: Wallet, mock_api):
    """A resolver error leaves metadata None; the balance call still succeeds."""
    mock_api.post(
        "https://mempool.lineage.to/v1/balances/query",
        json={"balance": _balance_with(GH, metadata=None)},
    )
    mock_api.get(
        f"{STORAGE_HOST}/v1/items/{GH}",
        status_code=500,
        json={"type": "about:blank", "title": "Internal Server Error", "status": 500, "detail": "boom"},
    )

    result = wallet.fetch_balance(["addr1"])
    assert result.is_ok
    assert _item(result.get_ok(), "addr1")["metadata"] is None


def test_resolve_miss_does_not_clobber_inline_metadata(wallet: Wallet, mock_api):
    """An item carrying inline metadata keeps it when the resolver fails (miss != overwrite)."""
    mock_api.post(
        "https://mempool.lineage.to/v1/balances/query",
        json={"balance": _balance_with(GH, metadata="inline-metadata")},
    )
    mock_api.get(
        f"{STORAGE_HOST}/v1/items/{GH}",
        status_code=500,
        json={"type": "about:blank", "title": "Internal Server Error", "status": 500, "detail": "boom"},
    )

    result = wallet.fetch_balance(["addr1"])
    assert result.is_ok
    assert _item(result.get_ok(), "addr1")["metadata"] == "inline-metadata"


def test_fetch_balance_enrich_false_issues_no_resolver_calls(wallet: Wallet, mock_api):
    """enrich=False resolves nothing and leaves items untouched (opt-out gate)."""
    mock_api.post(
        "https://mempool.lineage.to/v1/balances/query",
        json={"balance": _balance_with(GH, metadata=None)},
    )
    item_mock = mock_api.get(f"{STORAGE_HOST}/v1/items/{GH}", json=INFO)

    result = wallet.fetch_balance(["addr1"], enrich=False)
    assert result.is_ok
    assert item_mock.call_count == 0  # the interceptor must NOT be consumed
    assert _item(result.get_ok(), "addr1")["metadata"] is None
