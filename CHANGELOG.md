# Changelog

## 0.2.9

- Consistent network error handling across `BlockchainClient` and `Wallet` (IResult everywhere)
- `Wallet.get_balance` now returns `IResult[dict]` (breaking)
- Unified headers and response handling via shared helpers
- Added `NetworkNotInitialized` error
- Docs updated for IResult usage and error mappings
- CI: added test job and publish-on-main with PyPI token
- Config: standardized environment variables to `AIBLOCK_*` (`AIBLOCK_MEMPOOL_HOST`, `AIBLOCK_STORAGE_HOST`, `AIBLOCK_PASSPHRASE`, optional `AIBLOCK_VALENCE_HOST`)

## 0.2.8

- Docs refresh and minor fixes

