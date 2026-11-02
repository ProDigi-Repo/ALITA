# Hetzner: shared workspace with Cloudflare mail code

Everyone who is admitted may read/download all documents and use both chats.
Only `ADMIN_EMAILS` may upload, change metadata and run maintenance/recomputation calls.
Every person brings their own OpenRouter key. There are no local user accounts.
For anonymous review without an e-mail address there is an optional, separate
[reviewer access with an invitation code](reviewers.md).
The [operations runbook](operations.md) describes the optional 4 GB pilot profile,
manual code deployments and rollbacks with `deploy.sh`.

## 1. Prepare the VM

- Ubuntu 24.04 LTS; as a starting point 4 vCPU / 16 GB RAM / at least 100 GB SSD, depending on the data volume.
  For small, economical pilot installations use the [4 GB profile with host swap](operations.md#optional-4-gb-pilot-profile) instead; parallel load is not guaranteed with it.
- Install Docker Engine and Compose **>= 2.24.4**: [official Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/).
- Hetzner Cloud Firewall: block all inbound traffic except SSH (TCP 22) from your admin IP/VPN,
  for IPv4 **and** IPv6. SSH with keys only; no public exposure of 80/443 or database ports.
- Outbound connections must be possible: DNS, HTTPS and Cloudflare Tunnel (TCP/UDP 7844).
- Enable security updates. Access to Docker equals root access; the docker group is for admins only.
- Clone the repo onto the VM and work in the repository root. Do not run the Oracle setup.

## 2. Configure Cloudflare – before publishing the tunnel

Prerequisite: your own domain as an active zone at Cloudflare and a Zero Trust account.
No Google OAuth app and no own mail server needed. Dashboard labels may vary slightly.

1. Enable **Zero Trust → Integrations → Identity providers → Add → One-time PIN**.
2. **Access controls → Applications → Add application → Self-hosted**:
   - Hostname: `alita.your-domain.com`, **no path filter** (protect the whole application).
   - Session duration: for example **8 hours**.
   - Login method: **One-time PIN** only.
   - Policy: **Allow → Include → Emails**, enter the individual allowed addresses, **including your admin mail**.
   - No `Everyone` or `Bypass` rule and no rule that relies solely on the login method.
   - Copy the **Application Audience (AUD) Tag** from the application settings.
3. Note the **team domain**: `your-team.cloudflareaccess.com` (without `https://`).
4. **Networks → Connectors/Tunnels → Create tunnel → Cloudflared**, name for example `alita`:
   - From the installation command shown, copy only the **tunnel token**; do not install an additional host service.
   - Published application route / public hostname: `alita.your-domain.com`.
   - Service: **HTTP**, URL **`frontend:80`** (not localhost, not the VM IP).
   - In the additional settings, switch on **Access → Protect with Access**;
     select/enter the team and the AUD tag of the application above.
   - Cloudflare creates the tunnel DNS record. No additional A/AAAA record pointing to the VM IP.
5. For this hostname enable **Always Use HTTPS** and set a cache rule **Bypass cache**.
   No "Cache Everything" rule; chat answers, downloads and login must not be cached.

A user opens the URL, enters their admitted e-mail and receives a one-time code.
`ADMIN_EMAILS` alone does not allow a login: admins must also be on the Access allowlist.
To revoke access: remove the address from the policy **and revoke existing Access sessions**.
Protect the admins' Cloudflare, Hetzner and mail accounts with MFA, even though the app login uses mail codes.

## 3. Server configuration

```bash
umask 077
cp .env.example .env                  # only for a new installation
openssl rand -hex 32                 # enter the output as NEO4J_PASSWORD in .env
nano .env
```

Set these values in `.env` (replace the placeholders, do not commit a production secret):

```dotenv
COMPOSE_FILE=docker-compose.yml:deploy/hetzner/docker-compose.hetzner.yml
NEO4J_PASSWORD=<randomly-generated-password>
ACCESS_TEAM_DOMAIN=your-team.cloudflareaccess.com
ACCESS_AUDIENCE=<aud-tag-of-the-access-application>
PUBLIC_ORIGIN=https://alita.your-domain.com
ADMIN_EMAILS=you@example.org
RESEARCH_DIR=./research
```

`PUBLIC_ORIGIN` without a trailing slash; separate several admins with commas.
The Hetzner profile forces `ACCESS_ENABLED=true`, regardless of `.env`.
It publishes **no** host port. Backend JWT check: signature, issuer, audience and expiry;
missing/invalid tokens are rejected. An e-mail header alone grants no rights.
Only the internal liveness route `/api/health` is exempt from this backend check;
publicly it, too, stays behind Access.

Store the tunnel token separately (Bash; the input is hidden and not in the shell history):

```bash
install -d -m 700 .secrets
read -rsp 'Cloudflare Tunnel-Token: ' token; printf '\n'
printf '%s' "$token" > .secrets/cloudflare-token
unset token
chmod 644 .secrets/cloudflare-token
chmod 600 .env
```

The file is readable inside the **directory that only you can access (0700)**, so that
`cloudflared` as UID 65532 can read the read-only secret mount. Compose secrets are local
file mounts here, not an encrypted secret store. `.env` and `.secrets/` are git-ignored;
the tunnel token is not passed to the backend containers.

```bash
docker compose config --quiet        # checks the configuration without printing secret values
docker compose up -d --build
docker compose ps
docker compose logs --tail 50 cloudflared backend
```

**Existing Neo4j database:** a new `NEO4J_PASSWORD` only initialises an empty database.
With an existing volume, first change the password in Neo4j and then align the configuration.
Do not delete the data volume to get around the password problem.

## 4. Data and acceptance

No automatic `seed` on server start. Load data deliberately via the admin upload or the existing CLI.
Existing data can be transferred with `migrate export/import`; copy `research/` separately.
Embedding model and dimension must match the imported index (`.env.example` uses 1536 dimensions).

Test before sending invitations:
- Private window: `/`, `/api/documents`, `/api/export` and `/files/<valid-id>` lead to the login.
- An e-mail that is not admitted does not get in. An admitted e-mail receives the mail code.
- Normal user: read, open PDFs, both chats with their own key; uploads/changes return **403**.
- Admin: upload works. Both chats stream visibly; without an OpenRouter key no model call.
- External port test: 8080, 8000, 6333, 7474 and 7687 not reachable (IPv4/IPv6).
- `docker compose ps` shows no host port mapping, at most internal container ports.

**Browser behaviour:** key and chat history stay only in the memory of the open page.
Reloading/closing discards them; export chats as TXT beforehand. Old persisted keys and chat histories
are removed on the first load: export any old chats you want to keep before an upgrade.
"Log out" ends the Access session; on shared computers close all ALITA tabs afterwards.

## 5. Deliberately lean limits and operation

- Admin uploads: at most **50 MiB per HTTP request**, ZIP at most **1000 entries / 250 MiB unpacked**;
  no symlinks or unsafe ZIP paths. Load larger collections via SSH/CLI.
- Only PDFs are shown inline; other originals as downloads. Same-origin API, no wildcard CORS.
- Ingestion stays an in-process background job: **one backend worker**, no restarts during running jobs,
  large imports one after the other. No worker/queue rework in this PR.
- No tenant isolation, no antivirus sandbox, no high availability. Uploads by trusted admins only.
- Backups before updates and regularly, encrypted, to a separate target: Qdrant snapshots,
  uploads (`app_data`), `research/`, configuration and Neo4j (or a tested rebuild from Qdrant).
  `migrate export` alone does **not** include `research/`. Pause writes for consistent backups.
  Test restoring on a separate instance; never use `docker compose down -v` for normal updates.
- Update images/dependencies regularly; monitor disk space and backup success.
- Cloudflare terminates HTTPS; OpenRouter and model providers receive content for processing.
  A German VM location alone does not guarantee exclusively German/EU data processing.

References: [mail codes](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/),
[Access and Tunnel](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/),
[JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).
