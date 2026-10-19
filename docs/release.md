# Release

A release is a version tag pushed from `main`: `.github/workflows/release.yml` runs the checks,
builds, and publishes to PyPI (trusted publishing). The version comes from the tag
(setuptools-scm), nothing to bump in the code.

## 1. Changelog

Check that `CHANGELOG.md` covers what changed since the last tag (`git log <last-tag>..main`), and
that its top section is the version about to be tagged. If not, update it first.

Keep it brief and high level: what changed for someone using ripple-effect, not how. Its readers are
experienced developers (testing upstream/downstream projects means juggling several of them), so no
TL;DR, no implementation details, no list of internal refactors. Breaking changes must be there.

## 2. Tag

From a clean, up-to-date `main` whose CI is green:

```bash
git tag v1.1.0          # lightweight tag, semver
git push origin v1.1.0
```

Tags go on `main` only, never on a branch.
