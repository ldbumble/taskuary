# Releasing

`pip install taskuary` instead of `pip install git+https://…` is the difference between a
project that looks finished and one that looks abandoned mid-build. This is the afternoon
that buys it. The name **taskuary** is unclaimed on PyPI as of this writing.

Everything below is done once. After that a release is a tag.

## One-time: Trusted Publishing

No API token is ever created, copied, or stored — PyPI verifies the GitHub workflow's own
identity. A token in a repository secret is a token that can leak; this cannot.

1. Create the account at [pypi.org/account/register](https://pypi.org/account/register/) and
   turn on 2FA (PyPI requires it to publish).
2. Go to [pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/) →
   **Add a new pending publisher**:
   - PyPI Project Name: `taskuary`
   - Owner: `ldbumble`
   - Repository name: `taskuary`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
   *Pending* is the point — it claims the name for this workflow before the project exists,
   so the first publish needs no manual upload.
3. In the repo: **Settings → Environments → New environment** → `pypi`. (Add yourself as a
   required reviewer if you want a human gate on every release.)
4. Optional, recommended for the first one: repeat 2 and 3 on
   [test.pypi.org](https://test.pypi.org/manage/account/publishing/) with environment
   `testpypi`, then run the **publish** workflow by hand (Actions → publish → Run workflow).
   It uploads to TestPyPI only, so a mistake costs nothing — a real PyPI version number can
   never be reused, even after deletion.

## Cutting a release

```bash
# 1. version in ONE place - the tag must match, or you publish a number nobody can see
$EDITOR pyproject.toml            # version = "0.3.0"

# 2. the UI is committed, so it must be current in the same commit
cd website && npm run build && cd ..

python -m pytest tests -q         # the gate before anything leaves the machine
# Timeline/Board chip changes: a named picture in taskuary.testing, pinned in tests/test_factory.py

git commit -am "Release 0.3.0" && git push
git tag v0.3.0 && git push origin v0.3.0
```

The tag runs `.github/workflows/publish.yml`, which rebuilds the UI from that tag's source,
builds the sdist and wheel, and refuses to publish unless the wheel actually contains the
app — `index.html`, the JS and CSS bundles, the operator templates, the WhatsApp bridge — and
installs cleanly into an empty venv. A wheel whose UI is missing installs perfectly and then
serves a blank page, which is a worse first impression than no package at all.

## After the first publish

Change the two install lines in `README.md`:

```
pip install git+https://github.com/ldbumble/taskuary   ->  pip install taskuary
pip install "taskuary[desktop] @ git+https://…"        ->  pip install "taskuary[desktop]"
```

Do it *after* the version is live, not before. A README promising a package that does not
exist yet sends the reader straight to `ERROR: No matching distribution found` — which costs
more trust than the git URL ever did.

Then add the badge under the others:

```markdown
[![PyPI](https://img.shields.io/pypi/v/taskuary.svg)](https://pypi.org/project/taskuary/)
```

## Notes

- **A version is permanent.** PyPI never lets a number be reused, even after you delete the
  file. Test on TestPyPI first, and bump rather than re-upload.
- **`0.x` says what it means.** Breaking changes are expected before 1.0, and the README says
  so at the top.
- The single-file `Taskuary.exe` is a separate artifact built by `ci.yml` on push to master;
  PyPI carries the Python package only.
