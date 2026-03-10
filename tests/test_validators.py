"""Tests for validator functionality."""

import time
import pytest
import logging
from lineage.validators import (
    validate_metadata,
    validate_transaction,
    validate_transaction_fields
)
from lineage.interfaces import IResult, IErrorInternal
from lineage.constants import MAX_METADATA_SIZE

# Set up logging
logger = logging.getLogger(__name__)

def test_validate_metadata():
    """Test metadata validation."""
    # Test valid metadata
    valid_metadata = {"key": "value"}
    result = validate_metadata(valid_metadata)
    assert result.is_ok
    assert result.get_ok() == valid_metadata

    # Test invalid metadata
    invalid_metadata = None
    result = validate_metadata(invalid_metadata)
    assert result.is_err
    assert "Invalid type provided" in result.error_message

def test_validate_metadata_size():
    """Test metadata size validation."""
    # Test metadata within size limit
    valid_metadata = {"key": "value"}
    result = validate_metadata(valid_metadata)
    assert result.is_ok
    assert result.get_ok() == valid_metadata

    # Test metadata exceeding size limit
    large_metadata = {"key": "x" * (MAX_METADATA_SIZE + 1)}
    result = validate_metadata(large_metadata)
    assert result.is_err
    assert "Exceeds maximum size" in result.error_message

def test_validate_transaction():
    """Test transaction validation."""
    # Test valid transaction
    valid_tx = {
        "sender": "sender_address",
        "receiver": "receiver_address",
        "amount": 100,
        "fee": 1,
        "nonce": 1,
        "timestamp": int(time.time())
    }
    result = validate_transaction(valid_tx)
    assert result.is_ok
    assert result.get_ok() == valid_tx

def test_validate_transaction_fields():
    """Test transaction field validation."""
    # Test missing required fields
    missing_fields_tx = {
        "sender": "sender_address",
        "receiver": "receiver_address"
    }
    result = validate_transaction(missing_fields_tx)
    assert result.is_err
    assert "Missing required fields" in result.error_message

def test_validate_metadata_valid():
    """Test metadata validation with valid input."""
    valid_metadata = {
        'name': 'Test Item',
        'description': 'A test item',
        'image': 'https://example.com/image.png',
        'attributes': [
            {'trait_type': 'Rarity', 'value': 'Common'},
            {'trait_type': 'Type', 'value': 'Test'}
        ]
    }
    
    result = validate_metadata(valid_metadata)
    assert result.is_ok
    assert result.get_ok() == valid_metadata

def test_validate_metadata_invalid_type():
    """Test metadata validation with invalid type."""
    invalid_inputs = [
        None,
        "not a dict",
        123,
        [],
        True
    ]
    
    for invalid_input in invalid_inputs:
        result = validate_metadata(invalid_input)
        assert result.is_err
        assert result.error == IErrorInternal.InvalidParametersProvided
        assert "Invalid type provided" in result.error_message

def test_validate_metadata_non_serializable():
    """Test metadata validation with non-JSON-serializable content."""
    from datetime import datetime
    
    invalid_metadata = {
        'name': 'Test Item',
        'timestamp': datetime.now(),  # datetime is not JSON serializable
        'function': lambda x: x  # function is not JSON serializable
    }
    
    result = validate_metadata(invalid_metadata)
    assert result.is_err
    assert result.error == IErrorInternal.InvalidParametersProvided
    assert "not JSON serializable" in result.error_message

def test_validate_metadata_nested():
    """Test metadata validation with nested structures."""
    nested_metadata = {
        'name': 'Test Item',
        'details': {
            'category': 'Test',
            'subcategories': ['A', 'B', 'C'],
            'properties': {
                'size': 'large',
                'color': 'blue',
                'tags': ['tag1', 'tag2']
            }
        }
    }
    
    result = validate_metadata(nested_metadata)
    assert result.is_ok
    assert result.get_ok() == nested_metadata

def test_validate_metadata_empty():
    """Test metadata validation with empty dict."""
    result = validate_metadata({})
    assert result.is_ok
    assert result.get_ok() == {} 