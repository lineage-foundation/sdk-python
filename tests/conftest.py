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
        'mempoolHost': 'https://mempool.lineage.to',
        'storageHost': 'https://storage.lineage.to',
        'valenceHost': 'https://valence.lineage.to'
    }

@pytest.fixture
def wallet_instance():
    """Fixture providing a fresh wallet instance."""
    return Wallet()

@pytest.fixture
def test_config() -> Dict[str, Any]:
    """Fixture providing test configuration."""
    return {
        'mempoolHost': 'https://mempool.lineage.to',
        'storageHost': 'https://storage.lineage.to',
        'valenceHost': 'https://valence.lineage.to'
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
        'https://mempool.lineage.to/debug_data',
        json=debug_response
    )
    requests_mock.post(
        'https://mempool.lineage.to/debug_data',
        json=debug_response
    )

    # Mock storage debug data
    requests_mock.get(
        'https://storage.lineage.to/debug_data',
        json=debug_response
    )
    requests_mock.post(
        'https://storage.lineage.to/debug_data',
        json=debug_response
    )

    # Mock supply endpoint (/v1) - backs both total_supply and issued_supply
    requests_mock.get(
        'https://mempool.lineage.to/v1/supply',
        json={
            'total': 1000000,
            'issued': 500000
        }
    )

    # Mock balance endpoint (/v1)
    requests_mock.post(
        'https://mempool.lineage.to/v1/balances/query',
        json={
            'balance': {
                'total': {
                    'tokens': 0,
                    'items': {}
                },
                'address_list': {}
            }
        }
    )

    # Mock item creation endpoint (/v1)
    requests_mock.post(
        'https://mempool.lineage.to/v1/items',
        status_code=201,
        json={
            'asset': {
                'kind': 'item',
                'amount': 1000,
                'genesis_hash': 'default_genesis_hash',
                'metadata': None
            },
            'to_address': 'test_to_address',
            'tx_hash': 'test_tx_hash'
        }
    )

    # Mock transaction creation endpoint (/v1)
    requests_mock.post(
        'https://mempool.lineage.to/v1/transactions',
        status_code=201,
        json={
            'transactions': {
                'test-tx-hash': {
                    'address': 'test_destination_address',
                    'asset': {'kind': 'token', 'amount': 100}
                }
            }
        }
    )

    # Mock storage endpoints (/v1)
    requests_mock.get(
        'https://storage.lineage.to/v1/blocks/latest',
        json={
            'block_num': 1000,
            'block_hash': 'test_hash',
            'timestamp': 1234567890
        }
    )

    # Mock block by number endpoint
    requests_mock.get(
        'https://storage.lineage.to/v1/blocks',
        json={
            'block_num': 1000,
            'block_hash': 'test_hash',
            'timestamp': 1234567890,
            'transactions': []
        }
    )

    # Mock blockchain entries query endpoint
    requests_mock.post(
        'https://storage.lineage.to/v1/blockchain-entries/query',
        json={
            'block_num': 1000,
            'block_hash': 'test_hash',
            'previous_hash': 'prev_hash',
            'timestamp': 1234567890
        }
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