# Releasing

Releases publish to PyPI from GitHub Actions using PyPI Trusted Publishing.
No PyPI password or API token is stored in the repository.

PyPI must have a pending or active Trusted Publisher with:

- Project: `evergen`
- Owner: `Elijas`
- Repository: `evergen`
- Workflow: `publish.yml`
- Environment: `pypi`

The GitHub repository should also have a `pypi` environment. Configure required
reviewers there if releases should need manual approval after a tag is pushed.

## Checklist

1. [ ] Ensure `main` is green in CI.
2. [ ] Bump `version` in `pyproject.toml`.
3. [ ] Move `[Unreleased]` items in `CHANGELOG.md` to a new dated version
       section and update the link references at the bottom.
4. [ ] Commit: `git commit -am "release: vX.Y.Z"` and push; wait for CI.
5. [ ] Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
6. [ ] Watch the `Publish` workflow. It runs tests, lint, `uv build`, then
       publishes the built distributions to PyPI using GitHub OIDC.
7. [ ] Verify the published package: `uvx evergen@X.Y.Z --help`.
8. [ ] Create a GitHub release from the tag, pasting the changelog section.

PyPI rejects reused versions. If the publish job fails after PyPI receives a
version, fix forward with a new version instead of retagging the same release.
