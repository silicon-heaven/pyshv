# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- `RpcError` that represents SHV RPC errors
- `SHVMeta` and variation on SHV types based on it with companion functions to
  mange these custom extended types

### Changed
- `RpcMessage.ErrorCode` moved and renamed to `RpcErrorCode`
- `RpcClient.read_rpc_message` now raises `RpcError` instead of
  `RpcClient.MethodCallError`
-  `ChainPackWriter`, `ChainPackReader`, `CponWriter` and `CponReader` now
   require `io.BytesIO` instead of `UnpackContext` and `PackContext`
- `RpcMessage` has now attribute `value` instead of `rpcValue` (this is
  intentional break to force users to review their code due to the type change)
- `rpcclient.get_next_rpc_request_id` was moved to `RpcClient.next_request_id`

### Removed
- `RpcClient.LoginType.NONE` as login needs to be always performed even when any
  authentication is accepted to actually pass options
- `RpcValue` and instead native types or `SHVMeta` based types are used
- `cpcontext` and `ctx` attributes of `ChainPackWriter`, `ChainPackReader`,
  `CponWriter` and `CponReader`
- `ChainPack.is_little_endian` as it can be easilly done directly


## [0.1.1] - 2023-05-22
### Fixed
- Handler lookup in `ClientConnection` now correctly selects longest match
  rather than shortest


## [0.1.0] - 2023-04-10
### Added
- The original implementation under name `libshv-py`
- Methods `shverror` and `set_shverror` to `RpcMessage` with an appropriate SHV
  error format
- `RpcServer` that listens for new client connections
- `RpcClient.disconnect` method to disconnect the connection

### Changed
- Top-level package `chainpack` renamed to `shv`
- `RpcValue` now explicitly converts Python representation to its internal one
  and also back
- Tags and Keys in `RpcMessage` are now in Enum instead of being constants
- `RpcClient`'s method `connect` is now class method that creates new instance
- `RpcClient` now has to he initialized with writter and reader
- `RpcClient.LoginType` are now capitalized to match Python paradigm
- `RpcClient.State` is removed

### Fixed
- Terminate loop of `RpcClient` on EOF
- Packing of empty string
