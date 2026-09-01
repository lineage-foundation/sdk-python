"""Tests for blockchain client."""

import pytest
import requests
import logging
from lineage.blockchain import BlockchainClient, get_headers, get_random_string
from lineage.interfaces import IResult, IErrorInternal
from typing import Dict, Any

# Set up logging
logger = logging.getLogger(__name__)

@pytest.fixture
def blockchain_client(mock_api) -> BlockchainClient:
    """Fixture providing an initialized blockchain client."""
    return BlockchainClient(
        storage_host='https://storage.aiblock.dev',
        mempool_host='https://mempool.aiblock.dev'
    )

@pytest.fixture
def storage_only_client(mock_api) -> BlockchainClient:
    """Fixture providing a blockchain client with only storage host."""
    return BlockchainClient(storage_host='https://storage.aiblock.dev')

def test_get_headers():
    """Test header generation."""
    headers = get_headers()
    assert headers == {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

def test_get_headers_with_api_key():
    """Test header generation includes x-api-key when an API key is set."""
    headers = get_headers('secret-key')
    assert headers['x-api-key'] == 'secret-key'
    assert headers['Content-Type'] == 'application/json'
    assert headers['Accept'] == 'application/json'

def test_get_random_string():
    """Test random string generation."""
    str1 = get_random_string(32)
    str2 = get_random_string(32)
    assert len(str1) == 32
    assert len(str2) == 32
    assert str1 != str2  # Should be random
    assert all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for c in str1)

def test_get_latest_block(blockchain_client: BlockchainClient, mock_api):
    """Test getting the latest block."""
    result = blockchain_client.get_latest_block()
    assert result.is_ok
    assert result.get_ok()['block_num'] == 1000
    assert result.get_ok()['block_hash'] == 'test_hash'
    assert mock_api.last_request.url == 'https://storage.aiblock.dev/v1/blocks/latest'

def test_get_latest_block_not_found_when_empty(blockchain_client: BlockchainClient, mock_api):
    """A chain with no blocks yet returns 404, which must map to a not-found result, not a crash."""
    mock_api.get(
        'https://storage.aiblock.dev/v1/blocks/latest',
        status_code=404,
        json={'type': 'about:blank', 'title': 'Not Found', 'status': 404, 'detail': 'No blocks found'}
    )
    result = blockchain_client.get_latest_block()
    assert result.is_err
    assert result.error == IErrorInternal.NotFound
    assert 'No blocks found' in result.error_message

def test_get_latest_block_network_error(blockchain_client: BlockchainClient, mock_api):
    """Test network error handling when getting latest block."""
    mock_api.get(
        "https://storage.aiblock.dev/v1/blocks/latest",
        exc=requests.exceptions.ConnectionError
    )
    result = blockchain_client.get_latest_block()
    assert result.is_err
    assert result.error == IErrorInternal.NetworkError
    assert 'Connection error' in result.error_message

def test_get_latest_block_invalid_json(blockchain_client: BlockchainClient, mock_api):
    """Test invalid JSON handling when getting latest block."""
    mock_api.get(
        "https://storage.aiblock.dev/v1/blocks/latest",
        text="invalid json"
    )
    result = blockchain_client.get_latest_block()
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "Invalid JSON" in result.error_message

def test_get_block_by_num(blockchain_client: BlockchainClient, mock_api):
    """Test getting a block by number."""
    result = blockchain_client.get_block_by_num(1000)
    assert result.is_ok
    assert result.get_ok()['block_num'] == 1000
    assert result.get_ok()['block_hash'] == 'test_hash'
    assert mock_api.last_request.path == '/v1/blocks'
    assert mock_api.last_request.qs == {'num': ['1000']}

def test_get_block_by_num_invalid_input(blockchain_client: BlockchainClient):
    """Test input validation for get_block_by_num."""
    # Test negative number
    result = blockchain_client.get_block_by_num(-1)
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "Block number must be a non-negative integer" in result.error_message

    # Test non-integer (this would be caught by type checker, but testing runtime)
    result = blockchain_client.get_block_by_num("invalid")
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided

def test_get_block_by_num_network_error(blockchain_client: BlockchainClient, mock_api):
    """Test network error handling when getting block by number."""
    mock_api.get(
        "https://storage.aiblock.dev/v1/blocks",
        exc=requests.exceptions.ConnectionError
    )
    result = blockchain_client.get_block_by_num(1000)
    assert result.is_err
    assert result.error == IErrorInternal.NetworkError
    assert 'Connection error' in result.error_message

def test_get_block_by_num_not_found(blockchain_client: BlockchainClient, mock_api):
    """Test handling of non-existent block number."""
    mock_api.get(
        "https://storage.aiblock.dev/v1/blocks",
        status_code=404,
        json={'type': 'about:blank', 'title': 'Not Found', 'status': 404, 'detail': 'Block not found'}
    )
    result = blockchain_client.get_block_by_num(1000)
    assert result.is_err
    assert result.error == IErrorInternal.NotFound
    assert "Block not found" in result.error_message

def test_get_blockchain_entry(blockchain_client: BlockchainClient, mock_api):
    """Test getting a blockchain entry."""
    result = blockchain_client.get_blockchain_entry('test_hash')
    assert result.is_ok
    assert result.get_ok()['block_num'] == 1000
    assert result.get_ok()['block_hash'] == 'test_hash'
    assert mock_api.last_request.json() == {'keys': ['test_hash']}

def test_get_blockchain_entry_network_error(blockchain_client: BlockchainClient, mock_api):
    """Test network error handling when getting blockchain entry."""
    mock_api.post(
        "https://storage.aiblock.dev/v1/blockchain-entries/query",
        exc=requests.exceptions.ConnectionError
    )
    result = blockchain_client.get_blockchain_entry('test_hash')
    assert result.is_err
    assert 'Connection error' in result.error_message

def test_get_blockchain_entry_method_not_allowed(blockchain_client: BlockchainClient, mock_api):
    """Test handling of method not allowed error."""
    mock_api.post(
        "https://storage.aiblock.dev/v1/blockchain-entries/query",
        status_code=405,
        json={'type': 'about:blank', 'title': 'Method Not Allowed', 'status': 405, 'detail': 'Method not allowed'}
    )
    result = blockchain_client.get_blockchain_entry('test_hash')
    assert result.is_err
    assert result.error == IErrorInternal.BadRequest
    assert "Method not allowed" in result.error_message

def test_get_transaction_by_hash(blockchain_client: BlockchainClient, mock_api):
    """Test getting a transaction by hash using the blockchain-entries endpoint."""
    result = blockchain_client.get_transaction_by_hash('test_tx_hash')
    assert result.is_ok
    assert result.get_ok()['block_hash'] == 'test_hash'
    assert mock_api.last_request.json() == {'keys': ['test_tx_hash']}

def test_get_transaction_by_hash_invalid_input(blockchain_client: BlockchainClient):
    """Test input validation for get_transaction_by_hash."""
    # Test empty string
    result = blockchain_client.get_transaction_by_hash('')
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "Transaction hash must be a non-empty string" in result.error_message

    # Test None
    result = blockchain_client.get_transaction_by_hash(None)
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided

def test_fetch_transactions(blockchain_client: BlockchainClient, mock_api):
    """Test fetching multiple transactions using the blockchain-entries endpoint."""
    result = blockchain_client.fetch_transactions(['hash1', 'hash2', 'hash3'])
    assert result.is_ok
    assert result.get_ok()['block_hash'] == 'test_hash'
    assert mock_api.last_request.json() == {'keys': ['hash1', 'hash2', 'hash3']}

def test_fetch_transactions_invalid_input(blockchain_client: BlockchainClient):
    """Test input validation for fetch_transactions."""
    # Test empty list
    result = blockchain_client.fetch_transactions([])
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "Transaction hashes list cannot be empty" in result.error_message

    # Test non-list
    result = blockchain_client.fetch_transactions("not_a_list")
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "Transaction hashes must be a list" in result.error_message

    # Test list with invalid hash
    result = blockchain_client.fetch_transactions(['valid_hash', '', 'another_hash'])
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "All transaction hashes must be non-empty strings" in result.error_message

def test_blockchain_client_without_initialization():
    """Test error handling when client is not initialized."""
    with pytest.raises(ValueError, match="storage_host cannot be None"):
        BlockchainClient(None)

def test_get_total_supply(blockchain_client: BlockchainClient, mock_api):
    """Test getting total supply from mempool host."""
    result = blockchain_client.get_total_supply()
    assert result.is_ok
    assert result.get_ok()['total'] == 1000000
    assert result.get_ok()['issued'] == 500000
    assert mock_api.last_request.url == 'https://mempool.aiblock.dev/v1/supply'

def test_get_total_supply_error(blockchain_client: BlockchainClient, mock_api):
    """Test error handling when getting total supply."""
    mock_api.get(
        "https://mempool.aiblock.dev/v1/supply",
        exc=requests.exceptions.ConnectionError
    )
    result = blockchain_client.get_total_supply()
    assert result.is_err
    assert result.error == IErrorInternal.NetworkError
    assert 'Connection error' in result.error_message

def test_get_total_supply_no_mempool(storage_only_client: BlockchainClient, mock_api):
    """Test handling when mempool URL is not set."""
    result = storage_only_client.get_total_supply()
    assert result.is_err
    assert result.error == IErrorInternal.NetworkNotInitialized
    assert "Mempool host is required" in result.error_message

def test_get_issued_supply(blockchain_client: BlockchainClient, mock_api):
    """Test getting issued supply from mempool host."""
    result = blockchain_client.get_issued_supply()
    assert result.is_ok
    assert result.get_ok()['issued'] == 500000
    assert result.get_ok()['total'] == 1000000

def test_get_issued_supply_error(blockchain_client: BlockchainClient, mock_api):
    """Test error handling when getting issued supply."""
    mock_api.get(
        "https://mempool.aiblock.dev/v1/supply",
        exc=requests.exceptions.ConnectionError
    )
    result = blockchain_client.get_issued_supply()
    assert result.is_err
    assert result.error == IErrorInternal.NetworkError
    assert 'Connection error' in result.error_message

def test_get_issued_supply_pending(blockchain_client: BlockchainClient, mock_api):
    """Test handling of pending issued supply request."""
    mock_api.get(
        "https://mempool.aiblock.dev/v1/supply",
        status_code=202,
        text="Request is being processed"
    )
    result = blockchain_client.get_issued_supply()
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "Request is being processed" in result.error_message

def test_get_issued_supply_no_mempool(storage_only_client: BlockchainClient, mock_api):
    """Test handling when mempool URL is not set."""
    result = storage_only_client.get_issued_supply()
    assert result.is_err
    assert result.error == IErrorInternal.NetworkNotInitialized
    assert "Mempool host is required" in result.error_message

def test_get_issued_supply_unknown_error(blockchain_client: BlockchainClient, mock_api):
    """Test handling of unknown error status code."""
    mock_api.get(
        "https://mempool.aiblock.dev/v1/supply",
        status_code=418,
        text="I'm a teapot"
    )
    result = blockchain_client.get_issued_supply()
    assert result.is_err
    assert result.error == IErrorInternal.UnknownError
    assert "I'm a teapot" in result.error_message

def test_problem_json_error_uses_detail_over_title(blockchain_client: BlockchainClient, mock_api):
    """A problem+json body's `detail` should take priority over `title` for the error message."""
    mock_api.get(
        "https://storage.aiblock.dev/v1/blocks/latest",
        status_code=400,
        json={'type': 'about:blank', 'title': 'Bad Request', 'status': 400, 'detail': 'num must be positive'}
    )
    result = blockchain_client.get_latest_block()
    assert result.is_err
    assert result.error == IErrorInternal.BadRequest
    assert result.error_message == 'num must be positive'

def test_problem_json_error_falls_back_to_title(blockchain_client: BlockchainClient, mock_api):
    """A problem+json body without `detail` should fall back to `title`."""
    mock_api.get(
        "https://storage.aiblock.dev/v1/blocks/latest",
        status_code=401,
        json={'type': 'about:blank', 'title': 'Unauthorized', 'status': 401}
    )
    result = blockchain_client.get_latest_block()
    assert result.is_err
    assert result.error == IErrorInternal.Unauthorized
    assert result.error_message == 'Unauthorized'

def test_server_error_maps_to_internal_server_error(blockchain_client: BlockchainClient, mock_api):
    """A 500 with a problem+json body maps to InternalServerError with the detail message."""
    mock_api.get(
        "https://storage.aiblock.dev/v1/blocks/latest",
        status_code=500,
        json={'type': 'about:blank', 'title': 'Internal Server Error', 'status': 500, 'detail': 'database unavailable'}
    )
    result = blockchain_client.get_latest_block()
    assert result.is_err
    assert result.error == IErrorInternal.InternalServerError
    assert 'database unavailable' in result.error_message

def test_api_key_sent_as_header(mock_api):
    """When configured, the API key should be sent as the x-api-key header."""
    client = BlockchainClient(
        storage_host='https://storage.aiblock.dev',
        mempool_host='https://mempool.aiblock.dev',
        api_key='my-secret-key'
    )
    result = client.get_latest_block()
    assert result.is_ok
    assert mock_api.last_request.headers['x-api-key'] == 'my-secret-key'

def test_no_api_key_header_when_not_configured(blockchain_client: BlockchainClient, mock_api):
    """When no API key is configured, no x-api-key header should be sent."""
    result = blockchain_client.get_latest_block()
    assert result.is_ok
    assert 'x-api-key' not in mock_api.last_request.headers
