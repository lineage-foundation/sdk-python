"""Client for interacting with the Lineage blockchain."""

from __future__ import annotations

import requests
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from lineage.interfaces import IResult, IErrorInternal
from importlib import metadata as _importlib_metadata
import json
import random

# Set up logging
logger = logging.getLogger(__name__)

def get_random_string(length: int) -> str:
    """Generate a random string of specified length."""
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choice(chars) for _ in range(length))

def get_headers(api_key: Optional[str] = None) -> Dict[str, str]:
    """Get headers for API requests.

    Args:
        api_key: Optional API key to send as the `x-api-key` header.

    Returns:
        Dict[str, str]: Headers to send with every request.
    """
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    if api_key:
        headers['x-api-key'] = api_key

    return headers

def _extract_problem_detail(response) -> str:
    """Extract a human-readable message from an `application/problem+json` body.

    Falls back to the raw response text when the body isn't JSON or doesn't
    carry a `detail`/`title` field.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text or ''

    if isinstance(body, dict):
        return body.get('detail') or body.get('title') or response.text or ''

    return response.text or ''

def handle_response(response) -> IResult[Any]:
    """Handle a `/v1` API response.

    On success (any 2xx other than 202) the parsed JSON body is returned
    as-is - `/v1/items` and `/v1/transactions` reply `201`, while reads
    reply `200`. `202` keeps its existing "still processing" semantics and
    is treated as a (non-fatal) pending result, not a plain success. On
    failure the response is expected to carry an `application/problem+json`
    body (`detail`/`title`), which is mapped onto the SDK's internal error
    types.

    Args:
        response: The response object from the API request.

    Returns:
        IResult[Any]: The parsed JSON body on success, or an error result.
    """
    try:
        if 200 <= response.status_code < 300 and response.status_code != 202:
            try:
                return IResult.ok(response.json())
            except ValueError:
                return IResult.err(IErrorInternal.InvalidParametersProvided, 'Invalid JSON response')

        message = _extract_problem_detail(response)

        if response.status_code == 400:
            return IResult.err(IErrorInternal.BadRequest, message or 'Bad request')
        elif response.status_code == 401:
            return IResult.err(IErrorInternal.Unauthorized, message or 'Unauthorized')
        elif response.status_code == 403:
            return IResult.err(IErrorInternal.Forbidden, message or 'Forbidden')
        elif response.status_code == 404:
            return IResult.err(IErrorInternal.NotFound, message or 'Resource not found')
        elif response.status_code == 405:
            return IResult.err(IErrorInternal.BadRequest, message or 'Method not allowed')
        elif response.status_code == 202:
            return IResult.err(IErrorInternal.InvalidParametersProvided, message or 'Request is being processed')
        elif response.status_code == 500:
            return IResult.err(IErrorInternal.InternalServerError, message or 'Internal server error')
        elif response.status_code == 503:
            return IResult.err(IErrorInternal.ServiceUnavailable, message or 'Service unavailable')
        elif response.status_code == 504:
            return IResult.err(IErrorInternal.GatewayTimeout, message or 'Gateway timeout')
        elif response.status_code >= 500:
            return IResult.err(IErrorInternal.InternalServerError, f'Server error: {message}')
        else:
            return IResult.err(IErrorInternal.UnknownError, f'Unknown error: {message}')
    except requests.exceptions.ConnectionError:
        return IResult.err(IErrorInternal.NetworkError, 'Network error occurred')
    except Exception as e:
        return IResult.err(IErrorInternal.InternalError, f'Error processing response: {str(e)}')

class BlockchainClient:
    """Client for interacting with the Lineage blockchain `/v1` REST API."""

    def __init__(self, storage_host: str, mempool_host: Optional[str] = None, api_key: Optional[str] = None) -> None:
        """Initialize the blockchain client.

        Args:
            storage_host: URL of the storage node
            mempool_host: Optional URL of the mempool node
            api_key: Optional API key sent as the `x-api-key` header

        Raises:
            ValueError: If storage_host is None
        """
        if storage_host is None:
            raise ValueError("storage_host cannot be None")
        self.storage_host = storage_host
        self.mempool_host = mempool_host
        self.api_key = api_key

    def _validate_storage_host(self) -> None:
        """Validate storage_host."""
        if self.storage_host is None:
            raise ValueError("storage_host cannot be None")

    def _make_request(self, path: str, method: str = 'GET', data: Any = None, use_mempool: bool = False) -> IResult[Any]:
        """
        Make an HTTP request against the `/v1` API.

        Args:
            path: The `/v1`-relative path to call, e.g. `blocks/latest`
            method: HTTP method ('GET' or 'POST')
            data: Data to send with POST requests
            use_mempool: Whether to route this request at the mempool host (storage host otherwise)

        Returns:
            IResult containing the API response or error
        """
        try:
            if use_mempool:
                if not self.mempool_host:
                    return IResult.err(IErrorInternal.NetworkNotInitialized, "Mempool host is required for this endpoint")
                host = self.mempool_host
            else:
                if not self.storage_host:
                    return IResult.err(IErrorInternal.NetworkNotInitialized, "Storage host is required for this endpoint")
                host = self.storage_host

            url = f"{host}/v1/{path}"

            # Prepare headers using shared generator
            headers = get_headers(self.api_key)
            headers['User-Agent'] = f"Lineage-Python-SDK/{self._get_version()}"

            # Make the request
            if method.upper() == 'POST':
                payload = json.dumps(data) if data is not None else None
                response = requests.request('POST', url, headers=headers, data=payload, timeout=30)
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

    def get_latest_block(self) -> IResult[Any]:
        """Get the latest block from the blockchain.

        Returns:
            IResult containing the latest block, or a not-found error when
            the chain has no blocks yet (the API returns a 404 in that case).
        """
        return self._make_request('blocks/latest')

    def get_block_by_num(self, block_num: int) -> IResult[Any]:
        """
        Get a specific block by its number.

        Args:
            block_num: The block number to retrieve

        Returns:
            IResult containing the block data or error
        """
        # Validate input
        if not isinstance(block_num, int) or block_num < 0:
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Block number must be a non-negative integer")

        return self._make_request(f'blocks?num={block_num}')

    def get_blockchain_entry(self, block_hash: str) -> IResult[Any]:
        """
        Get blockchain entry by hash.

        Args:
            block_hash: The block hash to look up

        Returns:
            IResult containing the blockchain entry data or error
        """
        return self._make_request('blockchain-entries/query', method='POST', data={'keys': [block_hash]})

    def get_total_supply(self) -> IResult[Any]:
        """Get the total supply of tokens.

        Returns:
            IResult[Any]: A result containing `{total, issued}` supply information.
        """
        return self._make_request('supply', use_mempool=True)

    def get_issued_supply(self) -> IResult[Any]:
        """Get the issued supply of tokens.

        Returns:
            IResult[Any]: A result containing `{total, issued}` supply information.
        """
        return self._make_request('supply', use_mempool=True)

    def get_transaction_by_hash(self, tx_hash: str) -> IResult[Any]:
        """
        Get transaction by hash using the blockchain-entries endpoint.

        Args:
            tx_hash: The transaction hash to look up

        Returns:
            IResult containing the transaction data or error
        """
        # Validate input
        if not tx_hash or not isinstance(tx_hash, str):
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Transaction hash must be a non-empty string")

        return self._make_request('blockchain-entries/query', method='POST', data={'keys': [tx_hash]})

    def fetch_transactions(self, transaction_hashes: list[str]) -> IResult[Any]:
        """
        Fetch multiple transactions by their hashes using the blockchain-entries endpoint.

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

        return self._make_request('blockchain-entries/query', method='POST', data={'keys': transaction_hashes})

    def _get_version(self) -> str:
        """Get the SDK version from installed metadata, fallback to project version."""
        try:
            return _importlib_metadata.version('lineage')
        except Exception:
            return "0.2.8"

    def _get_random_string(self, length: int) -> str:
        """Generate a random string of specified length."""
        import random
        import string
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))
