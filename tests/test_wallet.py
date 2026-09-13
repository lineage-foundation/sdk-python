import pytest
import sys
import logging
from pathlib import Path
from lineage.wallet import Wallet, ITEM_DEFAULT
from lineage.interfaces import IResult, IErrorInternal, IMasterKey
import hashlib
import json
from typing import Dict, Any
from unittest.mock import patch

# Set up logging
logger = logging.getLogger(__name__)

# Add the package root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lineage import wallet
from lineage.key_handler import generate_seed_phrase, validate_seed_phrase, generate_master_key

def test_seed_phrase_generation():
    """Test that seed phrase generation works and produces valid phrases."""
    seed = generate_seed_phrase()
    assert isinstance(seed, str)
    assert len(seed.split()) == 12  # Standard BIP39 uses 12 words
    assert validate_seed_phrase(seed) is True

def test_master_key_generation():
    """Test that master key generation works with a valid seed phrase."""
    seed = generate_seed_phrase()
    # Test without passphrase
    master_key_result = generate_master_key(seed)
    assert master_key_result.is_ok
    master_key = master_key_result.get_ok()
    assert isinstance(master_key, IMasterKey)
    assert isinstance(master_key.secret, bytes)
    assert len(master_key.secret) == 64  # Master key should be 64 bytes
    assert master_key.seed == seed

    # Test with passphrase
    master_key_result_with_pass = generate_master_key(seed, "test123")
    assert master_key_result_with_pass.is_ok
    master_key_with_pass = master_key_result_with_pass.get_ok()
    assert isinstance(master_key_with_pass, IMasterKey)
    assert isinstance(master_key_with_pass.secret, bytes)
    assert len(master_key_with_pass.secret) == 64
    assert master_key_with_pass.seed == seed

def test_wallet_initialization(test_config):
    """Test basic wallet initialization."""
    wallet = Wallet()
    seed_phrase = wallet.generate_seed_phrase()
    result = wallet.from_seed(seed_phrase, test_config)
    assert result.is_ok
    assert wallet.current_keypair is not None
    assert wallet.network_config.get('mempoolHost') == test_config['mempoolHost']
    assert wallet.network_config.get('storageHost') == test_config['storageHost']
    assert wallet.network_config.get('valenceHost') == test_config['valenceHost']

def test_offline_wallet_initialization(test_config):
    wallet = Wallet()
    seed_phrase = wallet.generate_seed_phrase()
    result = wallet.from_seed(seed_phrase, test_config, init_offline=True)
    assert result.is_ok
    assert wallet.current_keypair is not None

def test_wallet_error_handling(test_config):
    wallet = Wallet()
    result = wallet.from_seed("invalid seed phrase", test_config)
    assert result.is_err
    assert wallet.current_keypair is None

def test_wallet_invalid_config():
    wallet = Wallet()
    seed_phrase = wallet.generate_seed_phrase()
    result = wallet.from_seed(seed_phrase, {})
    assert result.is_err
    assert wallet.current_keypair is None

def test_wallet_invalid_seed_phrase(test_config):
    wallet = Wallet()
    result = wallet.from_seed("", test_config)
    assert result.is_err
    assert wallet.current_keypair is None

def test_wallet_invalid_config_missing_keys(test_config):
    """Test wallet initialization with missing config keys."""
    wallet = Wallet()
    seed_phrase = wallet.generate_seed_phrase()
    invalid_config = test_config.copy()
    del invalid_config['mempoolHost']
    result = wallet.from_seed(seed_phrase, invalid_config)
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "Missing or invalid mempoolHost" in result.error_message

def test_wallet_invalid_config_invalid_urls(test_config):
    """Test wallet initialization with invalid URLs."""
    wallet = Wallet()
    seed_phrase = wallet.generate_seed_phrase()
    invalid_config = test_config.copy()
    invalid_config['mempoolHost'] = 'invalid_url'
    result = wallet.from_seed(seed_phrase, invalid_config)
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "Invalid URL for mempoolHost" in result.error_message

def test_wallet_invalid_config_missing_hosts(test_config):
    """Test wallet initialization with missing hosts."""
    wallet = Wallet()
    seed_phrase = wallet.generate_seed_phrase()
    invalid_config = {}  # Empty config should fail validation
    result = wallet.from_seed(seed_phrase, invalid_config)
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided

def test_create_item_asset(wallet: Wallet, mock_api):
    """Test item asset creation posts to /v1/items with no `version` field and maps the response."""
    # Test with default values
    response = wallet.create_item_asset(
        secret_key=wallet.current_keypair.secret_key,
        public_key=wallet.current_keypair.public_key,
        version=wallet.current_keypair.version
    )
    assert response.is_ok
    assert mock_api.last_request.url == 'https://mempool.lineage.to/v1/items'
    body = mock_api.last_request.json()
    assert 'version' not in body
    assert body['item_amount'] == ITEM_DEFAULT
    assert body['metadata'] is None
    content = response.get_ok()
    assert content['to_address'] == 'test_to_address'
    assert content['tx_hash'] == 'test_tx_hash'
    assert content['asset']['kind'] == 'item'

    # Test with custom metadata
    metadata = {"test": "data"}
    response = wallet.create_item_asset(
        secret_key=wallet.current_keypair.secret_key,
        public_key=wallet.current_keypair.public_key,
        version=wallet.current_keypair.version,
        amount=100,
        metadata=metadata
    )
    assert response.is_ok
    body = mock_api.last_request.json()
    assert 'version' not in body
    assert body['item_amount'] == 100
    assert json.loads(body['metadata']) == metadata

def test_create_item_asset_matches_golden_vector_signature(wallet: Wallet, mock_api):
    """The /v1/items signature must be byte-identical to Task 1's golden-vector item signature."""
    item_public_key = bytes.fromhex(
        "69fee81c9045b35eaf04b74bfa7983618a08acb719ef8d3749a4f004a293cadf"
    )
    item_secret_key = bytes.fromhex(
        "fcba9969899335500359aa45ae7008c7dd8b16883dfe8ea39a799259e70f985a"
    )
    response = wallet.create_item_asset(
        secret_key=item_secret_key,
        public_key=item_public_key,
        version=wallet.current_keypair.version,
        amount=1000,
    )
    assert response.is_ok
    body = mock_api.last_request.json()
    assert body['signature'] == (
        "277d56770697ba1f6cec5e859aa4dcdff0ec4a261c75408092d44a38e768461"
        "a45fc0a7964ecb4714eb2849b0cd4c43e107db76f8a62c6b783342a895889b80c"
    )
    assert body['public_key'] == (
        "69fee81c9045b35eaf04b74bfa7983618a08acb719ef8d3749a4f004a293cadf"
    )
    assert 'version' not in body

def test_create_item_asset_problem_json_error(wallet: Wallet, mock_api):
    """A problem+json error from /v1/items maps onto the SDK's error type."""
    mock_api.post(
        'https://mempool.lineage.to/v1/items',
        status_code=400,
        json={'type': 'about:blank', 'title': 'Bad Request', 'status': 400, 'detail': 'invalid genesis_hash_spec'}
    )
    response = wallet.create_item_asset(
        secret_key=wallet.current_keypair.secret_key,
        public_key=wallet.current_keypair.public_key,
        version=wallet.current_keypair.version,
    )
    assert response.is_err
    assert response.error == IErrorInternal.BadRequest
    assert 'invalid genesis_hash_spec' in response.error_message

# 2-way (DRUID) payment flow methods (make/fetch/accept/reject) are covered
# by tests/test_twoway_flow.py against the rewritten plaintext valence
# `/messages` transport - see that file rather than this one.

def test_sign_message(wallet: Wallet):
    """Test message signing."""
    # Test with string message
    message = "test message"
    signature = wallet.sign_message(message)
    assert isinstance(signature, str)
    assert len(signature) > 0

    # Test with bytes message
    message_bytes = b"test message"
    signature = wallet.sign_message(message_bytes)
    assert isinstance(signature, str)
    assert len(signature) > 0

    # Test with empty message
    signature = wallet.sign_message("")
    assert isinstance(signature, str)
    assert len(signature) > 0

def test_get_balance(wallet: Wallet, mock_api):
    """Test balance retrieval."""
    # Update mock to return the correct response structure
    mock_api.post('https://mempool.lineage.to/v1/balances/query', json={
        'balance': {
            'total': {
                'tokens': 0,
                'items': {}
            }
        }
    })

    balance_result = wallet.get_balance()
    assert balance_result.is_ok
    balance = balance_result.get_ok()
    assert isinstance(balance, dict)
    assert 'total' in balance
    assert 'tokens' in balance['total']
    assert 'items' in balance['total']

def test_create_transactions_insufficient_balance(wallet: Wallet, mock_api):
    """Test transaction creation with insufficient balance."""
    # Update mock to return zero balance
    mock_api.post('https://mempool.lineage.to/v1/balances/query', json={
        'balance': {
            'total': {
                'tokens': 0,
                'items': {}
            }
        }
    })

    # Try to create a transaction with more tokens than available
    result = wallet.create_transactions("destination_address", 100)
    assert result.is_err
    assert result.error == IErrorInternal.InsufficientFunds

def test_create_transactions_matches_golden_vector(wallet: Wallet, mock_api):
    """`create_transactions` must submit the exact golden-vector-signed tx to /v1/transactions.

    Reuses the fixed 3-address wallet/UTXO fixtures from
    `tests/test_transaction_signing.py` (Scenario A: an exact `Token: 60`
    payment, no excess) so the signed transaction is deterministic and can
    be asserted against known-good sdk-js-derived signatures.
    """
    from lineage.interfaces import IKeypair
    from tests.test_transaction_signing import (
        ADDR1_ADDRESS, ADDR1_PUBLIC_KEY_HEX, ADDR1_SECRET_KEY_HEX,
        ADDR2_ADDRESS, ADDR2_PUBLIC_KEY_HEX, ADDR2_SECRET_KEY_HEX,
        ADDR3_ADDRESS, ADDR3_PUBLIC_KEY_HEX, ADDR3_SECRET_KEY_HEX,
        PAYMENT_ADDRESS, EXCESS_ADDRESS, _seed, _fetch_balance_response,
    )

    def keypair(address, public_key_hex, secret_key_hex):
        return IKeypair(
            address=address,
            secret_key=_seed(secret_key_hex),
            public_key=bytes.fromhex(public_key_hex),
            version=1,
        )

    all_keypairs = [
        keypair(ADDR1_ADDRESS, ADDR1_PUBLIC_KEY_HEX, ADDR1_SECRET_KEY_HEX),
        keypair(ADDR2_ADDRESS, ADDR2_PUBLIC_KEY_HEX, ADDR2_SECRET_KEY_HEX),
        keypair(ADDR3_ADDRESS, ADDR3_PUBLIC_KEY_HEX, ADDR3_SECRET_KEY_HEX),
    ]
    wallet.current_keypair = keypair(EXCESS_ADDRESS, ADDR2_PUBLIC_KEY_HEX, ADDR2_SECRET_KEY_HEX)

    mock_api.post(
        'https://mempool.lineage.to/v1/balances/query',
        json={'balance': _fetch_balance_response()}
    )
    mock_api.post(
        'https://mempool.lineage.to/v1/transactions',
        status_code=201,
        json={
            'transactions': {
                'golden-vector-tx-hash': {
                    'address': PAYMENT_ADDRESS,
                    'asset': {'kind': 'token', 'amount': 60}
                }
            }
        }
    )

    result = wallet.create_transactions(
        PAYMENT_ADDRESS, 60, all_keypairs=all_keypairs, excess_keypair=wallet.current_keypair
    )
    assert result.is_ok

    body = mock_api.last_request.json()
    assert body == {
        'transactions': [
            {
                'inputs': [
                    {
                        'previous_out': {'t_hash': '000000', 'n': 0},
                        'script_signature': {
                            'Pay2PkH': {
                                'signable_data': (
                                    '41b8515c80bbe065cebcfeae1e1487eec1cd8506a9119030669b8d646a9a568e'
                                ),
                                'signature': (
                                    '8c0e700361647f1cb2f5918e97fd3f085dc406d7d776da976438eb423f5bcef1'
                                    '9a4f9020342423467bd60d438307046c2f2d099e91eaba70c19064b68c7a6406'
                                ),
                                'public_key': ADDR1_PUBLIC_KEY_HEX,
                                'address_version': None,
                            }
                        },
                    },
                    {
                        'previous_out': {'t_hash': '000001', 'n': 0},
                        'script_signature': {
                            'Pay2PkH': {
                                'signable_data': (
                                    '728eb0ea255c492736667c6c61d56cf54534c35b2027f967f4a5cbe649059d32'
                                ),
                                'signature': (
                                    'b5cde58d3f85fcde78432fa436cfd520e25bcf217612600d2cf5419db02798cc'
                                    '7b5ed1082350778b56b60806642c180f5348ce35fb5353b443e2969b88bcd00a'
                                ),
                                'public_key': ADDR2_PUBLIC_KEY_HEX,
                                'address_version': None,
                            }
                        },
                    },
                ],
                'outputs': [
                    {
                        'value': {'Token': 60},
                        'locktime': 0,
                        'script_public_key': PAYMENT_ADDRESS,
                    }
                ],
                'version': 2,
                'druid_info': None,
                'fees': None,
            }
        ]
    }

    content = result.get_ok()
    assert content['transaction_hash'] == 'golden-vector-tx-hash'
    assert content['payment_address'] == PAYMENT_ADDRESS
    assert content['asset'] == {'kind': 'token', 'amount': 60}
    assert content['used_addresses'] == [ADDR1_ADDRESS, ADDR2_ADDRESS]

def test_create_transactions_problem_json_error(wallet: Wallet, mock_api):
    """A problem+json error from /v1/transactions maps onto the SDK's error type."""
    from lineage.interfaces import IKeypair
    from tests.test_transaction_signing import (
        ADDR1_ADDRESS, ADDR1_PUBLIC_KEY_HEX, ADDR1_SECRET_KEY_HEX,
        ADDR2_ADDRESS, ADDR2_PUBLIC_KEY_HEX, ADDR2_SECRET_KEY_HEX,
        ADDR3_ADDRESS, ADDR3_PUBLIC_KEY_HEX, ADDR3_SECRET_KEY_HEX,
        PAYMENT_ADDRESS, _seed, _fetch_balance_response,
    )

    def keypair(address, public_key_hex, secret_key_hex):
        return IKeypair(
            address=address,
            secret_key=_seed(secret_key_hex),
            public_key=bytes.fromhex(public_key_hex),
            version=1,
        )

    all_keypairs = [
        keypair(ADDR1_ADDRESS, ADDR1_PUBLIC_KEY_HEX, ADDR1_SECRET_KEY_HEX),
        keypair(ADDR2_ADDRESS, ADDR2_PUBLIC_KEY_HEX, ADDR2_SECRET_KEY_HEX),
        keypair(ADDR3_ADDRESS, ADDR3_PUBLIC_KEY_HEX, ADDR3_SECRET_KEY_HEX),
    ]
    wallet.current_keypair = all_keypairs[0]

    mock_api.post(
        'https://mempool.lineage.to/v1/balances/query',
        json={'balance': _fetch_balance_response()}
    )
    mock_api.post(
        'https://mempool.lineage.to/v1/transactions',
        status_code=400,
        json={'type': 'about:blank', 'title': 'Bad Request', 'status': 400, 'detail': 'invalid signature'}
    )

    result = wallet.create_transactions(PAYMENT_ADDRESS, 60, all_keypairs=all_keypairs)
    assert result.is_err
    assert result.error == IErrorInternal.BadRequest
    assert 'invalid signature' in result.error_message

def test_transaction_signing(wallet: Wallet):
    """Test transaction signing functionality."""
    # Create test transaction data
    outputs = [{
        "value": {"Token": 100},
        "locktime": 0,
        "script_public_key": "test_address"
    }]
    
    # Test signing data
    signable_data = {
        "input_index": 0,
        "out_point": "test_outpoint",
        "outputs": outputs
    }
    
    # Create canonical JSON string and hash
    signable_str = json.dumps(signable_data, separators=(',', ':'), sort_keys=True)
    tx_hash = hashlib.sha3_256(signable_str.encode()).hexdigest()
    
    # Sign the hash
    signature = wallet.sign_message(tx_hash)
    assert isinstance(signature, str)
    assert len(signature) > 0

def test_invalid_seed_phrase():
    """Test that invalid seed phrases are properly rejected."""
    invalid_seed = "not a valid seed phrase at all"
    assert validate_seed_phrase(invalid_seed) is False

    master_key_result = generate_master_key(invalid_seed)
    assert master_key_result.is_err
    assert master_key_result.error == IErrorInternal.InvalidSeedPhrase

def test_wallet_initialization_invalid_config(wallet_instance):
    """Test that wallet initialization fails with invalid configuration."""
    invalid_config = {
        # Missing required fields
        'passphrase': 'test_passphrase'
    }

    init_result = wallet_instance.init_new(invalid_config)
    assert init_result.is_err
    assert init_result.error == IErrorInternal.InvalidParametersProvided
    assert "Missing or invalid mempoolHost" in init_result.error_message

def test_invalid_config():
    """Test wallet initialization with invalid config."""
    result = Wallet().init_new({})
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "No configuration provided" in result.error_message

# Remove blockchain-related tests since they are now in test_blockchain.py 