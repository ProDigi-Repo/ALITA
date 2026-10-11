# Anonyme Reviewer mit Einladungscode

Zusätzlicher, optionaler Zugang auf `https://review.prodigi-marburg.de`. Der bestehende
Cloudflare-Mailcode-Zugang auf `alita.prodigi-marburg.de` bleibt unverändert.
Kein Caddy, zusätzlicher Identity-Provider oder Benutzer-Datenbank erforderlich.

## Rechte und Grenzen

- Keine E-Mail, kein Name: jeder Reviewer erhält einen zufälligen Einladungscode (192 Bit).
- Alle Dokumente/Metadaten lesen und Originale herunterladen; beide Chats mit **eigenem OpenRouter-Key**.
- Keine Uploads, Metadatenänderungen, Rebuilds oder Adminrechte – auch nicht mit gefälschten E-Mail-Headern.
- Codes gelten standardmäßig 30 Tage; Sitzungen maximal acht Stunden und nie länger als der Code.
- Serverseitig liegen nur Code-Hashes und Ablaufdaten; der Session-Cookie ist hostgebunden, Secure,
  HttpOnly und SameSite=Strict. Schlüssel und Chats bleiben wie bisher nur im Seitenspeicher.
- Jeder, der einen gültigen Code besitzt, kann ihn nutzen/weitergeben. Ein Code pro Reviewer erlaubt
  getrenntes Widerrufen, beweist aber keine Identität. Codes nicht öffentlich oder in URL-Parametern teilen.
- Cloudflare kann IP-Adressen und Verbindungsdaten verarbeiten. Das ist keine Garantie vollständiger
  Netzwerkanonymität. Downloads lassen sich nachträglich nicht zurückholen.

## 1. Erst Code bereitstellen und Backend aktivieren

Auf der VM im aktuellen Checkout `/opt/alita/app`, **bevor** die Reviewer-Route veröffentlicht wird:

```bash
umask 077
python3 tools/reviewer_invites.py --origin https://review.prodigi-marburg.de --days 30
```

Der Befehl ergänzt `.env` atomar, erzeugt bei Bedarf den Session-Schlüssel und zeigt den Einladungscode
**einmalig** an. Die Ausgabe ist vertraulich; privat an die Redaktion weitergeben. Die ebenfalls angezeigte
Invitation ID und das Ablaufdatum für späteren Widerruf notieren. Keine echten Codes/Secrets committen.
Bei weiteren Aufrufen entsteht jeweils ein zusätzlicher Code; bestehende Codes bleiben erhalten.

Nach erstmaligem Deployment dieser Erweiterung:

```bash
docker compose up -d --build --wait backend frontend
docker compose exec -T frontend nginx -t
docker compose exec -T frontend nginx -s reload
```

Nach späterem Erzeugen/Widerrufen eines Codes reicht:

```bash
docker compose up -d --no-deps --wait backend
```

Das kurze Backend-Neustarten unterbricht aktive Anfragen: nicht während eines Uploads/Imports ausführen.
`REVIEW_ORIGIN`, `REVIEW_SESSION_SECRET` und `REVIEW_INVITES` werden über `.env` geladen; ohne
`REVIEW_ORIGIN` bleibt diese Funktion deaktiviert. Die Admin-Allowlist gilt niemals für Reviewer-Sitzungen.

## 2. Cloudflare: zweite Route, keine Änderung der privaten Access-Policy

Im **bestehenden Tunnel** eine weitere Published application route anlegen:

| Feld | Wert |
|---|---|
| Subdomain | `review` |
| Domain | `prodigi-marburg.de` |
| Path | leer |
| Service URL | `http://frontend:80` |
| Protect with Access | für **diese Reviewer-Route aus**; hier authentifiziert die App selbst |

Keine Access-Mailcode-Anwendung für diesen Reviewer-Host anlegen und **keine Bypass-/Everyone-Regel**
für die private ALITA-Anwendung hinzufügen. Falls kontoweites „Require Access protection“ aktiv ist,
muss dieser separate App-Login in der Cloudflare-Konfiguration ausdrücklich berücksichtigt werden;
den Schutz der privaten Anwendung nicht global lockern.

Always Use HTTPS und Cache Bypass für den Reviewer-Host aktivieren. nginx erzwingt zusätzlich HTTPS
anhand des von Cloudflare gesetzten Visitor-Protokolls, begrenzt Login-Anfragen und akzeptiert dort
höchstens 1 KiB Request-Body. Die API-/Download-Prüfung gilt unabhängig von sichtbaren UI-Buttons.

## 3. Test und Weitergabe

- Inkognito `https://review.prodigi-marburg.de` öffnen: Weiterleitung zur Code-Eingabe.
- Falscher/abgelaufener Code: kein Zugriff; richtiger Code: App ohne Adminrechte.
- Dokument herunterladen und mit eigenem Key chatten. Keine Veränderung/Uploads möglich.
- Ausloggen: `/api/me` und Downloads ohne gültigen Cookie wieder gesperrt.
- Private URL weiterhin ausschließlich mit Cloudflare-Mailcode erreichbar.

Danach URL und Code **getrennt von öffentlichen Materialien** über die Redaktion weitergeben.
Für funktionierende Downloads müssen die Originaldateien ebenfalls auf dem Server liegen;
ein Qdrant-Migrationsexport allein genügt nicht.

## Widerrufen

```bash
python3 tools/reviewer_invites.py --revoke <Invitation-ID>
docker compose up -d --no-deps --wait backend
```

Nach dem Neustart sind auch vorhandene Sitzungen dieses Codes ungültig. Ein Wechsel des
`REVIEW_SESSION_SECRET` invalidiert sämtliche Reviewer-Sitzungen. Zum Abschalten aller Reviewer
`REVIEW_ORIGIN` leeren und Backend neu erstellen; die private Cloudflare-Anmeldung bleibt bestehen.
