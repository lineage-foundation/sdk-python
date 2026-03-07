"""Tests for key handler functionality."""

import pytest
import base64
import hashlib
import nacl.signing
from aiblock.key_handler import (
    get_address_version,
    generate_seed_phrase,
    validate_seed_phrase,
    get_passphrase_buffer,
    generate_master_key,
    generate_keypair,
    construct_address,
    create_signature,
    truncate_string
)
from aiblock.interfaces import IErrorInternal, IResult, IMasterKey
from aiblock.constants import ADDRESS_VERSION, ADDRESS_VERSION_OLD, TEMP_ADDRESS_VERSION

def test_generate_seed_phrase():
    """Test seed phrase generation."""
    seed = generate_seed_phrase()
    assert isinstance(seed, str)
    assert len(seed.split()) == 12  # Should be 12 words
    assert validate_seed_phrase(seed)  # Should be valid

def test_validate_seed_phrase():
    """Test seed phrase validation."""
    # Valid seed phrase
    valid_seed = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    assert validate_seed_phrase(valid_seed)
    
    # Invalid cases
    assert not validate_seed_phrase("")  # Empty string
    assert not validate_seed_phrase(None)  # None
    assert not validate_seed_phrase("not a valid seed phrase")  # Invalid phrase
    assert not validate_seed_phrase("abandon " * 11)  # Too few words
    assert not validate_seed_phrase("abandon " * 13)  # Too many words

def test_get_passphrase_buffer():
    """Test passphrase buffer generation."""
    # Valid passphrase
    result = get_passphrase_buffer("test123")
    assert result.is_ok
    assert isinstance(result.get_ok(), bytes)
    assert len(result.get_ok()) > 0

    # None or empty string should return empty bytes
    result = get_passphrase_buffer(None)
    assert result.is_ok
    assert result.get_ok() == b''

    result = get_passphrase_buffer("")
    assert result.is_ok
    assert result.get_ok() == b''

def test_generate_master_key():
    """Test master key generation."""
    # Test without passphrase
    seed = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    result = generate_master_key(seed)
    assert result.is_ok
    master_key = result.get_ok()
    assert isinstance(master_key, IMasterKey)
    assert isinstance(master_key.secret, bytes)
    assert len(master_key.secret) == 64  # Master key should be 64 bytes
    assert master_key.seed == seed

    # Test with passphrase
    result_with_pass = generate_master_key(seed, "test123")
    assert result_with_pass.is_ok
    master_key_with_pass = result_with_pass.get_ok()
    assert isinstance(master_key_with_pass, IMasterKey)
    assert isinstance(master_key_with_pass.secret, bytes)
    assert len(master_key_with_pass.secret) == 64
    assert master_key_with_pass.seed == seed
    
    # Verify different passphrases produce different keys
    assert master_key.secret != master_key_with_pass.secret

    # Invalid seed
    result = generate_master_key("invalid seed phrase")
    assert result.is_err
    assert result.error == IErrorInternal.InvalidSeedPhrase

    # Empty seed
    result = generate_master_key("")
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided

    # None seed
    result = generate_master_key(None)
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided

def test_generate_keypair():
    """Test keypair generation."""
    # Default version
    result = generate_keypair()
    assert result.is_ok
    keypair = result.get_ok()
    assert len(keypair.secret_key) == 32
    assert len(keypair.public_key) == 32
    assert len(keypair.address) == 64  # sha3_256 hex string length
    assert keypair.version == ADDRESS_VERSION
    
    # With seed
    seed = bytes([i for i in range(32)])  # 32 bytes
    result_with_seed = generate_keypair(seed=seed)
    assert result_with_seed.is_ok
    assert result_with_seed.get_ok().secret_key == seed  # Should use provided seed
    
    # With different version
    result_temp = generate_keypair(version=TEMP_ADDRESS_VERSION)
    assert result_temp.is_ok
    assert result_temp.get_ok().version == TEMP_ADDRESS_VERSION
    
    # Invalid seed length
    long_seed = bytes([i for i in range(64)])
    result_long_seed = generate_keypair(seed=long_seed)
    assert result_long_seed.is_ok  # Should truncate to 32 bytes
    assert len(result_long_seed.get_ok().secret_key) == 32

def test_construct_address():
    """Test address construction."""
    keypair = generate_keypair().get_ok()
    public_key = keypair.public_key
    
    # Default version
    result = construct_address(public_key, ADDRESS_VERSION)
    assert result.is_ok
    assert len(result.get_ok()) == 64  # sha3_256 hex string length
    
    # Old version
    result_old = construct_address(public_key, ADDRESS_VERSION_OLD)
    assert result_old.is_ok
    assert len(result_old.get_ok()) == 48  # Truncated length
    
    # Temp version
    result_temp = construct_address(public_key, TEMP_ADDRESS_VERSION)
    assert result_temp.is_ok
    assert len(result_temp.get_ok()) == 64  # sha3_256 hex string length
    
    # Invalid version
    assert construct_address(public_key, 999).is_err

def test_get_address_version():
    """Test address version detection."""
    keypair = generate_keypair().get_ok()
    public_key = keypair.public_key
    
    # Get addresses for different versions
    default_addr = construct_address(public_key, ADDRESS_VERSION).get_ok()
    temp_addr = construct_address(public_key, TEMP_ADDRESS_VERSION).get_ok()
    
    # Test version detection
    result = get_address_version(public_key=public_key, address=default_addr)
    assert result.is_ok
    assert result.get_ok() == ADDRESS_VERSION  # Default version returns ADDRESS_VERSION
    
    result_temp = get_address_version(public_key=public_key, address=temp_addr)
    assert result_temp.is_ok
    assert result_temp.get_ok() == TEMP_ADDRESS_VERSION
    
    # Invalid cases
    assert get_address_version().is_err  # No parameters
    assert get_address_version(version=999).is_err  # Invalid version
    assert get_address_version(public_key=public_key, address="invalid").is_err

def test_create_signature():
    """Test signature creation."""
    keypair = generate_keypair().get_ok()
    message = b"test message"
    
    # Create signature
    signature = create_signature(keypair.secret_key, message)
    assert isinstance(signature, bytes)
    assert len(signature) == 64  # Ed25519 signature length
    
    # Verify signature
    verify_key = nacl.signing.VerifyKey(keypair.public_key)
    try:
        verify_key.verify(message, signature)
        assert True  # Signature verification successful
    except:
        assert False  # Should not reach here

def test_truncate_string():
    """Test string truncation."""
    # Normal case
    assert truncate_string("12345", 3) == "123"
    
    # String shorter than max length
    assert truncate_string("123", 5) == "123"
    
    # Empty string
    assert truncate_string("", 5) == ""
    
    # None with default values
    assert truncate_string() == ""
    
    # Long string
    long_str = "a" * 100
    assert len(truncate_string(long_str, 50)) == 50 