"""Transaction construction and signing primitives, ported from sdk-js.

This module intentionally mirrors sdk-js's `tx.mgmt.ts` / `script.mgmt.ts` /
`key.mgmt.ts` byte-for-byte so that signable-hash preimages and signatures
produced here match sdk-js exactly. See
`fleet/tasks/sdk-python-tx-signing-spec.md` for the full algorithm spec and
golden test vector this was ported against.

Do not "clean up" the JSON field ordering or number handling below without
re-checking the spec - both are load-bearing for byte-for-byte parity.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

import nacl.signing

from lineage import key_handler
from lineage.constants import ADDRESS_VERSION


def get_string_bytes(s: str) -> bytes:
    """UTF-8 encode a string. Mirrors sdk-js's `getStringBytes`."""
    return s.encode('utf-8')


def construct_address(public_key: bytes) -> str:
    """Derive the default (latest) address for a public key.

    Matches sdk-js's `constructAddress(publicKey, ADDRESS_VERSION /* null */)`:
    the address is the raw `sha3_256(public_key)` hex digest - no version
    byte, no checksum, no truncation.

    `key_handler.construct_address` already implements this exact formula
    for its `ADDRESS_VERSION` case (the numeric value differs from sdk-js's
    `null`, but the underlying computation - `hashlib.sha3_256(public_key)
    .hexdigest()` - is identical), so this simply reuses it rather than
    duplicating the crypto.
    """
    result = key_handler.construct_address(public_key, ADDRESS_VERSION)
    return result.get_ok()


def construct_tx_in_signable_asset_hash(asset: Dict[str, Any]) -> str:
    """Hash an asset for tx-input/item-creation signing.

    Preimage is a plain (non-JSON) template string - `Token:<n>` or
    `Item:<n>` - deliberately excluding `genesis_hash`/`metadata` for the
    item case. Matches sdk-js's `constructTxInSignableAssetHash`.
    """
    if 'Token' in asset:
        preimage = f"Token:{asset['Token']}"
    else:
        preimage = f"Item:{asset['Item']['amount']}"
    return hashlib.sha3_256(get_string_bytes(preimage)).hexdigest()


def construct_tx_in_out_signable_hash(
    previous_out: Optional[Dict[str, Any]],
    outputs: List[Dict[str, Any]],
) -> str:
    """Build the per-input signable hash over outputs then previous_out.

    Matches sdk-js's `constructTxInOutSignableHash`: each output is
    independently JSON-serialized (compact, exact field order) and the
    results are concatenated with no delimiter, followed by the
    JSON-serialized `previous_out` (the literal string "null" if there is
    no previous_out), and the whole preimage is sha3_256-hashed.
    """
    signable_tx_outs = ''.join(
        json.dumps(tx_out, separators=(',', ':')) for tx_out in outputs
    )
    signable_tx_in = json.dumps(previous_out, separators=(',', ':'))
    preimage = f"{signable_tx_outs}{signable_tx_in}"
    return hashlib.sha3_256(get_string_bytes(preimage)).hexdigest()


def construct_signature(signable_hex: str, secret_key: bytes) -> str:
    """Sign a signable-hash hex string, returning a hex-encoded signature.

    Matches sdk-js's `constructSignature`: signs the UTF-8 bytes of the
    hex-digest STRING itself, not the raw decoded hash bytes. `secret_key`
    is the 32-byte ed25519 seed, matching this repo's existing
    `IKeypair.secret_key` convention (see `key_handler.create_signature`).
    """
    signing_key = nacl.signing.SigningKey(secret_key)
    signature = signing_key.sign(get_string_bytes(signable_hex)).signature
    return signature.hex()
