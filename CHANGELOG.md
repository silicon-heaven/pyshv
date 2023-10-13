# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
pySHV now conforms with work in progress SHV standard 3.0!

### Added
- `SimpleClient.ls_has_child` to query if child node exists
- `SimpleClient.dir_description` to get description of a single method

### Changed
- `RpcMessage` API to now use proprties instead of methods
- Removed unused argument `login_options` for `SimpleClient.connect`
- `SimpleClient.dir_details` is now `SimpleClient.dir` and old `dir`
  implementation is removed
- Broker configuration now no longer contains `rules` sections and instead we
  specify `methods` in `roles` sections. Methods are combination of path and
  method that is used to identify methods this role is applied to.
- Broker now allows all users browse access to the `.app` and read access to the
  `.app/broker/currentClient`.
- Received invalid messages are now skipped instead of raising exception.

### Removed
- `SimpleClient.ls_with_children` as that is now invalid with SHV 3.0


## [0.3.0] - 2023-09-19
### Added
- `ValueClient.wait_for_change` that blocks task until value change is detected.
- `ValueClient.prop_change_wait` that simplifies a common operation of waiting
  for a new value.
- `ValueClient.get_snapshot` is now able to snapshot multiple paths or
  subscribed paths if no path is given.
- `ValueClient.clean_cache` method to remove old entried for no longer
  subscribed paths.
- `ValueClient.prop_get` now supports `max_age` parameter
- Support for UDP/IP protocol
- Initial support for Serial protocol
- Ability to reset the client connection (`RpcClient.reset`)

### Changed
- URL now uses field `location` instead of `host` as it is more descriptive
  considering the usage.
- Login is now allowed for local socket because it can be used to elevate access
  rights of some clients without need to have multiple sockets.
- `ValueClient` now caches new value for subscribed paths when `prop_get` is
  used and optionally right on `prop_set`.
- `ValueClient.unsubscribe` now calls `ValueClient.clean_cache` on successful
  unsubscribe (this can be suppressed with argument).
- `create_rpc_server` returns `RpcServer` instead of `asyncio.Server`

### Fixed
- Running pyshvbroker as a standalone application not working
- Packing of `Decimal` in ChainPack that in some cases packed invalid value
- Unpacking of strings in Cpon that mangled UTF-8 encoding.
- Packing of `str` in Cpon that invalidly escaped some characters.
- `ValueClient.get_snapshot` no longer fails when node is not implementing `ls`
  method.
- `ValueClient.is_subscribed` now correctly matches only paths for subscribed
  nodes and its children instead of just generic string prefix.
- `ValueClient.prop_get` reports value change only when it really happened.
- `ValueClient.prop_change_wait` implementation
- `RpcUrl` uses local user's name instead of empty string
- Handling of idle ping for `SimpleClient` when used only to listen
- `pycp2cp` invocation with file


## [0.2.0] - 2023-06-16
### Added
- `SimpleClient` that provides simple API to connect to the broker and perform
  calls as well as to handle requests and signals
- `RpcError` that represents SHV RPC errors
- `SHVMeta` and variation on SHV types based on it with companion functions to
  manage these custom extended types
- Small broker implemented purely in Python

### Changed
- `RpcMessage.ErrorCode` moved and renamed to `RpcErrorCode`
- `RpcClient.read_rpc_message` now raises `RpcError` instead of
  `RpcClient.MethodCallError`
-  `ChainPackWriter`, `ChainPackReader`, `CponWriter` and `CponReader` now
   require `io.BytesIO` instead of `UnpackContext` and `PackContext`
- `RpcMessage` has now attribute `value` instead of `rpcValue` (this is
  intentional break to force users to review their code due to the type change)
- `RpcClient` methods for sending and receiving RPC messages were replaced with
  `send` and `receive` methods.
- `rpcclient.get_next_rpc_request_id` was moved to `RpcMessage.next_request_id`

### Removed
- `ClinetConnection`, please use `SimpleClient` or `ValueClient` instead
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
