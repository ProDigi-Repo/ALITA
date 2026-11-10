# ALITA on the internet: Oracle Cloud (free) + Cloudflare Tunnel + Google login

```
Browser ──https──> Cloudflare Access (Google login, admitted e-mails only)
                         │
                   Cloudflare Tunnel (outbound connection, no open port)
                         │
Oracle VM (ARM, Always Free) ── docker compose: cloudflared → frontend (nginx) → backend → Qdrant, Neo4j
```

The server opens no port. Only people whose Google address you admit get as far as the page.
In addition, every request runs only with the OpenRouter key that the person enters in the interface.

**What you need**

- An Oracle Cloud account (Always Free). On sign-up Oracle asks for a credit card for verification; it is not charged on the free tier.
- A Cloudflare account (free) with **a domain of your own**. Cloudflare Access does not work without a domain. A domain costs about €10 a year, e.g. directly at Cloudflare Registrar.
- Zero Trust Free plan: free for up to 50 people. Cloudflare also asks for a payment method here but charges nothing.

Allow 1 to 2 hours for the first time.

---

## 1. Oracle: create the VM

1. Create a free-tier account on cloud.oracle.com. Choose the **home region** carefully (e.g. Germany Central/Frankfurt); it cannot be changed later.
2. Menu → Compute → Instances → **Create instance**:
   - Image: **Canonical Ubuntu 24.04** (not "Minimal")
   - Shape: **Ampere → VM.Standard.A1.Flex**, **2 OCPU, 12 GB RAM**
     (In 2026 Oracle halved the free quota from 4 OCPU / 24 GB to 2 OCPU / 12 GB. With 2/12 you safely stay at €0; that is enough for ALITA.)
   - Boot volume: 100 GB (200 GB in total are free)
   - SSH keys: **Generate a key pair** → download the private key (e.g. to `C:\Users\<you>\.ssh\oracle.key`)
3. If "Out of capacity" appears: try again later or choose another availability domain.
4. Note the **public IP** of the instance.

> Tip: Oracle may reclaim Always Free VMs that use hardly any CPU for days. Upgrading the account to
> "Pay As You Go" prevents this; within the Always Free limits it still stays free. Then set
> a budget of €1 with an e-mail alert under Billing → Budgets.

Connect (Windows PowerShell):

```powershell
ssh -i $HOME\.ssh\oracle.key ubuntu@<PUBLIC-IP>
```

## 2. Export the index from your own computer

So that nothing has to be ingested again (which costs time and API money), you move the finished index.
On your PC in the project folder (PowerShell):

```powershell
cd "D:\Programming Projects\research-rag"
docker compose build backend
docker compose run --rm migrate export        # writes Qdrant snapshots + uploads to .\migrate\
```

Then copy the whole project folder (including `migrate`, `research` and `.env`) to the VM:

```powershell
scp -i $HOME\.ssh\oracle.key -r "D:\Programming Projects\research-rag" ubuntu@<PUBLIC-IP>:~/
```

The Neo4j graph is not copied; it is rebuilt on the server from the index (without LLM costs).

## 3. Cloudflare: domain, tunnel, Google login

**Domain:** dash.cloudflare.com → Add a domain (or buy one there). With another registrar, enter the two
Cloudflare name servers and wait until the domain is "Active".

**Tunnel:** Zero Trust (one.dash.cloudflare.com) → Networks → **Tunnels** → Create a tunnel → *Cloudflared* →
name `alita`. Under "Install and run connector" there is a command with `--token eyJ…`: copy **only the token**.
Continue to **Public hostname**:

| Field | Value |
|---|---|
| Subdomain / Domain | `alita` / your domain |
| Service Type | `HTTP` |
| URL | `frontend:80` |

**Google as login:** Zero Trust → Settings → Authentication → Login methods → Add new → **Google**.
Cloudflare shows short instructions there; in essence:

1. console.cloud.google.com → new project → *APIs & Services* → *OAuth consent screen* (External, app name "ALITA").
2. *Credentials* → Create credentials → **OAuth client ID** → Web application.
   Authorized JavaScript origin: `https://<team-name>.cloudflareaccess.com`
   Authorized redirect URI: `https://<team-name>.cloudflareaccess.com/cdn-cgi/access/callback`
   (`<team-name>` is shown in Zero Trust under Settings → Custom Pages or Team domain.)
3. Enter the client ID and client secret in Cloudflare → click **Test**.

**Restrict access:** Zero Trust → Access → **Applications** → Add → *Self-hosted*:

- Application domain: `alita.<your-domain>`
- Identity providers: tick only **Google**
- Policy: Action **Allow**, Include → **Emails** → the Google addresses that may get in (or *Emails ending in* `@your-uni.edu`)

## 4. Start on the VM

```bash
cd ~/research-rag
bash deploy/oracle/setup.sh          # installs Docker and swap, completes .env
nano .env                            # enter CLOUDFLARE_TUNNEL_TOKEN=eyJ…, save
exit                                 # log out and in again once (docker group)
```

```bash
ssh -i … ubuntu@<PUBLIC-IP>
cd ~/research-rag
docker compose up -d --build         # first build on ARM: 10–20 minutes
docker compose run --rm migrate import   # load the index + rebuild the knowledge graph
docker compose ps                    # everything "healthy", cloudflared "running"
```

Then open `https://alita.<your-domain>` → Google login → ALITA → enter the OpenRouter key at the top right.

Among other things, `setup.sh` sets `COMPOSE_FILE=docker-compose.yml:deploy/oracle/docker-compose.oracle.yml` in `.env`.
This makes every `docker compose …` on the server use the server variant automatically: no open ports,
tunnel service, memory limits for Neo4j.

## Operation

| Task | Command on the VM |
|---|---|
| Logs | `docker compose logs -f backend cloudflared` |
| Install a new version | copy the changed files with `scp`, then `docker compose up -d --build` |
| Ingest new documents | copy files to `~/research-rag/research/…`, then `docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-… ingest all /research` |
| Back up the index | `docker compose run --rm migrate export` → download the `migrate` folder |
| Test without Cloudflare | locally `ssh -i … -L 8080:127.0.0.1:8080 ubuntu@<IP>` → http://localhost:8080 |

**Limits:** uploads via the page are limited to 100 MB per file on Cloudflare Free. Copy larger project ZIPs with `scp`
to `research/` and ingest them with `ingest`.
