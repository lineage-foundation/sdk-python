"""Client for a valence mailbox host.

Valence is the plaintext message-relay service two-way payment counterparties
use to exchange DRUID trade offers, acceptances, and rejections. Messages are
sent and stored in plaintext - valence provides delivery and mailbox scoping,
not confidentiality (any local-persistence encryption is the wallet's own,
under its own passphrase key, and is orthogonal to this client).

Every request is authenticated by signing the target mailbox address's raw
UTF-8 bytes (unhashed) with the caller's own keypair - see `_auth_headers`.
This mirrors sdk-go's `ValenceClient`/`valenceAuthHeaders` and sdk-php's
`ValenceClient::authHeaders` byte-for-byte: the signing keypair need not be
the mailbox address's own keypair, since valence messages may be posted into
(or deleted from) a counterparty's mailbox, signed by the sender's own key,
as proof of a validly-held keypair rather than of mailbox ownership.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

import nacl.signing
import requests

from lineage.interfaces import IErrorInternal, IResult
from lineage.blockchain import get_headers as client_get_headers, handle_response as client_handle_response

logger = logging.getLogger(__name__)

# Every mailbox operation (post an offer, read a mailbox, delete a settled
# entry) lives under this single path, matching sdk-js's IAPIRoute.ValenceSet
# / ValenceGet / ValenceDel (all "/messages", DELETE additionally suffixed
# with "/{id}").
MESSAGES_PATH = "/messages"


def _keypair_secret(keypair: Any) -> bytes:
    secret = keypair['secret_key'] if isinstance(keypair, dict) else keypair.secret_key
    return bytes.fromhex(secret) if isinstance(secret, str) else secret


def _keypair_public_hex(keypair: Any) -> str:
    public = keypair['public_key'] if isinstance(keypair, dict) else keypair.public_key
    return public.hex() if isinstance(public, bytes) else public


class ValenceClient:
    """A client for a valence mailbox host.

    Attributes:
        host: The valence host's base URL (no trailing slash expected).
    """

    def __init__(self, host: str) -> None:
        self.host = host

    def _auth_headers(self, address: str, keypair: Any) -> Dict[str, str]:
        """Build the address/public_key/signature headers a valence request
        must carry.

        `address` is the target mailbox's address (hex); `public_key` is the
        caller's own public key (hex); `signature` is
        `hex(ed25519.sign(secret_key, address.encode()))` - a detached
        signature over the mailbox address string's raw UTF-8 bytes,
        unhashed. Matches sdk-go's `valenceAuthHeaders` / sdk-php's
        `ValenceClient::authHeaders`.
        """
        signing_key = nacl.signing.SigningKey(_keypair_secret(keypair))
        signature = signing_key.sign(address.encode('utf-8')).signature
        return {
            'address': address,
            'public_key': _keypair_public_hex(keypair),
            'signature': signature.hex(),
        }

    def _request(
        self,
        method: str,
        path: str,
        address: str,
        keypair: Any,
        body: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> IResult[Any]:
        headers = self._auth_headers(address, keypair)
        url = f"{self.host}{path}"

        try:
            if body is not None:
                headers.update(client_get_headers())
                response = requests.request(method, url, json=body, headers=headers, timeout=timeout)
            else:
                response = requests.request(method, url, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            logger.error("Valence %s %s failed: %s", method, path, str(e))
            return IResult.err(IErrorInternal.NetworkError, str(e))

        if 200 <= response.status_code < 300 and response.status_code != 202:
            if not response.content:
                return IResult.ok(None)
            try:
                return IResult.ok(response.json())
            except ValueError:
                return IResult.ok(None)

        return client_handle_response(response)

    def post(self, address: str, keypair: Any, details: Dict[str, Any]) -> IResult[None]:
        """Place (or overwrite) the plaintext offer/status `details` under
        the mailbox identified by `address` (`details["druid"]` is the
        mailbox entry's id), signed by `keypair`.

        Mirrors sdk-go's `ValenceClient.Post` / sdk-php's
        `ValenceClient::post` (`POST /messages`).
        """
        body = {'id': details.get('druid'), 'data': details}
        result = self._request('POST', MESSAGES_PATH, address, keypair, body=body)
        if result.is_err:
            return result
        return IResult.ok(None)

    def get(self, address: str, keypair: Any) -> IResult[Dict[str, Any]]:
        """Return the full contents of `address`'s mailbox: a map of druid
        to the stored details payload directly (not wrapped), signed by
        `keypair`.

        Mirrors sdk-go's `ValenceClient.Get` / sdk-php's
        `ValenceClient::get` (`GET /messages`).
        """
        result = self._request('GET', MESSAGES_PATH, address, keypair)
        if result.is_err:
            return result
        return IResult.ok(result.get_ok() or {})

    def delete(self, druid: str, address: str, keypair: Any) -> IResult[None]:
        """Remove the mailbox entry identified by `druid` from `address`'s
        mailbox, signed by `keypair`.

        Mirrors sdk-go's `ValenceClient.Delete` / sdk-php's
        `ValenceClient::delete` (`DELETE /messages/{id}`).
        """
        path = f"{MESSAGES_PATH}/{quote(druid, safe='')}"
        result = self._request('DELETE', path, address, keypair)
        if result.is_err:
            return result
        return IResult.ok(None)
