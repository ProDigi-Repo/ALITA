# Hetzner: gemeinsamer Workspace mit Cloudflare-Mailcode

Alle freigegebenen Personen dürfen alle Dokumente lesen/herunterladen und beide Chats nutzen.
Nur `ADMIN_EMAILS` dürfen hochladen, Metadaten ändern und Wartungs-/Neuberechnungsaufrufe ausführen.
Jede Person bringt ihren eigenen OpenRouter-Key mit. Es gibt keine lokalen Benutzerkonten.

## 1. VM vorbereiten

- Ubuntu 24.04 LTS; als Startwert 4 vCPU / 16 GB RAM / mindestens 100 GB SSD, je nach Datenmenge.
- Docker Engine und Compose **>= 2.24.4** installieren: [offizielle Ubuntu-Anleitung](https://docs.docker.com/engine/install/ubuntu/).
- Hetzner Cloud Firewall: eingehend alles sperren außer SSH (TCP 22) von deiner Admin-IP/VPN,
  für IPv4 **und** IPv6. SSH nur mit Schlüssel; keine öffentliche Freigabe von 80/443 oder DB-Ports.
- Ausgehende Verbindungen müssen möglich sein: DNS, HTTPS und Cloudflare Tunnel (TCP/UDP 7844).
- Sicherheitsupdates aktivieren. Zugriff auf Docker entspricht Root-Zugriff; Docker-Gruppe nur für Admins.
- Repo auf die VM klonen und im Repository-Wurzelverzeichnis arbeiten. Nicht das Oracle-Setup ausführen.

## 2. Cloudflare konfigurieren – vor Veröffentlichung des Tunnels

Voraussetzung: eigene Domain als aktive Zone bei Cloudflare und ein Zero-Trust-Konto.
Keine Google-OAuth-App und kein eigener Mailserver nötig. Dashboard-Bezeichnungen können leicht variieren.

1. **Zero Trust → Integrations → Identity providers → Add → One-time PIN** aktivieren.
2. **Access controls → Applications → Add application → Self-hosted**:
   - Hostname: `alita.deine-domain.de`, **kein Pfadfilter** (gesamte Anwendung schützen).
   - Session duration: beispielsweise **8 Stunden**.
   - Login method: nur **One-time PIN**.
   - Policy: **Allow → Include → Emails**, einzelne erlaubte Adressen eintragen, **inklusive deiner Admin-Mail**.
   - Keine `Everyone`-, `Bypass`- oder ausschließlich auf die Login-Methode gestützte Freigabe.
   - Den **Application Audience (AUD) Tag** aus den Anwendungseinstellungen kopieren.
3. Die **Team domain** notieren: `dein-team.cloudflareaccess.com` (ohne `https://`).
4. **Networks → Connectors/Tunnels → Create tunnel → Cloudflared**, Name beispielsweise `alita`:
   - Aus dem angezeigten Installationsbefehl nur den **Tunnel-Token** kopieren; keinen zusätzlichen Host-Dienst installieren.
   - Published application route / Public hostname: `alita.deine-domain.de`.
   - Service: **HTTP**, URL **`frontend:80`** (nicht localhost, nicht die VM-IP).
   - Unter den zusätzlichen Einstellungen **Access → Protect with Access** einschalten;
     Team und den AUD-Tag der obigen Anwendung auswählen/eintragen.
   - Cloudflare legt den Tunnel-DNS-Eintrag an. Kein zusätzlicher A/AAAA-Eintrag zur VM-IP.
5. Für diesen Hostnamen **Always Use HTTPS** aktivieren und eine Cache-Regel **Bypass cache** setzen.
   Keine „Cache Everything“-Regel; Chat-Antworten, Downloads und Login dürfen nicht gecacht werden.

Ein Nutzer öffnet die URL, gibt seine freigegebene E-Mail an und erhält einen Einmalcode.
`ADMIN_EMAILS` allein erlaubt noch keinen Login: Admins müssen auch in der Access-Allowlist stehen.
Zugang entziehen: Adresse aus der Policy entfernen **und bestehende Access-Sitzungen widerrufen**.
Cloudflare-, Hetzner- und Mailkonten der Admins mit MFA absichern, auch wenn der App-Login Mailcodes nutzt.

## 3. Serverkonfiguration

```bash
umask 077
cp .env.example .env                  # nur bei einer neuen Installation
openssl rand -hex 32                 # Ausgabe als NEO4J_PASSWORD in .env eintragen
nano .env
```

Diese Werte in `.env` setzen (Platzhalter ersetzen, kein produktives Secret committen):

```dotenv
COMPOSE_FILE=docker-compose.yml:deploy/hetzner/docker-compose.hetzner.yml
NEO4J_PASSWORD=<zufaellig-generiertes-passwort>
ACCESS_TEAM_DOMAIN=dein-team.cloudflareaccess.com
ACCESS_AUDIENCE=<aud-tag-der-access-anwendung>
PUBLIC_ORIGIN=https://alita.deine-domain.de
ADMIN_EMAILS=du@example.org
RESEARCH_DIR=./research
```

`PUBLIC_ORIGIN` ohne abschließenden Slash; mehrere Admins mit Komma trennen.
Das Hetzner-Profil erzwingt `ACCESS_ENABLED=true`, unabhängig von `.env`.
Es veröffentlicht **keinen** Hostport. Backend-JWT-Prüfung: Signatur, Issuer, Audience und Ablauf;
fehlende/ungültige Tokens werden abgewiesen. Ein E-Mail-Header allein gewährt keine Rechte.
Nur die interne Liveness-Route `/api/health` ist von dieser Backend-Prüfung ausgenommen;
öffentlich bleibt auch sie hinter Access.

Den Tunnel-Token separat ablegen (Bash, Eingabe unsichtbar und nicht in der Shell-History):

```bash
install -d -m 700 .secrets
read -rsp 'Cloudflare Tunnel-Token: ' token; printf '\n'
printf '%s' "$token" > .secrets/cloudflare-token
unset token
chmod 644 .secrets/cloudflare-token
chmod 600 .env
```

Die Datei ist innerhalb des **nur für dich zugänglichen Verzeichnisses (0700)** lesbar, damit
`cloudflared` als UID 65532 den read-only Secret-Mount lesen kann. Compose-Secrets sind hier lokale
Dateimounts, kein verschlüsselter Secret-Store. `.env` und `.secrets/` sind Git-ignoriert;
der Tunnel-Token wird nicht an die Backend-Container weitergegeben.

```bash
docker compose config --quiet        # prüft Konfiguration, ohne Secret-Werte auszugeben
docker compose up -d --build
docker compose ps
docker compose logs --tail 50 cloudflared backend
```

**Bestehende Neo4j-Datenbank:** Ein neues `NEO4J_PASSWORD` initialisiert nur eine leere Datenbank.
Bei vorhandenem Volume zuerst das Passwort in Neo4j ändern und dann die Konfiguration angleichen.
Nicht das Datenvolume löschen, um das Passwortproblem zu umgehen.

## 4. Daten und Abnahme

Kein automatisches `seed` beim Serverstart. Daten bewusst über den Admin-Upload oder die bestehende CLI einlesen.
Vorhandene Daten lassen sich mit `migrate export/import` übertragen; `research/` separat kopieren.
Embedding-Modell und Dimension müssen zum importierten Index passen (die `.env.example` nutzt 1536 Dimensionen).

Vor Einladungen testen:
- Inkognito: `/`, `/api/documents`, `/api/export` und `/files/<gültige-id>` führen zum Login.
- Nicht freigegebene E-Mail kommt nicht hinein. Freigegebene E-Mail bekommt den Mailcode.
- Normaler Nutzer: lesen, PDF öffnen, beide Chats mit eigenem Key; Upload/Änderungen liefern **403**.
- Admin: Upload funktioniert. Beide Chats streamen sichtbar; ohne OpenRouter-Key kein Modellaufruf.
- Externer Porttest: 8080, 8000, 6333, 7474 und 7687 nicht erreichbar (IPv4/IPv6).
- `docker compose ps` zeigt keine Host-Portzuordnung, nur gegebenenfalls interne Containerports.

**Browserverhalten:** Key und Chatverlauf bleiben nur im Speicher der geöffneten Seite.
Reload/Schließen verwirft sie; Chats vorher als TXT exportieren. Alte persistierte Keys und Chatverläufe
werden beim ersten Laden entfernt: vor einem Upgrade gewünschte alte Chats exportieren.
„Log out“ beendet die Access-Sitzung; an geteilten Rechnern anschließend alle ALITA-Tabs schließen.

## 5. Bewusst schlanke Grenzen und Betrieb

- Admin-Uploads: höchstens **50 MiB pro HTTP-Anfrage**, ZIP höchstens **1000 Einträge / 250 MiB entpackt**;
  keine Symlinks oder unsicheren ZIP-Pfade. Größere Bestände per SSH/CLI einlesen.
- Nur PDFs werden inline angezeigt; andere Originale als Downloads. Same-origin API, kein Wildcard-CORS.
- Ingestion bleibt ein Prozess-Hintergrundjob: **ein Backend-Worker**, keine Neustarts während laufender Jobs,
  große Imports nacheinander. Kein Worker-/Queue-Umbau in diesem PR.
- Kein Mandantenschutz, keine Antivirus-Sandbox, keine Hochverfügbarkeit. Upload nur durch vertrauenswürdige Admins.
- Backups vor Updates und regelmäßig verschlüsselt auf ein getrenntes Ziel: Qdrant-Snapshots,
  Uploads (`app_data`), `research/`, Konfiguration und Neo4j (oder getesteter Rebuild aus Qdrant).
  `migrate export` allein enthält **nicht** `research/`. Für konsistente Sicherungen Schreibzugriffe pausieren.
  Wiederherstellung auf einer separaten Instanz testen; nie `docker compose down -v` für normale Updates.
- Images/Abhängigkeiten regelmäßig aktualisieren; Speicherplatz und Backuperfolg überwachen.
- Cloudflare terminiert HTTPS; OpenRouter und Modellanbieter erhalten Inhalte zur Verarbeitung.
  Deutscher VM-Standort allein garantiert keine ausschließlich deutsche/EU-Datenverarbeitung.

Referenzen: [Mailcodes](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/),
[Access und Tunnel](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/),
[JWT-Prüfung](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).
