# Kleine VM, Code-Deployment und Rollback

Manueller Betrieb ohne GitHub-Zugangsdaten auf der VM und ohne zusätzliche offene Ports.
Kein automatischer Actions-Deploy. Secrets, Einladungen, private Schlüssel und Backups bleiben außerhalb von Git.

## Optionales 4-GB-Pilotprofil

`docker-compose.4gb.yml` enthält die auf der kleinen VM erprobten Grenzen:
Backend 1280 MiB (ein Worker, höchstens acht gleichzeitige Anfragen), Neo4j 1152 MiB
(Heap 256–512 MiB, Pagecache 256 MiB), Qdrant 1024 MiB (ein Such-/Optimizer-Thread,
`nofile=65536`). Dazu kleine Limits für nginx, cloudflared und die CLI-Jobs.
Importierte Qdrant-Snapshots können eigene Collection-Optimiererwerte mitbringen; diese separat prüfen.
`memswap_limit` bezeichnet **RAM plus Swap**, nicht zusätzlichen Swap.

Die Summe der maximalen Limits überschreitet 4 GB: kein Versprechen für parallele Last.
Uploads/Imports nacheinander, nicht parallel zu starkem Chatbetrieb. Vor größeren Imports Daten sichern.
Auf dem Host zuerst `free -h`, `swapon --show` und `df -h /` prüfen. Der Pilot nutzt
**4 GiB persistenten Swap** und `vm.swappiness=10`; vorhandene Swap-Dateien nicht überschreiben.
Auf neuen VMs Swap bewusst einrichten und nach einem Neustart überprüfen, bevor dieses Profil verwendet wird.

Bei einer neuen Installation in `.env` die vollständige Kette wählen:

```dotenv
COMPOSE_FILE=docker-compose.yml:deploy/hetzner/docker-compose.hetzner.yml:deploy/hetzner/docker-compose.4gb.yml
```

Das 4-GB-Profil ersetzt **nicht** das Hetzner-Sicherheitsprofil. Danach nur
`docker compose config --quiet` ausführen, nie die aufgelöste Konfiguration mit Secrets ausgeben.
Auf einer vorhandenen VM mit `compose.host.yml` nichts automatisch umstellen: Konfiguration sichern,
Werte vergleichen und die lokale letzte Datei erst bei einer geplanten Umstellung durch das versionierte Profil ersetzen.
Der PR allein ändert keine laufenden Container. Das Deploy-Skript selbst startet keine Datenbanken neu.

## Code-Update

Voraussetzungen: bestehender, gesunder Stack, sauberer Checkout, `.env` mit Modus 0600,
Docker/Compose >= 2.24.4, Bash, Python 3 und `flock` (Ubuntu: util-linux).
Vorher Tests ausführen, Änderungen prüfen und Schreibzugriffe/Uploads/Imports pausieren.
Das Skript ist nur für rückwärtskompatible **Code-Updates**, nicht für Datenmigrationen,
geänderte DB-Images, neue Netzwerke oder einen neuen Backend-Image-Tag vorgesehen.
Datenbestände vorher separat/offsite sichern: die folgenden Sicherungen enthalten **keine Datenvolumes**.

Auf dem vertrauenswürdigen Arbeitsrechner den gemergten `main` verwenden, nicht einen alten Release-Tag:

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

Bei langer Laufzeit in `tmux`/`screen` auf dem Server ausführen. Alternativ genügt der volle SHA
als einziges Argument, wenn der Commit bereits im Server-Checkout vorhanden ist.
Das Skript ruft nie `git pull` auf und akzeptiert nur Fast-Forward-Updates; eine Bundle-Datei muss
lokal sein und ihr `main` exakt dem angegebenen Commit entsprechen. Die VM bleibt absichtlich auf
diesem exakten Commit (`detached HEAD`), lokale/Remote-Branches werden nicht umgeschrieben.

Ablauf:
- Exklusive Deploy-Sperre, Access/Port-/Seed-Prüfung und Sicherung der Konfiguration/des vorherigen Images.
- Quelldateien nach Git-Modus lesbar machen (0644/0755), **nicht** `.env`, `.secrets/` oder Forschungsdaten.
  `umask 077` gilt für Secrets/Backups; Git-Quellen brauchen 022, sonst scheitert der nicht privilegierte Container.
- Backend bauen und API-Import als Container-Benutzer ohne Netzwerk testen, bevor der laufende Dienst ersetzt wird.
- Nur Backend und Frontend mit `--no-deps` starten; Healthcheck abwarten, nginx testen und die API-Liveness durch den Proxy abrufen.
  nginx wird neu erstellt: ein Reload kann nach Git-Updates einen alten Datei-Bind-Mount behalten.
- Konfigurationsdateien und Qdrant-/Graph-Zähler vorher/nachher vergleichen; Qdrant muss grün sein.
- Bei Fehlern Code und Image zurücksetzen, bei unvollständigem Rollback klar abbrechen. Kein `down -v`,
  kein automatischer Seed, kein Datenbank-Restore und kein Zurückkopieren möglicherweise inzwischen geänderter Secrets.

## Status und manuelle Wiederherstellung

Standardablage: `/opt/alita/deployments` (0700; mit `ALITA_DEPLOY_STATE_DIR` außerhalb des Checkouts anpassbar).
`current-backup` zeigt auf die Sicherung des letzten Versuchs: `.env`, optional `compose.host.yml`,
`revision`, `backend-image`, `image-tag`, Datenzähler und Fehlerdiagnose. Diese Dateien vertraulich behandeln.
Alte Images/Backups erst nach erfolgreicher Abnahme und separater Datensicherung löschen.

`status` enthält `RUNNING`, `DEPLOYED`, `ROLLBACK_OK` oder `ROLLBACK_NEEDS_ATTENTION`.
Bei SIGKILL/Stromausfall kann `RUNNING` stehen bleiben; dann manuell prüfen. Das ist kein HA-System.

Falls ein späterer öffentlicher Test scheitert, aus einer privaten Admin-Shell wiederherstellen
(erst laufende Jobs pausieren; aktuelle Secrets nicht blind mit älteren Werten überschreiben):

```bash
(
set -euo pipefail
cd /opt/alita/app
exec 9>/opt/alita/deployments/lock
flock -n 9 || exit 1
backup=$(< /opt/alita/deployments/current-backup)
cmp -s .env "$backup/.env"   # bei Änderungen erst manuell abgleichen
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
)  # Sperre auch bei Fehlern freigeben
```

Datenmigrationen werden **nicht** zurückgerollt; dafür ist ein separat getestetes Backup-/Restore-Verfahren nötig.

## Öffentliche Abnahme nach jedem Update

Private URL weiterhin hinter Cloudflare Access; Reviewer ohne Code ohne API-/Download-Zugriff.
Mit bestehendem Code: lesen/herunterladen, keine Uploads/Adminrechte, beide Chats mit eigenem OpenRouter-Key,
ausloggen und erneuten Zugriff ohne Cookie ablehnen. Frontend-/Backend-Version und Dokumentzahlen prüfen.
Originaldateien müssen separat auf dem Server liegen, sonst funktionieren Downloads trotz vorhandenem Index nicht.
