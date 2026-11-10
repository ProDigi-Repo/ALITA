# Small VM, code deployment and rollback

Manual operation without GitHub credentials on the VM and without additional open ports.
No automatic Actions deploy. Secrets, invitations, private keys and backups stay outside Git.

## Optional 4 GB pilot profile

`docker-compose.4gb.yml` contains the limits tested on the small VM:
backend 1280 MiB (one worker, at most 40 open connections, six chat answers computed at once – further questions wait in line), Neo4j 1152 MiB
(heap 256–512 MiB, page cache 256 MiB), Qdrant 1024 MiB (one search/optimizer thread,
`nofile=65536`). Plus small limits for nginx, cloudflared and the CLI jobs.
Imported Qdrant snapshots may bring their own collection optimizer values; check these separately.
`memswap_limit` means **RAM plus swap**, not additional swap.

The sum of the maximum limits exceeds 4 GB: no promise for parallel load.
Run uploads/imports one after the other, not in parallel with heavy chat use. Back up data before larger imports.
On the host, first check `free -h`, `swapon --show` and `df -h /`. The pilot uses
**4 GiB of persistent swap** and `vm.swappiness=10`; do not overwrite existing swap files.
On new VMs set up swap deliberately and check it after a reboot before using this profile.

For a new installation choose the full chain in `.env`:

```dotenv
COMPOSE_FILE=docker-compose.yml:deploy/hetzner/docker-compose.hetzner.yml:deploy/hetzner/docker-compose.4gb.yml
```

The 4 GB profile does **not** replace the Hetzner security profile. Afterwards only run
`docker compose config --quiet`; never print the resolved configuration with secrets.
On an existing VM with `compose.host.yml` do not switch anything automatically: back up the configuration,
compare the values and replace the local last file with the versioned profile only during a planned switch.
The PR alone changes no running containers. The deploy script itself restarts no databases.

## Code update

Prerequisites: an existing, healthy stack, a clean checkout, `.env` with mode 0600,
Docker/Compose >= 2.24.4, Bash, Python 3 and `flock` (Ubuntu: util-linux).
Run the tests first, review the changes and pause writes/uploads/imports.
The script is meant only for backwards-compatible **code updates**, not for data migrations,
changed database images, new networks or a new backend image tag.
Back up the data separately/off-site beforehand: the backups below contain **no data volumes**.

On the trusted workstation use the merged `main`, not an old release tag:

```bash
git switch main
git pull --ff-only
sha=$(git rev-parse HEAD)
git bundle create /tmp/alita-deploy.bundle main
scp /tmp/alita-deploy.bundle alita:/opt/alita/deploy.bundle
scp deploy/hetzner/deploy.sh alita:/opt/alita/deploy.sh
ssh alita 'chmod 700 /opt/alita/deploy.sh'
ssh alita "cd /opt/alita/app && /opt/alita/deploy.sh '$sha' /opt/alita/deploy.bundle"
```

For long runs, execute it in `tmux`/`screen` on the server. Alternatively the full SHA alone
is enough as the only argument if the commit is already in the server checkout.
The script never calls `git pull` and accepts only fast-forward updates; a bundle file must be
local and its `main` must match the given commit exactly. The VM deliberately stays on
this exact commit (`detached HEAD`); local/remote branches are not rewritten.

Sequence:
- Exclusive deploy lock, Access/port/seed check and backup of the configuration/the previous image.
- Make source files readable according to their Git mode (0644/0755), **not** `.env`, `.secrets/` or research data.
  `umask 077` applies to secrets/backups; Git sources need 022, otherwise the unprivileged container fails.
- Build the backend and test the API import as the container user without network before the running service is replaced.
- Start only backend and frontend with `--no-deps`; wait for the health check, test nginx and fetch the API liveness through the proxy.
  nginx is recreated: a reload can keep an old file bind mount after Git updates.
- Compare configuration files and Qdrant/graph counters before/after; Qdrant must be green.
- On errors, reset code and image; abort clearly if the rollback is incomplete. No `down -v`,
  no automatic seed, no database restore and no copying back of secrets that may have changed in the meantime.

## Status and manual recovery

Default location: `/opt/alita/deployments` (0700; can be moved outside the checkout with `ALITA_DEPLOY_STATE_DIR`).
`current-backup` points to the backup of the last attempt: `.env`, optionally `compose.host.yml`,
`revision`, `backend-image`, `image-tag`, data counters and error diagnostics. Treat these files as confidential.
Delete old images/backups only after a successful acceptance and a separate data backup.

`status` contains `RUNNING`, `DEPLOYED`, `ROLLBACK_OK` or `ROLLBACK_NEEDS_ATTENTION`.
After SIGKILL/power loss `RUNNING` may remain; then check manually. This is not an HA system.

If a later public test fails, recover from a private admin shell
(pause running jobs first; do not blindly overwrite current secrets with older values):

```bash
(
set -euo pipefail
cd /opt/alita/app
exec 9>/opt/alita/deployments/lock
flock -n 9 || exit 1
backup=$(< /opt/alita/deployments/current-backup)
cmp -s .env "$backup/.env"   # if it differs, reconcile manually first
if [[ -f "$backup/compose.host.yml" ]]; then
  cmp -s compose.host.yml "$backup/compose.host.yml"
else
  test ! -e compose.host.yml
fi
umask 022
git switch --detach "$(< "$backup/revision")"
docker image tag "$(< "$backup/backend-image")" "$(< "$backup/image-tag")"
docker compose config --quiet
docker compose up -d --no-deps --force-recreate --wait backend
docker compose up -d --no-deps --force-recreate --wait frontend
docker compose exec -T frontend nginx -t
docker compose exec -T frontend wget -q -T 3 -O /dev/null http://127.0.0.1/api/health
printf 'ROLLBACK_OK\n' > /opt/alita/deployments/status
)  # releases the lock even on errors
```

Data migrations are **not** rolled back; that needs a separately tested backup/restore procedure.

## Public acceptance after every update

The private URL is still behind Cloudflare Access; reviewers without a code have no API/download access.
With an existing code: read/download, no uploads/admin rights, both chats with their own OpenRouter key,
log out and check that renewed access without a cookie is refused. Check the front-end/backend version and document counts.
Original files must be on the server separately, otherwise downloads do not work even though the index exists.
