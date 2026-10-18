# GitHub Actions: CI

Der Workflow [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) startet bei PRs gegen `main`,
bei Pushes auf `main` und nach dem Merge auch manuell über **Actions → CI → Run workflow**.
Ein GitHub-gehosteter Ubuntu-24.04-Runner nutzt Python 3.12 (wie das Backend-Image) und Node 24.
Überholte Läufe desselben Branches werden abgebrochen, jeder Lauf ist auf 15 Minuten begrenzt.

## Prüfungen

- Gitleaks-CLI: aktueller versionierter Dateibaum und neue PR-/Push-Commits, Ausgabe mit redigierten Secrets.
  Manuelle Läufe bzw. nicht verfügbare Basis-Commits prüfen zusätzlich zum Dateibaum nur den letzten Commit;
  das ist kein erneuter vollständiger Audit der alten Git-Historie.
- Ruff für Backend und Einladungs-CLI; Bash-Syntax und ShellCheck für das Deploy-Skript.
- Syntax aller Frontend-JavaScript-Dateien und nginx-Konfiguration im Container.
- Gesamte pytest-Suite einschließlich Authentifizierung, Reviewer-Rechten, Deploy-/Rollback-Fehlerfällen
  und tatsächlich aufgelösten Compose-Profilen für beide VM-Größen. Keine Produktions-DB oder Modellaufrufe.
- Neu erzeugte Frontend-Fallbackdaten müssen mit der versionierten Datei übereinstimmen.

Python-Abhängigkeiten kommen aus `backend/requirements.txt`; deren bestehende Versionsbereiche werden
nicht durch diesen Workflow eingefroren. uv, Ruff und ShellCheck sind für CI versioniert, Actions per
Commit und das Gitleaks-Image per Digest fixiert. Werkzeugpins bei Updates bewusst überprüfen.
uv-Caches werden in PRs nur gelesen und bei Pushes auf `main` gespeichert.

## Sicherheit und Betrieb

Keine einzutragenden Repository-Secrets, keine OpenRouter-Keys, keine SSH-/Cloudflare-/Hetzner-Zugangsdaten.
Der GitHub-Token hat nur `contents: read`; Checkout-Zugangsdaten werden nicht im Arbeitsverzeichnis behalten.
Kein `pull_request_target`, Self-hosted Runner, Paket-Upload oder Produktiv-Deployment. Gitleaks läuft als
lokale CLI im Container und benötigt keine Organisationslizenz der separaten Gitleaks-Action.
Normale GitHub-Actions-Minuten für private Repositories werden gemäß Kontingent abgerechnet;
der kleine Hetzner-Server wird nicht für CI verwendet.

Der Produktiv-Deploy bleibt bewusst [manuell mit Healthcheck/Rollback](../deploy/hetzner/operations.md).
Optional kann ein Repo-Admin den erfolgreichen Check **CI / Tests and checks** für `main` verpflichtend
machen. Dieser PR ändert keine Branch-Regeln, Secrets, Firewall oder Serverkonfiguration.
