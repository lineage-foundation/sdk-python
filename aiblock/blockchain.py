"""Client for interacting with the AIBlock blockchain."""

from __future__ import annotations

import requests
import logging
from typing import TypedDict, Literal, Optional, Dict, Any
from enum import Enum
import uuid
import random
from urllib.parse import urlparse
from aiblock.interfaces import IResult, IErrorInternal
from importlib import metadata as _importlib_metadata
import json

# Set up logging
logger = logging.getLogger(__name__)

# Type definitions
ResponseStatus = Literal['success', 'error', 'pending', 'unknown']

class ResponseContent(TypedDict, total=False):
    """Content type for API responses."""
    block_num: int
    block_hash: str
    timestamp: int
    transactions: list
    previous_hash: str
    total_supply: str
    issued_supply: str

class APIResponse(TypedDict):
    """Standard API response type."""
    id: str
    status: ResponseStatus
    reason: str
    content: Optional[ResponseContent]

def get_random_string(length: int) -> str:
    """Generate a random string of specified length."""
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choice(chars) for _ in range(length))

def get_headers(cache_id: Optional[str] = None) -> Dict[str, str]:
    """Get headers for API requests."""
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Request-ID': str(uuid.uuid4()),
        'Nonce': get_random_string(32)
    }
    
    if cache_id:
        headers['x-cache-id'] = cache_id
    
    return headers

def create_response(
    status: ResponseStatus,
    reason: str,
    content: Optional[ResponseContent] = None
) -> APIResponse:
    """Create a standardized API response."""
    return {
        'id': str(uuid.uuid4()),
        'status': status,
        'reason': reason,
        'content': content
    }

def handle_response(response) -> IResult[APIResponse]:
    """Handle API response and return standardized format.

    Args:
        response: The response object from the API request.

    Returns:
        IResult[APIResponse]: A result containing:
            - id (str): A unique identifier for the response
            - status (str): The status of the response (Success, error, pending, unknown)
            - reason (str): A human-readable message explaining the status
            - content (dict, optional): The response content for successful requests
    """
    # Generate a unique ID for this response
    response_id = str(uuid.uuid4())

    # Extract the endpoint from the URL
    path = urlparse(str(response.url)).path.strip('/')
    endpoint = path.split('/')[0] if path else ''

    # Define success messages for different endpoints
    success_messages = {
        'latest_block': 'Latest block retrieved successfully',
        'block': 'Block retrieved successfully',
        'block_by_num': 'Block retrieved successfully',
        'blockchain': 'Blockchain entry retrieved successfully',
        'blockchain_entry': 'Blockchain entry retrieved successfully',
        'total_supply': 'Total supply retrieved successfully',
        'issued_supply': 'Issued supply retrieved successfully'
    }

    try:
        if response.status_code == 200:
            try:
                content = response.json()
                return IResult.ok({
                    'id': response_id,
                    'status': 'success',
                    'reason': success_messages.get(endpoint, 'Operation completed successfully'),
                    'content': content.get('content', content)
                })
            except ValueError:
                return IResult.err(IErrorInternal.InvalidParametersProvided, 'Invalid JSON response')
        elif response.status_code == 400:
            return IResult.err(IErrorInternal.BadRequest, response.text or 'Bad request')
        elif response.status_code == 401:
            return IResult.err(IErrorInternal.Unauthorized, response.text or 'Unauthorized')
        elif response.status_code == 403:
            return IResult.err(IErrorInternal.Forbidden, response.text or 'Forbidden')
        elif response.status_code == 404:
            return IResult.err(IErrorInternal.NotFound, response.text or 'Resource not found')
        elif response.status_code == 405:
            return IResult.err(IErrorInternal.BadRequest, response.text or 'Method not allowed')
        elif response.status_code == 202:
            return IResult.err(IErrorInternal.InvalidParametersProvided, response.text or 'Request is being processed')
        elif response.status_code == 500:
            return IResult.err(IErrorInternal.InternalServerError, response.text or 'Internal server error')
        elif response.status_code == 503:
            return IResult.err(IErrorInternal.ServiceUnavailable, response.text or 'Service unavailable')
        elif response.status_code == 504:
            return IResult.err(IErrorInternal.GatewayTimeout, response.text or 'Gateway timeout')
        elif response.status_code >= 500:
            return IResult.err(IErrorInternal.InternalServerError, f'Server error: {response.text}')
        else:
            return IResult.err(IErrorInternal.UnknownError, f'Unknown error: {response.text}')
    except requests.exceptions.ConnectionError:
        return IResult.err(IErrorInternal.NetworkError, 'Network error occurred')
    except Exception as e:
        return IResult.err(IErrorInternal.InternalError, f'Error processing response: {str(e)}')

class BlockchainClient:
    """Client for interacting with the AIBlock blockchain."""
    
    def __init__(self, storage_host: str, mempool_host: Optional[str] = None) -> None:
        """Initialize the blockchain client.
        
        Args:
            storage_host: URL of the storage node
            mempool_host: Optional URL of the mempool node
            
        Raises:
            ValueError: If storage_host is None
        """
        if storage_host is None:
            raise ValueError("storage_host cannot be None")
        self.storage_host = storage_host
        self.mempool_host = mempool_host

    def _validate_storage_host(self) -> None:
        """Validate storage_host."""
        if self.storage_host is None:
            raise ValueError("storage_host cannot be None")

    def _make_request(self, endpoint: str, method: str = 'GET', data: Any = None) -> IResult[APIResponse]:
        """
        Make an HTTP request to the appropriate host.
        
        Args:
            endpoint: The API endpoint to call
            method: HTTP method ('GET' or 'POST')
            data: Data to send with POST requests
            
        Returns:
            IResult containing the API response or error
        """
        try:
            # Determine which host to use based on endpoint
            if endpoint.startswith(('total_supply', 'issued_supply', 'fetch_balance', 'create_item_asset', 'create_transactions')):
                if not self.mempool_host:
                    return IResult.err(IErrorInternal.NetworkNotInitialized, "Mempool host is required for this endpoint")
                url = f"{self.mempool_host}/{endpoint}"
            else:
                if not self.storage_host:
                    return IResult.err(IErrorInternal.NetworkNotInitialized, "Storage host is required for this endpoint")
                url = f"{self.storage_host}/{endpoint}"

            # Prepare headers using shared generator
            headers = get_headers()
            headers['User-Agent'] = f"AIBlock-Python-SDK/{self._get_version()}"

            # Make the request
            if method.upper() == 'POST':
                if data is not None:
                    payload = json.dumps(data)
                    response = requests.request('POST', url, headers=headers, data=payload, timeout=30)
                else:
                    response = requests.post(url, headers=headers, timeout=30)
            else:
                response = requests.get(url, headers=headers, timeout=30)

            # Delegate response handling to shared handler
            return handle_response(response)

        except requests.exceptions.Timeout:
            return IResult.err(IErrorInternal.NetworkError, "Request timeout")
        except requests.exceptions.ConnectionError:
            return IResult.err(IErrorInternal.NetworkError, "Connection error")
        except requests.exceptions.RequestException as e:
            return IResult.err(IErrorInternal.NetworkError, f"Request failed: {str(e)}")
        except Exception as e:
            return IResult.err(IErrorInternal.UnknownError, f"Unexpected error: {str(e)}")

    def get_latest_block(self) -> IResult[APIResponse]:
        """Get the latest block from the blockchain."""
        return self._make_request('latest_block')

    def get_block_by_num(self, block_num: int) -> IResult[APIResponse]:
        """
        Get a specific block by its number.
        Uses the block_by_num endpoint with POST request containing array of block numbers.
        This matches the JavaScript SDK implementation pattern.
        
        Args:
            block_num: The block number to retrieve
            
        Returns:
            IResult containing the block data or error
        """
        # Validate input
        if not isinstance(block_num, int) or block_num < 0:
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Block number must be a non-negative integer")
        
        # Use block_by_num endpoint with POST request containing array of block numbers
        # This matches the JavaScript SDK implementation and the curl example
        return self._make_request('block_by_num', method='POST', data=[block_num])

    def get_blockchain_entry(self, block_hash: str) -> IResult[APIResponse]:
        """
        Get blockchain entry by hash using blockchain_entry endpoint.
        
        Args:
            block_hash: The block hash to look up
            
        Returns:
            IResult containing the blockchain entry data or error
        """
        # Use blockchain_entry endpoint with POST request containing array of hashes
        # This matches the JavaScript SDK implementation pattern
        return self._make_request('blockchain_entry', method='POST', data=[block_hash])

    def get_total_supply(self) -> IResult[APIResponse]:
        """Get the total supply of tokens.

        Returns:
            IResult[APIResponse]: A result containing the total supply information.
        """
        return self._make_request('total_supply')

    def get_issued_supply(self) -> IResult[APIResponse]:
        """Get the issued supply of tokens.

        Returns:
            IResult[APIResponse]: A result containing the issued supply information.
        """
        return self._make_request('issued_supply')

    def get_transaction_by_hash(self, tx_hash: str) -> IResult[APIResponse]:
        """
        Get transaction by hash using blockchain_entry endpoint.
        This matches the JavaScript SDK's approach where transactions are fetched
        using the blockchain_entry endpoint with an array of hashes.
        
        Args:
            tx_hash: The transaction hash to look up
            
        Returns:
            IResult containing the transaction data or error
        """
        # Validate input
        if not tx_hash or not isinstance(tx_hash, str):
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Transaction hash must be a non-empty string")
        
        # Use blockchain_entry endpoint with POST request containing array of hashes
        # This matches the JavaScript SDK implementation
        return self._make_request('blockchain_entry', method='POST', data=[tx_hash])
    
    def fetch_transactions(self, transaction_hashes: list[str]) -> IResult[APIResponse]:
        """
        Fetch multiple transactions by their hashes using blockchain_entry endpoint.
        This method matches the JavaScript SDK's fetchTransactions implementation.
        
        Args:
            transaction_hashes: List of transaction hashes to fetch
            
        Returns:
            IResult containing the transactions data or error
        """
        # Validate input
        if not transaction_hashes:
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Transaction hashes list cannot be empty")
        
        if not isinstance(transaction_hashes, list):
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Transaction hashes must be a list")
        
        # Validate each hash
        for tx_hash in transaction_hashes:
            if not tx_hash or not isinstance(tx_hash, str):
                return IResult.err(IErrorInternal.InvalidParametersProvided, "All transaction hashes must be non-empty strings")
        
        # Use blockchain_entry endpoint with POST request containing array of hashes
        # This exactly matches the JavaScript SDK implementation
        return self._make_request('blockchain_entry', method='POST', data=transaction_hashes)

    def _get_version(self) -> str:
        """Get the SDK version from installed metadata, fallback to project version."""
        try:
            return _importlib_metadata.version('aiblock')
        except Exception:
            return "0.2.8"
    
    def _get_random_string(self, length: int) -> str:
        """Generate a random string of specified length."""
        import random
        import string
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))