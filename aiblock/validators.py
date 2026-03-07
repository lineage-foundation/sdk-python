"""Validation functions for AIBlock SDK."""

import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, Union, List
from urllib.parse import urlparse

from aiblock.interfaces import IResult, IErrorInternal
from aiblock.constants import MAX_METADATA_SIZE

# Set up logging
logger = logging.getLogger(__name__)

class ValidationErrorType(Enum):
    """Validation error types."""
    INVALID_TYPE = "Invalid type provided"
    NOT_SERIALIZABLE = "Value is not JSON serializable"
    MISSING_REQUIRED = "Missing required field"
    INVALID_FORMAT = "Invalid format"
    INVALID_VALUE = "Invalid value"
    INVALID_URL = "Invalid URL"
    EXCEEDS_SIZE = "Exceeds maximum size"

@dataclass
class ValidationError:
    """Validation error details."""
    error_type: ValidationErrorType
    field: Optional[str] = None
    details: Optional[str] = None

    def __str__(self) -> str:
        msg = f"{self.error_type.value}"
        if self.field:
            msg += f" in field '{self.field}'"
        if self.details:
            msg += f": {self.details}"
        return msg

def validate_metadata(metadata: dict) -> IResult[Dict[str, Any]]:
    """Validate metadata dictionary for item asset creation.
    
    Validates that:
    - Input is a dictionary
    - All values are JSON serializable
    - Total size is within limits
    - Required fields are present (if specified)
    - Field types match expected types
    
    Args:
        metadata (dict): The metadata to validate
        
    Returns:
        IResult: Success with validated metadata or error with details
    """
    try:
        # Validate type
        if not isinstance(metadata, dict):
            error = ValidationError(
                ValidationErrorType.INVALID_TYPE,
                details=f"Expected dict, got {type(metadata).__name__}"
            )
            logger.error(f"Metadata validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
            
        # Ensure all values are JSON serializable
        try:
            serialized = json.dumps(metadata)
            if len(serialized.encode('utf-8')) > MAX_METADATA_SIZE:
                error = ValidationError(
                    ValidationErrorType.EXCEEDS_SIZE,
                    details=f"Metadata size exceeds maximum of {MAX_METADATA_SIZE} bytes"
                )
                logger.error(f"Metadata validation failed: {error}")
                return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
        except (TypeError, ValueError) as e:
            error = ValidationError(
                ValidationErrorType.NOT_SERIALIZABLE,
                details=str(e)
            )
            logger.error(f"Metadata validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
            
        # Optional: Validate required fields if specified
        required_fields = metadata.get('_required_fields', [])
        if required_fields:
            missing = [f for f in required_fields if f not in metadata]
            if missing:
                error = ValidationError(
                    ValidationErrorType.MISSING_REQUIRED,
                    details=f"Missing fields: {', '.join(missing)}"
                )
                logger.error(f"Metadata validation failed: {error}")
                return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
        
        logger.debug("Metadata validation successful")
        return IResult.ok(metadata)
        
    except Exception as e:
        logger.error(f"Unexpected error in metadata validation: {str(e)}")
        return IResult.err(IErrorInternal.InvalidParametersProvided, str(e))

def validate_url(url: str) -> IResult[str]:
    """Validate a URL string.
    
    Validates that:
    - URL has a valid scheme (http/https)
    - URL has a valid netloc (domain)
    - URL format is valid
    
    Args:
        url (str): The URL to validate
        
    Returns:
        IResult: Success with validated URL or error with details
    """
    try:
        if not isinstance(url, str):
            error = ValidationError(
                ValidationErrorType.INVALID_TYPE,
                details=f"Expected str, got {type(url).__name__}"
            )
            logger.error(f"URL validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        # Parse URL
        parsed = urlparse(url)
        
        # Validate scheme
        if not parsed.scheme or parsed.scheme not in ('http', 'https'):
            error = ValidationError(
                ValidationErrorType.INVALID_URL,
                details="Invalid or missing scheme (must be http/https)"
            )
            logger.error(f"URL validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        # Validate netloc
        if not parsed.netloc:
            error = ValidationError(
                ValidationErrorType.INVALID_URL,
                details="Missing domain"
            )
            logger.error(f"URL validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        # Optional: Validate format with regex
        url_pattern = r'^https?:\/\/[^\s\/$.?#].[^\s]*$'
        if not re.match(url_pattern, url):
            error = ValidationError(
                ValidationErrorType.INVALID_FORMAT,
                details="Invalid URL format"
            )
            logger.error(f"URL validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        logger.debug(f"URL validation successful: {url}")
        return IResult.ok(url)
        
    except Exception as e:
        logger.error(f"Unexpected error in URL validation: {str(e)}")
        return IResult.err(IErrorInternal.InvalidParametersProvided)

def validate_numeric_range(
    value: Union[int, float],
    min_value: Optional[Union[int, float]] = None,
    max_value: Optional[Union[int, float]] = None
) -> IResult[Union[int, float]]:
    """Validate a numeric value within an optional range.
    
    Args:
        value: The numeric value to validate
        min_value: Optional minimum value (inclusive)
        max_value: Optional maximum value (inclusive)
        
    Returns:
        IResult: Success with validated value or error with details
    """
    try:
        if not isinstance(value, (int, float)):
            error = ValidationError(
                ValidationErrorType.INVALID_TYPE,
                details=f"Expected number, got {type(value).__name__}"
            )
            logger.error(f"Numeric validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        if min_value is not None and value < min_value:
            error = ValidationError(
                ValidationErrorType.INVALID_VALUE,
                details=f"Value {value} is less than minimum {min_value}"
            )
            logger.error(f"Numeric validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        if max_value is not None and value > max_value:
            error = ValidationError(
                ValidationErrorType.INVALID_VALUE,
                details=f"Value {value} is greater than maximum {max_value}"
            )
            logger.error(f"Numeric validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        logger.debug(f"Numeric validation successful: {value}")
        return IResult.ok(value)
        
    except Exception as e:
        logger.error(f"Unexpected error in numeric validation: {str(e)}")
        return IResult.err(IErrorInternal.InvalidParametersProvided)

def validate_transaction_fields(tx: Dict[str, Any]) -> IResult[Dict[str, Any]]:
    """Validate transaction fields.
    
    Args:
        tx (Dict[str, Any]): Transaction to validate
        
    Returns:
        IResult: Success with validated transaction or error with details
    """
    required_fields = ['sender', 'receiver', 'amount', 'fee', 'nonce', 'timestamp']
    
    # Check required fields
    missing = [f for f in required_fields if f not in tx]
    if missing:
        error = ValidationError(
            ValidationErrorType.MISSING_REQUIRED,
            details=f"Missing required fields: {', '.join(missing)}"
        )
        logger.error(f"Transaction validation failed: {error}")
        return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
        
    # Validate field types
    type_checks = {
        'sender': str,
        'receiver': str,
        'amount': (int, float),
        'fee': (int, float),
        'nonce': int,
        'timestamp': int
    }
    
    for field, expected_type in type_checks.items():
        if not isinstance(tx[field], expected_type):
            error = ValidationError(
                ValidationErrorType.INVALID_TYPE,
                field=field,
                details=f"Expected {expected_type.__name__}, got {type(tx[field]).__name__}"
            )
            logger.error(f"Transaction validation failed: {error}")
            return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
            
    # Validate numeric ranges
    if tx['amount'] <= 0:
        error = ValidationError(
            ValidationErrorType.INVALID_VALUE,
            field='amount',
            details="Amount must be positive"
        )
        logger.error(f"Transaction validation failed: {error}")
        return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
        
    if tx['fee'] < 0:
        error = ValidationError(
            ValidationErrorType.INVALID_VALUE,
            field='fee',
            details="Fee cannot be negative"
        )
        logger.error(f"Transaction validation failed: {error}")
        return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
        
    if tx['nonce'] < 0:
        error = ValidationError(
            ValidationErrorType.INVALID_VALUE,
            field='nonce',
            details="Nonce cannot be negative"
        )
        logger.error(f"Transaction validation failed: {error}")
        return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
        
    # Validate timestamp is not in future
    current_time = int(time.time())
    if tx['timestamp'] > current_time + 300:  # Allow 5 minutes future drift
        error = ValidationError(
            ValidationErrorType.INVALID_VALUE,
            field='timestamp',
            details="Timestamp too far in future"
        )
        logger.error(f"Transaction validation failed: {error}")
        return IResult.err(IErrorInternal.InvalidParametersProvided, str(error))
        
    return IResult.ok(tx)

def validate_transaction(tx: Dict[str, Any]) -> IResult[Dict[str, Any]]:
    """Validate a transaction.
    
    Args:
        tx (Dict[str, Any]): Transaction to validate
        
    Returns:
        IResult: Success with validated transaction or error with details
    """
    # First validate the transaction fields
    fields_result = validate_transaction_fields(tx)
    if fields_result.is_err:
        return fields_result
        
    # Additional transaction-specific validation could go here
    
    return IResult.ok(tx) 