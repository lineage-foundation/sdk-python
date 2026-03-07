import base64
import hashlib
import uuid
import secrets
import logging
from typing import Any, Dict, Optional, Union

from aiblock.interfaces import IErrorInternal, IResult

# Set up logging
logger = logging.getLogger(__name__)

def get_hex_string_bytes(hex_string: str) -> bytes:
    """Convert a hex string to bytes."""
    return bytes.fromhex(hex_string)

def get_hex_string_from_bytes(byte_data: bytes) -> str:
    """Convert bytes to a hex string."""
    return byte_data.hex()

def get_random_bytes(length: int = 32) -> bytes:
    """Generate random bytes of specified length."""
    return secrets.token_bytes(length)

def get_random_string(length: int = 32) -> str:
    """Generate a random string of specified length."""
    return secrets.token_hex(length)

def get_uuid_bytes(uuid_str: Optional[str] = None) -> bytes:
    """Convert a UUID string to bytes, or generate a new UUID if none provided."""
    if uuid_str is None:
        uuid_str = str(uuid.uuid4())
    return uuid.UUID(uuid_str).bytes

def get_uuid_from_bytes(uuid_bytes: bytes) -> str:
    """Convert UUID bytes back to string format."""
    return str(uuid.UUID(bytes=uuid_bytes))

def get_string_bytes(input_str: str) -> bytes:
    """Convert a string to UTF-8 encoded bytes."""
    return input_str.encode('utf-8')

def truncate_by_bytes_utf8(input_str: str, max_bytes: int) -> str:
    """Truncate a string to ensure its UTF-8 encoded form doesn't exceed max_bytes."""
    encoded = input_str.encode('utf-8')
    if len(encoded) <= max_bytes:
        return input_str
    return encoded[:max_bytes].decode('utf-8', errors='ignore')

def cast_api_status(status: Union[str, int]) -> bool:
    """Convert API status to boolean success indicator."""
    if isinstance(status, str):
        return status.lower() == 'success'
    return status == 200

def create_id_and_nonce_headers() -> Dict[str, str]:
    """Create headers with UUID and nonce for API requests."""
    return {
        'id': str(uuid.uuid4()),
        'nonce': get_random_string(32)
    }

def throw_if_err(result: IResult[Any]) -> Any:
    """Throw an error if the result is an error, otherwise return the value."""
    if result.is_err:
        raise Exception(result.error)
    return result.get_ok()

def transform_create_tx_response_from_network(response: Dict[str, Any]) -> IResult[Dict[str, Any]]:
    """Transform and validate network response for transaction or item asset creation.
    
    Args:
        response: The response from the network
        
    Returns:
        IResult containing the transformed response or an error
    """
    if not response or not isinstance(response, dict):
        return IResult.err(IErrorInternal.InvalidParametersProvided)
    
    # Check if the response has a status field
    status = response.get('status')
    if status is None:
        return IResult.err(IErrorInternal.InvalidParametersProvided)
    
    # Convert status to boolean
    is_success = cast_api_status(status)
    
    # If status is False or 'error', return error response
    if not is_success:
        return IResult.err(IErrorInternal.InvalidParametersProvided)
    
    # Return the response as is
    return IResult.ok(response) 