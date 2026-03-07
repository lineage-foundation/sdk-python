import pytest
import sys
import logging
from pathlib import Path
from aiblock.wallet import Wallet, ITEM_DEFAULT
from aiblock.interfaces import IResult, IErrorInternal, IMasterKey
import hashlib
import json
from typing import Dict, Any
from unittest.mock import patch

# Set up logging
logger = logging.getLogger(__name__)

# Add the package root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiblock import wallet
from aiblock.key_handler import generate_seed_phrase, validate_seed_phrase, generate_master_key

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
    """Test item asset creation."""
    # Mock the create_item_asset endpoint
    mock_api.post('https://mempool.aiblock.dev/create_item_asset', json={
        'status': 'success',
        'reason': 'Item asset created successfully',
        'content': {
            'item_id': '123',
            'amount': ITEM_DEFAULT
        }
    })

    # Test with default values
    response = wallet.create_item_asset(
        secret_key=wallet.current_keypair.secret_key,
        public_key=wallet.current_keypair.public_key,
        version=wallet.current_keypair.version
    )
    assert response.is_ok

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

def test_2way_payment_methods(wallet: Wallet, mock_api):
    """Test 2WayPayment methods: make, fetch, accept, reject."""
    from aiblock.interfaces import IResult
    # Patch: Ensure passphrase_key is set for decryption
    wallet.passphrase_key = b"test_passphrase_key_32bytes_long!"
    # Patch: Ensure current_keypair is set and matches all_keypairs
    wallet.current_keypair = wallet.generate_keypair().get_ok()

    # Mock make_2way_payment endpoint
    mock_api.post('https://mempool.aiblock.dev/make_2way_payment', json={
        'status': 'success',
        'reason': '2Way payment created',
        'content': {'druid': 'druid123', 'encryptedTx': 'encrypted_data'}
    })
    # Mock fetch_pending_2way_payments endpoint (mempool)
    mock_api.post('https://mempool.aiblock.dev/fetch_pending_2way_payments', json={
        'status': 'success',
        'reason': 'Fetched',
        'content': {'pending': {'druid123': {'details': 'pending details'}}}
    })
    # Mock fetch_pending_2way_payments endpoint (valence)
    mock_api.post('https://valence.aiblock.dev/fetch_pending_2way_payments', json={
        'status': 'success',
        'reason': 'Fetched',
        'content': {'pending': {'druid123': {'encryptedTx': {'nonce': 'bm9uY2U=', 'ciphertext': 'Y2lwaGVydGV4dA=='}, 'senderPublicKey': 'AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE='}}}
    })
    # Mock accept_2way_payment endpoint (valence)
    mock_api.post('https://valence.aiblock.dev/accept_2way_payment', json={
        'status': 'success',
        'reason': 'Accepted',
        'content': {'result': 'accepted'}
    })
    # Mock reject_2way_payment endpoint (valence)
    mock_api.post('https://valence.aiblock.dev/reject_2way_payment', json={
        'status': 'success',
        'reason': 'Rejected',
        'content': {'result': 'rejected'}
    })
    # Mock valence_set endpoint for make_2way_payment
    mock_api.post('https://valence.aiblock.dev/valence_set', json={
        'status': 'success',
        'reason': 'Valence set successful',
        'content': {'result': 'valence_set'}
    })

    # Prepare dummy data
    payment_address = wallet.current_keypair.address
    sending_asset = {"Token": 100}
    receiving_asset = {"Item": {"amount": 1}}
    all_keypairs = [wallet.current_keypair]  # Use the real keypair object
    # Simulate an encrypted keypair dict for receive_address (as expected by decrypt_keypair)
    receive_address = {
        'public_key': wallet.current_keypair.public_key,
        'secret_key': wallet.current_keypair.secret_key,
        'address': wallet.current_keypair.address,
        'version': wallet.current_keypair.version
    }

    # Patch decrypt_keypair to return a valid keypair
    from unittest.mock import patch as upatch
    with upatch.object(wallet, "decrypt_keypair") as mock_decrypt:
        mock_decrypt.return_value.is_err = False
        mock_decrypt.return_value.is_ok = True
        mock_decrypt.return_value.get_ok = lambda: wallet.current_keypair
        # Patch fetch_balance to return a real IResult for make_2way_payment
        utxo_dict = {"utxos": [{
            "txid": "txid1",
            "vout": 0,
            "address": payment_address,
            "assetType": "Token",
            "amount": 100
        }]}
        with upatch.object(wallet, "fetch_balance") as mock_balance:
            mock_balance.return_value = IResult.ok(utxo_dict)
            # Test make_2way_payment
            result = wallet.make_2way_payment(payment_address, sending_asset, receiving_asset, all_keypairs, receive_address)
    # Now, outside the with blocks, check the result
    assert result.is_ok
    assert 'druid' in result.get_ok()

    # Test fetch_pending_2way_payments
    result = wallet.fetch_pending_2way_payments(all_keypairs, ["encrypted_data"])
    assert result.is_ok
    assert 'pending' in result.get_ok()

    # Test accept_2way_payment
    # Patch: Provide a pending_dict with a valid half_tx and a matching UTXO
    druid = 'druid123'
    half_tx = {
        "outputs": [{"address": payment_address, "assetType": "Token", "amount": 100}],
        "inputs": [],
        "druidInfo": {
            "senderExpectation": {"from": "", "to": "address2", "asset": {"Token": 100}},
            "receiverExpectation": {"from": "", "to": payment_address, "asset": {"Token": 100}}
        }
    }
    pending_dict = {druid: half_tx}
    # Patch fetch_balance to return a real IResult for accept_2way_payment
    with patch.object(wallet, "fetch_balance") as mock_balance:
        mock_balance.return_value = IResult.ok(utxo_dict)
        result = wallet.accept_2way_payment(druid, pending_dict, all_keypairs)
        assert result.is_ok
        assert result.get_ok()['result'] == 'accepted'

    # Test reject_2way_payment
    result = wallet.reject_2way_payment('druid123', {'druid123': {'details': 'pending details'}}, all_keypairs)
    assert result.is_ok
    assert result.get_ok()['result'] == 'rejected'

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
    mock_api.post('https://mempool.aiblock.dev/fetch_balance', json={
        'status': 'success',
        'reason': 'Balance successfully fetched',
        'content': {
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
    mock_api.post('https://mempool.aiblock.dev/fetch_balance', json={
        'status': 'success',
        'reason': 'Balance successfully fetched',
        'content': {
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

def test_headers_generation(wallet: Wallet):
    """Test API headers generation."""
    headers = wallet.get_headers()
    assert 'Content-Type' in headers
    assert 'Accept' in headers
    assert 'Request-ID' in headers
    assert 'Nonce' in headers
    assert headers['Content-Type'] == 'application/json'
    assert headers['Accept'] == 'application/json'
    assert len(headers['Request-ID']) > 0
    assert len(headers['Nonce']) > 0

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

def dummy_keypair():
    return {
        "address": "address1",
        "public_key": b"\x01" * 32,
        "secret_key": b"\x02" * 32,
        "version": 1
    }

def dummy_wallet():
    from aiblock.wallet import Wallet
    wallet = Wallet()
    wallet.network_config = {
        "valenceHost": "http://mockvalence"
    }
    wallet.get_headers = lambda: {"Content-Type": "application/json"}
    return wallet

def test_fetch_pending_2way_payments():
    wallet = dummy_wallet()
    keypair = dummy_keypair()
    encrypted_tx = {
        "nonce": "bm9uY2U=",  # base64 of 'nonce'
        "ciphertext": "Y2lwaGVydGV4dA=="  # base64 of 'ciphertext'
    }
    sender_pub_b64 = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="  # base64 of 32 bytes
    mock_response = {
        "content": {
            "pending": {
                "druid123": {
                    "encryptedTx": encrypted_tx,
                    "senderPublicKey": sender_pub_b64
                }
            }
        }
    }
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response
        # Patch decryption to just return a dummy tx
        with patch.object(wallet, "fetch_pending_2way_payments", wraps=wallet.fetch_pending_2way_payments) as real_method:
            result = real_method([keypair], ["dummy_encrypted"])
            assert result.is_ok
            assert "pending" in result.get_ok()

def test_accept_2way_payment():
    wallet = dummy_wallet()
    keypair = dummy_keypair()
    wallet.passphrase_key = b"test_passphrase_key_32bytes_long!"
    druid = "druid123"
    half_tx = {
        "outputs": [{"address": keypair["address"], "assetType": "Token", "amount": 100}],
        "inputs": [],
        "druidInfo": {
            "senderExpectation": {"from": "", "to": "address2", "asset": {"Token": 100}},
            "receiverExpectation": {"from": "", "to": keypair["address"], "asset": {"Token": 100}}
        }
    }
    pending_dict = {druid: half_tx}
    all_keypairs = [keypair]
    # Patch fetch_balance to return a matching UTXO
    with patch("requests.post") as mock_post, patch.object(wallet, "fetch_balance") as mock_balance:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"content": {"result": "accepted"}}
        mock_balance.return_value.get_ok = lambda: {"utxos": [{
            "txid": "txid1",
            "vout": 0,
            "address": keypair["address"],
            "assetType": "Token",
            "amount": 100
        }]}
        result = wallet.accept_2way_payment(druid, pending_dict, all_keypairs)
        assert result.is_ok

def test_reject_2way_payment():
    wallet = dummy_wallet()
    druid = "druid123"
    pending_dict = {druid: {}}
    all_keypairs = []
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"content": {"result": "rejected"}}
        result = wallet.reject_2way_payment(druid, pending_dict, all_keypairs)
        assert result.is_ok 