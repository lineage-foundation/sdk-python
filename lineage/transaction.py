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
from lineage.constants import ADDRESS_VERSION, TEMP_ADDRESS_VERSION
from lineage.interfaces import IKeypair

# Mirrors sdk-js's `constants.ts: NETWORK_VERSION` - the fixed
# `ICreateTransaction.version` value for the current network.
NETWORK_VERSION = 2

# Mirrors sdk-js's `constants.ts: TEMP_ADDRESS_VERSION` (99999) and
# `ADDRESS_VERSION_OLD` (1) - these are the values that must appear in a
# built transaction's `Pay2PkH.address_version` field, distinct from this
# repo's own internal `lineage.constants` numbering (which `key_handler`
# uses to select which address-derivation formula to run). The "default"
# (current/latest) address version is represented as `None` here, matching
# sdk-js's `null`.
JS_TEMP_ADDRESS_VERSION = 99999


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
    # ensure_ascii=False so non-ASCII (e.g. item metadata) is emitted as raw
    # UTF-8, matching JS JSON.stringify — escaping it as \uXXXX would produce a
    # different preimage and an invalid signature.
    signable_tx_outs = ''.join(
        json.dumps(tx_out, separators=(',', ':'), ensure_ascii=False) for tx_out in outputs
    )
    signable_tx_in = json.dumps(previous_out, separators=(',', ':'), ensure_ascii=False)
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


def get_address_version(public_key: bytes, address: str) -> Optional[int]:
    """Resolve the sdk-js-style address version for a public key/address pair.

    Matches sdk-js's `getAddressVersion(publicKey, address)`: re-derives
    both the temp-version and default-version addresses for `public_key`
    and compares against `address`, returning `JS_TEMP_ADDRESS_VERSION`
    (99999) or `None` (the default/latest version) respectively. Only
    these two are checked, exactly as sdk-js does - the old (v1) address
    structure is not resolved by this lookup.
    """
    temp_address = key_handler.construct_address(public_key, TEMP_ADDRESS_VERSION).get_ok()
    default_address = construct_address(public_key)
    if address == temp_address:
        return JS_TEMP_ADDRESS_VERSION
    if address == default_address:
        return None
    raise ValueError('InvalidAddressVersion')


def _asset_is_token(asset: Dict[str, Any]) -> bool:
    return 'Token' in asset


def _assets_are_compatible(lhs: Dict[str, Any], rhs: Dict[str, Any]) -> bool:
    if _asset_is_token(lhs) and _asset_is_token(rhs):
        return True
    if not _asset_is_token(lhs) and not _asset_is_token(rhs):
        return lhs['Item']['genesis_hash'] == rhs['Item']['genesis_hash']
    return False


def _asset_is_less_than(lhs: Dict[str, Any], rhs: Dict[str, Any]) -> bool:
    if _asset_is_token(lhs) and _asset_is_token(rhs):
        return lhs['Token'] < rhs['Token']
    if (
        not _asset_is_token(lhs)
        and not _asset_is_token(rhs)
        and lhs['Item']['genesis_hash'] == rhs['Item']['genesis_hash']
    ):
        return lhs['Item']['amount'] < rhs['Item']['amount']
    raise ValueError('AssetsIncompatible')


def _asset_is_greater_than(lhs: Dict[str, Any], rhs: Dict[str, Any]) -> bool:
    if _asset_is_token(lhs) and _asset_is_token(rhs):
        return lhs['Token'] > rhs['Token']
    if (
        not _asset_is_token(lhs)
        and not _asset_is_token(rhs)
        and lhs['Item']['genesis_hash'] == rhs['Item']['genesis_hash']
    ):
        return lhs['Item']['amount'] > rhs['Item']['amount']
    raise ValueError('AssetsIncompatible')


def _add_assets(lhs: Dict[str, Any], rhs: Dict[str, Any]) -> Dict[str, Any]:
    """Mirrors sdk-js's `addLhsAssetToRhsAsset`."""
    if _asset_is_token(lhs) and _asset_is_token(rhs):
        return {'Token': lhs['Token'] + rhs['Token']}
    if (
        not _asset_is_token(lhs)
        and not _asset_is_token(rhs)
        and lhs['Item']['genesis_hash'] == rhs['Item']['genesis_hash']
    ):
        return {
            'Item': {
                'amount': lhs['Item']['amount'] + rhs['Item']['amount'],
                'genesis_hash': lhs['Item']['genesis_hash'],
                'metadata': lhs['Item']['metadata'],
            }
        }
    raise ValueError('AssetsIncompatible')


def _sub_assets(lhs: Dict[str, Any], rhs: Dict[str, Any]) -> Dict[str, Any]:
    """Mirrors sdk-js's `subRhsAssetFromLhsAsset`."""
    if _asset_is_token(lhs) and _asset_is_token(rhs) and lhs['Token'] >= rhs['Token']:
        return {'Token': lhs['Token'] - rhs['Token']}
    if (
        not _asset_is_token(lhs)
        and not _asset_is_token(rhs)
        and lhs['Item']['genesis_hash'] == rhs['Item']['genesis_hash']
        and lhs['Item']['amount'] >= rhs['Item']['amount']
    ):
        return {
            'Item': {
                'amount': lhs['Item']['amount'] - rhs['Item']['amount'],
                'genesis_hash': lhs['Item']['genesis_hash'],
                'metadata': None,
            }
        }
    raise ValueError('AssetsIncompatible')


def get_inputs_for_tx(
    payment_asset: Dict[str, Any],
    fetch_balance_response: Dict[str, Any],
    all_keypairs: Dict[str, IKeypair],
) -> Dict[str, Any]:
    """Gather `TxIn` (input) values for a transaction.

    Matches sdk-js's `getInputsForTx`: greedily walks
    `fetch_balance_response['address_list']` in (insertion) order, and
    within each address its UTXO list in array order, accumulating UTXOs
    whose asset is compatible with `payment_asset` until the running total
    is no longer less than `payment_asset`. There is no sorting/selection
    heuristic beyond this - see hazard 9 in the spec.

    Each selected UTXO is signed immediately against a placeholder empty
    outputs list (`construct_tx_in_out_signable_hash(out_point, [])`),
    matching sdk-js exactly; this placeholder is fully overwritten later by
    `update_signatures` once the real outputs are known.

    Returns a dict: `{inputs, total_amount_gathered, used_addresses,
    depleted_addresses}`.
    """
    is_token = _asset_is_token(payment_asset)
    if is_token:
        enough_funds = payment_asset['Token'] <= fetch_balance_response['total']['tokens']
    else:
        genesis_hash = payment_asset['Item']['genesis_hash']
        enough_funds = payment_asset['Item']['amount'] <= (
            fetch_balance_response['total']['items'].get(genesis_hash, 0)
        )
    if not enough_funds:
        raise ValueError('InsufficientFunds')

    if is_token:
        total_amount_gathered: Dict[str, Any] = {'Token': 0}
    else:
        total_amount_gathered = {
            'Item': {
                'amount': 0,
                'genesis_hash': payment_asset['Item'].get('genesis_hash') or '',
                'metadata': payment_asset['Item'].get('metadata') or None,
            }
        }

    used_addresses: List[str] = []
    depleted_addresses: List[str] = []
    inputs: List[Dict[str, Any]] = []

    for address, out_points in fetch_balance_response['address_list'].items():
        keypair = all_keypairs[address]
        used_outpoints_count = 0
        for entry in out_points:
            out_point = entry['out_point']
            value = entry['value']

            if not _asset_is_less_than(total_amount_gathered, payment_asset):
                continue
            if not _assets_are_compatible(payment_asset, value):
                continue

            signable_data = construct_tx_in_out_signable_hash(out_point, [])
            signature = construct_signature(signable_data, keypair.secret_key)
            address_version = get_address_version(keypair.public_key, address)

            inputs.append({
                'previous_out': out_point,
                'script_signature': {
                    'Pay2PkH': {
                        'signable_data': signable_data,
                        'signature': signature,
                        'public_key': keypair.public_key.hex(),
                        'address_version': address_version,
                    }
                },
            })

            total_amount_gathered = _add_assets(value, total_amount_gathered)
            if address not in used_addresses:
                used_addresses.append(address)

            used_outpoints_count += 1
            if len(out_points) == used_outpoints_count:
                depleted_addresses.append(address)

    return {
        'inputs': inputs,
        'total_amount_gathered': total_amount_gathered,
        'used_addresses': used_addresses,
        'depleted_addresses': depleted_addresses,
    }


def create_tx(
    payment_address: str,
    payment_asset: Dict[str, Any],
    excess_address: str,
    druid_info: Optional[Dict[str, Any]],
    tx_ins: Dict[str, Any],
    locktime: int,
) -> Dict[str, Any]:
    """Assemble an `ICreateTransaction` from already-gathered inputs.

    Matches sdk-js's `createTx`: builds a single payment output, and - if
    `tx_ins['total_amount_gathered']` strictly exceeds `payment_asset` -
    appends a change/excess output. The excess output always uses
    `locktime: 0` regardless of `locktime` (hazard 8); `version` is always
    `NETWORK_VERSION`.

    Returns `{create_tx, excess_address_used, used_addresses}`.
    """
    inputs = tx_ins['inputs']
    if len(inputs) == 0:
        raise ValueError('NoInputs')

    outputs: List[Dict[str, Any]] = [
        {
            'value': payment_asset,
            'locktime': locktime,
            'script_public_key': payment_address,
        }
    ]

    total_amount_gathered = tx_ins['total_amount_gathered']
    excess_address_used = _asset_is_greater_than(total_amount_gathered, payment_asset)
    if excess_address_used:
        excess_amount = _sub_assets(total_amount_gathered, payment_asset)
        outputs.append({
            'value': excess_amount,
            'locktime': 0,
            'script_public_key': excess_address,
        })

    create_transaction = {
        'inputs': inputs,
        'outputs': outputs,
        'version': NETWORK_VERSION,
        'druid_info': druid_info,
    }

    return {
        'create_tx': create_transaction,
        'excess_address_used': excess_address_used,
        'used_addresses': tx_ins['used_addresses'],
    }


def _get_address_from_fetch_balance_response(
    fetch_balance_response: Dict[str, Any],
    t_hash: str,
) -> str:
    """Mirrors sdk-js's `getAddressFromFetchBalanceResponse`."""
    for address, out_points in fetch_balance_response['address_list'].items():
        if any(entry['out_point']['t_hash'] == t_hash for entry in out_points):
            return address
    raise ValueError('UnableToGetKeypair')


def update_signatures(
    transaction: Dict[str, Any],
    fetch_balance_response: Dict[str, Any],
    all_keypairs: Dict[str, IKeypair],
) -> Dict[str, Any]:
    """Re-sign every input against the transaction's final outputs.

    Matches sdk-js's `updateSignatures`: for each input, recomputes
    `signable_data` via `construct_tx_in_out_signable_hash` over the
    FINAL `transaction['create_tx']['outputs']` (not the empty placeholder
    used by `get_inputs_for_tx`), re-signs it, and overwrites the input's
    `signable_data`/`signature` in place. Mutates and returns `transaction`.
    """
    create_transaction = transaction['create_tx']
    outputs = create_transaction['outputs']

    for tx_in in create_transaction['inputs']:
        script_signature = tx_in.get('script_signature')
        previous_out = tx_in.get('previous_out')
        if not script_signature or not previous_out:
            continue

        address = _get_address_from_fetch_balance_response(
            fetch_balance_response, previous_out['t_hash']
        )
        keypair = all_keypairs[address]

        signable_data = construct_tx_in_out_signable_hash(previous_out, outputs)
        signature = construct_signature(signable_data, keypair.secret_key)

        script_signature['Pay2PkH']['signable_data'] = signable_data
        script_signature['Pay2PkH']['signature'] = signature

    return transaction


def create_payment_tx(
    payment_address: str,
    payment_asset: Dict[str, Any],
    excess_address: str,
    fetch_balance_response: Dict[str, Any],
    all_keypairs: Dict[str, IKeypair],
    locktime: int,
) -> Dict[str, Any]:
    """Top-level entry point for a plain (non-2-way) payment transaction.

    Matches sdk-js's `createPaymentTx`: gathers inputs, assembles the
    transaction (with `druid_info` always `None` for plain payments), then
    re-signs every input against the final outputs. Returns the mutated
    `{create_tx, excess_address_used, used_addresses}` dict from `create_tx`.
    """
    tx_ins = get_inputs_for_tx(payment_asset, fetch_balance_response, all_keypairs)
    transaction = create_tx(
        payment_address, payment_asset, excess_address, None, tx_ins, locktime
    )
    return update_signatures(transaction, fetch_balance_response, all_keypairs)
