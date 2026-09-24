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
