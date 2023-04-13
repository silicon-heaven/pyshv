# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- The original implementation
- Methods `shverror` and `set_shverror` to `RpcMessage` with an appropriate SHV
  error format
- `RpcServer` that listens for new client connections

### Changed
- `RpcValue` now explicitly converts Python representation to its internal one
  and also back
- Tags and Keys in `RpcMessage` are now in Enum instead of being constants

### Fixed
- Terminate loop of `RpcClient` on EOF
- Packing of empty string
