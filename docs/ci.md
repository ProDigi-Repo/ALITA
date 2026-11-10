# GitHub Actions: CI

The workflow [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on PRs against `main`,
on pushes to `main` and, after the merge, also manually via **Actions → CI → Run workflow**.
A GitHub-hosted Ubuntu 24.04 runner uses Python 3.12 (like the backend image) and Node 24.
Superseded runs of the same branch are cancelled; every run is limited to 15 minutes.

## Checks

- Gitleaks CLI: current versioned file tree and new PR/push commits, output with redacted secrets.
  Manual runs, or runs whose base commit is unavailable, check only the latest commit in addition to the file tree;
  this is not a fresh full audit of the old Git history.
- Ruff for the backend and the invitation CLI; Bash syntax and ShellCheck for the deploy script.
- Syntax of all front-end JavaScript files and the nginx configuration inside the container.
- The whole pytest suite, including authentication, reviewer permissions, deploy/rollback failure cases
  and the actually resolved Compose profiles for both VM sizes. No production database and no model calls.
- Freshly generated front-end fallback data must match the versioned file.

Python dependencies come from `backend/requirements.txt`; their existing version ranges are
not frozen by this workflow. uv, Ruff and ShellCheck are versioned for CI, actions are pinned by
commit and the Gitleaks image by digest. Review tool pins deliberately when updating.
uv caches are only read in PRs and saved on pushes to `main`.

## Security and operation

No repository secrets to enter, no OpenRouter keys, no SSH/Cloudflare/Hetzner credentials.
The GitHub token only has `contents: read`; checkout credentials are not kept in the working directory.
No `pull_request_target`, self-hosted runner, package upload or production deployment. Gitleaks runs as a
local CLI in a container and needs no organisation licence for the separate Gitleaks action.
Normal GitHub Actions minutes for private repositories are billed according to the quota;
the small Hetzner server is not used for CI.

The production deploy deliberately stays [manual with health check/rollback](../deploy/hetzner/operations.md).
Optionally, a repo admin can make the successful check **CI / Tests and checks** required for `main`.
This PR changes no branch rules, secrets, firewall or server configuration.
