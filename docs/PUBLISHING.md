# Publishing

`lineage-sdk` is published to PyPI automatically when a GitHub Release is
published, via [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC). No API token is stored in the repository.

- Distribution name (what you `pip install`): **`lineage-sdk`**
- Import name (what you `import`): **`lineage`**
- Owner: the `lineage-foundation` PyPI organization
- Version source of truth: `version` in `pyproject.toml` (and reflected via
  `importlib.metadata` at runtime — keep the two in sync by bumping only
  `pyproject.toml`, which package metadata then exposes)

## One-time PyPI setup (per project)

Do this once, before the first release, on the account that owns the
`lineage-foundation` organization:

1. Because the project doesn't exist on PyPI yet, add a **pending** trusted
   publisher: PyPI → your account/organization → *Publishing* → *Add a pending
   publisher*, with:
   - PyPI Project Name: `lineage-sdk`
   - Owner: `lineage-foundation`
   - Repository name: `sdk-python`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
2. In GitHub → repo *Settings* → *Environments*, create an environment named
   `pypi` (optionally add required reviewers so a human approves each publish).

After the first successful publish the pending publisher becomes a regular
trusted publisher automatically.

## Cutting a release

1. Bump `version` in `pyproject.toml` (and update any changelog).
2. Merge to `main`.
3. Tag and create a GitHub Release for that version, e.g. `v1.0.0`
   (`git tag v1.0.0 && git push origin v1.0.0`, then publish a Release from the
   tag — or create the Release in the GitHub UI, which makes the tag).
4. Publishing the Release triggers `.github/workflows/publish.yml`, which builds
   the sdist + wheel, runs `twine check`, and publishes to PyPI via OIDC.

## Local build check (no upload)

To validate the artifacts without publishing:

```bash
rm -rf dist
python -m build
python -m twine check dist/*
```

## TestPyPI (optional dry run)

To rehearse against TestPyPI first, add a second pending publisher on
https://test.pypi.org for the same project/repo/workflow, and either add a
`repository-url: https://test.pypi.org/legacy/` step or run
`twine upload --repository testpypi dist/*` locally with a TestPyPI token.
