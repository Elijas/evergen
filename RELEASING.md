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
2. [ ] Ensure the worktree is clean: `git status --porcelain` must print
       nothing before you build or tag anything.
3. [ ] Bump `version` in `pyproject.toml`, and update `__version__` in
       `src/evergen/__init__.py` to match.
4. [ ] Move `[Unreleased]` items in `CHANGELOG.md` to a new dated version
       section and update the link references at the bottom.
5. [ ] Commit: `git commit -am "release: vX.Y.Z"` and push; wait for CI.
6. [ ] Remove and rebuild `dist/` locally rather than trusting stale
       artifacts: `rm -rf dist && uv build`.
7. [ ] Run `uvx --with twine twine check dist/*` on the freshly built
       sdist and wheel before tagging.
8. [ ] Verify `pyproject.toml`'s `version` matches both the tag you are
       about to push (`vX.Y.Z`) and `__version__` in
       `src/evergen/__init__.py`.
9. [ ] Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
10. [ ] Watch the `Publish` workflow. It first verifies the pushed tag
        matches `pyproject.toml`'s version, then runs tests, lint,
        `uv build`, and publishes the built distributions to PyPI using
        GitHub OIDC.
11. [ ] Verify the published package: `uvx evergen@X.Y.Z --help`.
12. [ ] Verify PyPI artifact hashes after publish match what CI built, e.g.
        compare `sha256sum dist/*` against the hashes shown on
        `https://pypi.org/project/evergen/X.Y.Z/#files`.
13. [ ] Create a GitHub release from the tag, pasting the changelog section.

PyPI rejects reused versions. If the publish job fails after PyPI receives a
version, fix forward with a new version instead of retagging the same release.
