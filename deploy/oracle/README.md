# ALITA im Internet: Oracle Cloud (gratis) + Cloudflare Tunnel + Google-Login

```
Browser ──https──> Cloudflare Access (Google-Login, nur freigegebene E-Mails)
                         │
                   Cloudflare Tunnel (ausgehende Verbindung, kein offener Port)
                         │
Oracle-VM (ARM, Always Free) ── docker compose: cloudflared → frontend (nginx) → backend → Qdrant, Neo4j
```

Der Server öffnet keinen Port. Nur Personen, deren Google-Adresse du freigibst, kommen bis zur Seite.
Jede Anfrage läuft außerdem nur mit dem OpenRouter-Key, den die Person selbst im Interface einträgt.

**Was du brauchst**

- Oracle-Cloud-Konto (Always Free). Bei der Anmeldung will Oracle eine Kreditkarte zur Prüfung; belastet wird sie im Free Tier nicht.
- Cloudflare-Konto (gratis) mit **einer eigenen Domain**. Ohne Domain geht Cloudflare Access nicht. Eine Domain kostet ca. 10 € im Jahr, z. B. direkt bei Cloudflare Registrar.
- Zero Trust Free Plan: bis 50 Personen gratis. Cloudflare fragt dabei ebenfalls nach einer Zahlungsmethode, berechnet aber nichts.

Rechne mit 1 bis 2 Stunden für das erste Mal.

---

## 1. Oracle: VM anlegen

1. Auf cloud.oracle.com ein Free-Tier-Konto anlegen. **Home Region** gut wählen (z. B. Germany Central/Frankfurt), sie lässt sich nicht mehr ändern.
2. Menü → Compute → Instances → **Create instance**:
   - Image: **Canonical Ubuntu 24.04** (nicht „Minimal“)
   - Shape: **Ampere → VM.Standard.A1.Flex**, **2 OCPU, 12 GB RAM**
     (Oracle hat das Gratis-Kontingent 2026 von 4 OCPU / 24 GB auf 2 OCPU / 12 GB halbiert. Mit 2/12 bleibst du sicher bei 0 €; ALITA reicht das.)
   - Boot volume: 100 GB (gratis sind zusammen 200 GB)
   - SSH keys: **Generate a key pair** → privaten Schlüssel herunterladen (z. B. nach `C:\Users\<du>\.ssh\oracle.key`)
3. Erscheint „Out of capacity“: später erneut versuchen oder eine andere Availability Domain wählen.
4. Notiere die **Public IP** der Instanz.

> Tipp: Always-Free-VMs, die tagelang kaum CPU nutzen, kann Oracle zurückfordern. Ein Upgrade des Kontos auf
> „Pay As You Go“ verhindert das; innerhalb der Always-Free-Grenzen bleibt es trotzdem kostenlos. Setze dir dann
> unter Billing → Budgets ein Budget von 1 € mit E-Mail-Alarm.

Verbinden (Windows PowerShell):

```powershell
ssh -i $HOME\.ssh\oracle.key ubuntu@<PUBLIC-IP>
```

## 2. Index vom eigenen Rechner exportieren

Damit nicht alles neu eingelesen werden muss (kostet Zeit und API-Geld), ziehst du den fertigen Index um.
Auf deinem PC im Projektordner (PowerShell):

```powershell
cd "D:\Programming Projects\research-rag"
docker compose build backend
docker compose run --rm migrate export        # schreibt Qdrant-Snapshots + Uploads nach .\migrate\
```

Dann den ganzen Projektordner (inklusive `migrate`, `research` und `.env`) auf die VM kopieren:

```powershell
scp -i $HOME\.ssh\oracle.key -r "D:\Programming Projects\research-rag" ubuntu@<PUBLIC-IP>:~/
```

Der Neo4j-Graph wird nicht kopiert; er wird auf dem Server aus dem Index neu gebaut (ohne LLM-Kosten).

## 3. Cloudflare: Domain, Tunnel, Google-Login

**Domain:** dash.cloudflare.com → Add a domain (oder dort kaufen). Bei einem fremden Registrar die zwei
Cloudflare-Nameserver eintragen und warten, bis die Domain „Active“ ist.

**Tunnel:** Zero Trust (one.dash.cloudflare.com) → Networks → **Tunnels** → Create a tunnel → *Cloudflared* →
Name `alita`. Bei „Install and run connector“ steht ein Befehl mit `--token eyJ…`: **nur den Token** kopieren.
Weiter zu **Public hostname**:

| Feld | Wert |
|---|---|
| Subdomain / Domain | `alita` / deine Domain |
| Service Type | `HTTP` |
| URL | `frontend:80` |

**Google als Login:** Zero Trust → Settings → Authentication → Login methods → Add new → **Google**.
Cloudflare zeigt dort eine Kurzanleitung; im Kern:

1. console.cloud.google.com → neues Projekt → *APIs & Services* → *OAuth consent screen* (External, App-Name „ALITA“).
2. *Credentials* → Create credentials → **OAuth client ID** → Web application.
   Authorized JavaScript origin: `https://<team-name>.cloudflareaccess.com`
   Authorized redirect URI: `https://<team-name>.cloudflareaccess.com/cdn-cgi/access/callback`
   (`<team-name>` steht in Zero Trust unter Settings → Custom Pages bzw. Team domain.)
3. Client ID und Client Secret in Cloudflare eintragen → **Test** klicken.

**Zugang sperren:** Zero Trust → Access → **Applications** → Add → *Self-hosted*:

- Application domain: `alita.<deine-domain>`
- Identity providers: nur **Google** anhaken
- Policy: Action **Allow**, Include → **Emails** → die Google-Adressen, die rein dürfen (oder *Emails ending in* `@deine-uni.de`)

## 4. Auf der VM starten

```bash
cd ~/research-rag
bash deploy/oracle/setup.sh          # installiert Docker, Swap, ergänzt .env
nano .env                            # CLOUDFLARE_TUNNEL_TOKEN=eyJ… eintragen, speichern
exit                                 # einmal ab- und wieder anmelden (Docker-Gruppe)
```

```bash
ssh -i … ubuntu@<PUBLIC-IP>
cd ~/research-rag
docker compose up -d --build         # erster Build auf ARM: 10–20 Minuten
docker compose run --rm migrate import   # Index einspielen + Wissensgraph neu bauen
docker compose ps                    # alles „healthy“, cloudflared „running“
```

Dann `https://alita.<deine-domain>` öffnen → Google-Login → ALITA → oben rechts den OpenRouter-Key eintragen.

`setup.sh` setzt in `.env` unter anderem `COMPOSE_FILE=docker-compose.yml:deploy/oracle/docker-compose.oracle.yml`.
Dadurch nutzt jedes `docker compose …` auf dem Server automatisch die Server-Variante: keine offenen Ports,
Tunnel-Dienst, Speicherlimits für Neo4j.

## Betrieb

| Aufgabe | Befehl auf der VM |
|---|---|
| Logs | `docker compose logs -f backend cloudflared` |
| Neue Version einspielen | geänderte Dateien per `scp` kopieren, dann `docker compose up -d --build` |
| Neue Dokumente einlesen | Dateien nach `~/research-rag/research/…` kopieren, dann `docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-… ingest all /research` |
| Backup des Index | `docker compose run --rm migrate export` → Ordner `migrate` herunterladen |
| Testen ohne Cloudflare | lokal `ssh -i … -L 8080:127.0.0.1:8080 ubuntu@<IP>` → http://localhost:8080 |

**Grenzen:** Uploads über die Seite gehen bei Cloudflare Free bis 100 MB pro Datei. Größere Projekt-ZIPs per `scp`
nach `research/` kopieren und mit `ingest` einlesen.
