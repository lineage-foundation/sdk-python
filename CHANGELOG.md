# Changelog

## 0.2.9

- Consistent network error handling across `BlockchainClient` and `Wallet` (IResult everywhere)
- `Wallet.get_balance` now returns `IResult[dict]` (breaking)
- Unified headers and response handling via shared helpers
- Added `NetworkNotInitialized` error
- Docs updated for IResult usage and error mappings
- CI: added test job and publish-on-main with PyPI token
- Config: standardized environment variables to `LINEAGE_*` (`LINEAGE_MEMPOOL_HOST`, `LINEAGE_STORAGE_HOST`, `LINEAGE_PASSPHRASE`, optional `LINEAGE_VALENCE_HOST`)

## 0.2.8

- Docs refresh and minor fixes

