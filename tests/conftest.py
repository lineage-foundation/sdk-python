import pytest
import sys
import logging
from pathlib import Path
from lineage.wallet import Wallet
from typing import Dict, Any
import requests_mock
import json

# Set up logging
logger = logging.getLogger(__name__)

# Add the package root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lineage import wallet

@pytest.fixture
def valid_config():
    """Fixture providing a valid wallet configuration."""
    return {
        'passphrase': 'test_passphrase',
        'mempoolHost': 'https://mempool.aiblock.dev',
        'storageHost': 'https://storage.aiblock.dev',
        'valenceHost': 'https://valence.aiblock.dev'
    }

@pytest.fixture
def wallet_instance():
    """Fixture providing a fresh wallet instance."""
    return Wallet()

@pytest.fixture
def test_config() -> Dict[str, Any]:
    """Fixture providing test configuration."""
    return {
        'mempoolHost': 'https://mempool.aiblock.dev',
        'storageHost': 'https://storage.aiblock.dev',
        'valenceHost': 'https://valence.aiblock.dev'
    }

@pytest.fixture
def mock_api(requests_mock: requests_mock.Mocker):
    """Fixture providing mocked API responses."""
    debug_response = {
        'id': '1234-5678-9012-3456',
        'status': 'Success',
        'reason': 'Debug data successfully retrieved',
        'content': {
            'debugDataResponse': {
                'node_type': 'Storage',
                'node_api': [
                    'latest_block',
                    'block',
                    'blockchain_entry'
                ],
                'routes_pow': {
                    'fetch_balance': 0,
                    'create_item_asset': 0,
                    'create_transactions': 0,
                    'total_supply': 0,
                    'issued_supply': 0,
                    'transaction_status': 0,
                    'debug_data': 0,
                    'latest_block': 0,
                    'block': 0,
                    'blockchain_entry': 0
                }
            }
        }
    }

    # Mock both GET and POST for debug_data
    requests_mock.get(
        'https://mempool.aiblock.dev/debug_data',
        json=debug_response
    )
    requests_mock.post(
        'https://mempool.aiblock.dev/debug_data',
        json=debug_response
    )

    # Mock storage debug data
    requests_mock.get(
        'https://storage.aiblock.dev/debug_data',
        json=debug_response
    )
    requests_mock.post(
        'https://storage.aiblock.dev/debug_data',
        json=debug_response
    )

    # Mock total supply endpoint
    requests_mock.get(
        'https://mempool.aiblock.dev/total_supply',
        json={
            'id': '2345-6789-0123-4567',
            'status': 'success',
            'reason': 'Total supply retrieved successfully',
            'content': {
                'total_supply': 1000000
            }
        }
    )

    # Mock issued supply endpoint
    requests_mock.get(
        'https://mempool.aiblock.dev/issued_supply',
        json={
            'id': '3456-7890-1234-5678',
            'status': 'success',
            'reason': 'Issued supply retrieved successfully',
            'content': {
                'issued_supply': 500000
            }
        }
    )

    # Mock balance endpoint
    requests_mock.post(
        'https://mempool.aiblock.dev/fetch_balance',
        json={
            'id': '4567-8901-2345-6789',
            'status': 'success',
            'reason': 'Balance successfully fetched',
            'content': {
                'total': {
                    'tokens': 0,
                    'items': {}
                },
                'address_list': {}
            }
        }
    )

    # Mock item creation endpoint
    requests_mock.post(
        'https://mempool.aiblock.dev/create_item_asset',
        json={
            'id': '5678-9012-3456-7890',
            'status': 'success',
            'reason': 'Item asset(s) created',
            'content': {
                'asset': {
                    'asset': {
                        'Item': {
                            'amount': 1000,
                            'genesis_hash': 'default_genesis_hash',
                            'metadata': None
                        }
                    }
                }
            }
        }
    )

    # Mock transaction creation endpoint
    requests_mock.post(
        'https://mempool.aiblock.dev/create_transactions',
        json={
            'id': '6789-0123-4567-8901',
            'status': 'success',
            'reason': 'Transaction created successfully',
            'content': {
                'transaction_id': 'test-tx-id'
            }
        }
    )

    # Mock storage endpoints
    requests_mock.get(
        'https://storage.aiblock.dev/latest_block',
        json={
            'id': '7890-1234-5678-9012',
            'status': 'success',
            'reason': 'Latest block retrieved successfully',
            'content': {
                'block_num': 1000,
                'block_hash': 'test_hash',
                'timestamp': 1234567890
            }
        }
    )

    # Mock block by number endpoint - now uses POST with array format
    requests_mock.post(
        'https://storage.aiblock.dev/block_by_num',
        json={
            'id': '8901-2345-6789-0123',
            'status': 'success',
            'reason': 'Block retrieved successfully',
            'content': {
                'block_num': 1000,
                'block_hash': 'test_hash',
                'timestamp': 1234567890,
                'transactions': []
            }
        }
    )

    # Mock blockchain entry endpoint - now uses POST with array format
    requests_mock.post(
        'https://storage.aiblock.dev/blockchain_entry',
        json={
            'id': '9012-3456-7890-1234',
            'status': 'success',
            'reason': 'Blockchain entry retrieved successfully',
            'content': {
                'block_num': 1000,
                'block_hash': 'test_hash',
                'previous_hash': 'prev_hash',
                'timestamp': 1234567890
            }
        }
    )

    # Mock error responses for new POST endpoints
    requests_mock.get(
        'https://storage.aiblock.dev/latest_block_error',
        status_code=500,
        text='Server error occurred'
    )

    # Error mocks for POST endpoints
    requests_mock.post(
        'https://storage.aiblock.dev/block_by_num_error',
        status_code=404,
        text='Block not found'
    )

    requests_mock.post(
        'https://storage.aiblock.dev/blockchain_entry_error',
        status_code=405,
        text='Method not allowed'
    )

    requests_mock.get(
        'https://mempool.aiblock.dev/total_supply_error',
        status_code=500,
        text='Server error occurred'
    )

    requests_mock.get(
        'https://mempool.aiblock.dev/issued_supply_error',
        status_code=202,
        text='Request is being processed'
    )

    return requests_mock

@pytest.fixture
def wallet(test_config: Dict[str, Any], mock_api) -> Wallet:
    """Fixture providing an initialized wallet instance."""
    wallet = Wallet(debug=True)
    # Initialize the wallet with a seed phrase
    seed_phrase = wallet.generate_seed_phrase()
    result = wallet.from_seed(seed_phrase, test_config)
    assert result.is_ok
    assert wallet.current_keypair is not None
    return wallet

@pytest.fixture
def offline_wallet(test_config: Dict[str, Any]) -> Wallet:
    """Fixture providing an offline wallet instance."""
    wallet = Wallet(debug=False)
    # Initialize the wallet with a seed phrase in offline mode
    seed_phrase = wallet.generate_seed_phrase()
    # For offline mode, we only need passphrase
    offline_config = {'passphrase': test_config['passphrase']}
    result = wallet.from_seed(seed_phrase, offline_config, init_offline=True)
    assert result.is_ok
    assert wallet.current_keypair is not None
    return wallet 