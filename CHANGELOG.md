# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-06

### Fixed

- Generator modules are registered in `sys.modules` while executing, so
  ordinary Python such as `@dataclass` works inside generators.
- Generator source is compiled from bytes, honoring PEP 263 encoding cookies
  and a UTF-8 BOM.
- A generator's directory is prepended to `sys.path` during execution, so
  sibling imports (`from helper import ...`) work; sibling modules are evicted
  from `sys.modules` afterwards so generators never share same-named siblings.
- Import-time generator failures and filesystem write errors are reported as
  one-line `ERROR`s instead of tracebacks.
- Glob character classes such as `[a-z]` keep their range meaning; previously
  files matched by the glob could be silently skipped with exit 0.
- Existing targets are classified before their generator runs: dirty/unmanaged
  refusals are reported even when the generator would fail, and the state is
  re-checked immediately before each write so a target that changed mid-run is
  refused rather than overwritten.
- Existing non-UTF-8 targets are treated as unmanaged instead of crashing.
- Custom `--header` templates are validated before any generator executes, and
  all template rendering errors are reported as `ERROR`s.
- Rewriting an existing output preserves its file permissions (e.g. executable
  bits); new outputs get normal umask-based permissions instead of `0600`.
- Captures of `""`, `.`, and `..` are rejected, and a mapping whose output
  resolves onto its own generator file is a hard error (previously
  `--overwrite --output '{}.py' '{}.py'` could destroy the generator).

### Changed

- **Breaking:** the header token is now `BodyHash<<algorithm:hash>>` (e.g.
  `BodyHash<<sha256:4660ab1ff310887b>>`), replacing `SignedHash<<hash>>`. The
  old name implied a cryptographic signature the mechanism never had, and the
  token now names its hash algorithm, so the algorithm can evolve without
  another format break: evergen writes SHA-256 and verifies with whatever
  `hashlib` algorithm the token names. Outputs written by 0.1.0 read as
  unmanaged — rerun evergen once with `--overwrite` to migrate them.
- README restructured around adoption: problem statement, PyPI-first quick
  start, positioning vs alternatives, install/requirements section, badges,
  FAQ, and honest scoping of the safety promise (unauthenticated
  accidental-edit guard; `--check` executes generator code; atomicity covers
  process crashes, not power loss; symlinked outputs are resolved).
- CI/publish workflows pin actions to commit SHAs, test Python 3.10/3.13/3.14,
  verify the pushed tag matches `pyproject.toml`'s version before publishing,
  and smoke-test the built wheel.
- The sdist file list is an explicit allowlist, so untracked worktree files can
  no longer leak into source distributions.
- Release checklist requires a clean worktree, a fresh `dist/` build, and
  `twine check` before tagging.

## [0.1.0] - 2026-07-06

### Added

- GitHub Actions release workflow that builds and publishes tagged releases to
  PyPI via Trusted Publishing.
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

### Changed

- Updated GitHub Actions dependencies to current Node.js 24-compatible major
  versions.

[Unreleased]: https://github.com/Elijas/evergen/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Elijas/evergen/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Elijas/evergen/releases/tag/v0.1.0
