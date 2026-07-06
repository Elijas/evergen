# Releasing

Manual checklist for publishing a release to PyPI.

1. [ ] Ensure `main` is green in CI.
2. [ ] Bump `version` in `pyproject.toml`.
3. [ ] Move `[Unreleased]` items in `CHANGELOG.md` to a new dated version
       section and update the link references at the bottom.
4. [ ] Commit: `git commit -am "release: vX.Y.Z"` and push; wait for CI.
5. [ ] Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
6. [ ] Build from a clean tree: `rm -rf dist && uv build`.
7. [ ] Publish: `uv publish` (needs a PyPI token).
8. [ ] Verify the published package: `uvx evergen@X.Y.Z --help`.
9. [ ] Create a GitHub release from the tag, pasting the changelog section.
