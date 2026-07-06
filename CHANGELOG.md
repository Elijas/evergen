# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- GitHub Actions release workflow that builds and publishes tagged releases to
  PyPI via Trusted Publishing.

## [0.1.0] - 2026-07-06

### Added

- `evergen` CLI: maps generator files to output files via `{}` glob patterns
  and executes each generator's `gen() -> str`.
- Signed headers with three-state detection: clean (regenerate), stale
  (regenerate), and hand-edited (refuse unless `--overwrite`).
- `--check` mode: verifies outputs are present and current without writing,
  for CI enforcement.
- `--header` template customization for comment syntaxes beyond `#`.
- Atomic output writes (temp file + `os.replace`), so interrupted runs never
  leave truncated files.
- Zero runtime dependencies; supports Python 3.10–3.13.

[Unreleased]: https://github.com/Elijas/evergen/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Elijas/evergen/releases/tag/v0.1.0
