#!/usr/bin/env bash
# Code-only deployment of an explicitly reviewed commit; no fetch credentials required on the VM.
set -Eeuo pipefail

normalize_source() {
    # Git under umask 077 can produce root-only source; non-root containers need readable files.
    python3 - <<'PY'
import os
import subprocess
from pathlib import Path
for entry in subprocess.check_output(["git", "ls-files", "--stage", "-z"]).split(b"\0"):
    if not entry:
        continue
    meta, name = entry.split(b"\t", 1)
    mode = meta.split()[0]
    path = Path(os.fsdecode(name))
    if mode not in (b"100644", b"100755") or path.parts[0] in {"research", "data", "migrate"}:
        continue
    path.chmod(0o755 if mode == b"100755" else 0o644)
    parent = path.parent
    while parent != Path("."):
        parent.chmod(0o755)
        parent = parent.parent
PY
}

check_config() {
    # Do not log resolved Compose output: it contains .env secrets.
    docker compose --profile '*' config --format json | python3 -c '
import json, sys
services = json.load(sys.stdin)["services"]
assert not any(s.get("ports") for s in services.values()), "Published host ports are not allowed"
assert str(services["backend"]["environment"]["ACCESS_ENABLED"]).lower() == "true", "Access must stay enabled"
assert "seed" in services.get("seed", {}).get("profiles", []), "Automatic seed is not allowed"
if sys.argv[1]:
    assert services["backend"]["image"] == sys.argv[1], "Backend image tag changes require a manual deployment"
' "${image:-}"
}

counts() {
    docker compose exec -T backend python - <<'PY'
import json
from app import graph, store
from app.config import get_settings
s = get_settings()
c = store.client()
collections = {name: c.get_collection(name) for name in (s.col_documents, s.col_chunks, s.col_projects)}
assert all(str(info.status) == "green" for info in collections.values()), "Qdrant is not green"
result = {"collections": {name: info.points_count for name, info in collections.items()}}
if s.graph_enabled:
    result["graph"] = {
        "documents": graph.run("MATCH (d:Document) RETURN count(d) AS n")[0]["n"],
        "chunks": graph.run("MATCH (c:Chunk) RETURN count(c) AS n")[0]["n"],
    }
print(json.dumps(result, sort_keys=True))
PY
}

unchanged_config() {
    cmp -s .env "$backup/.env" || return
    if [[ -f "$backup/compose.host.yml" ]]; then
        cmp -s compose.host.yml "$backup/compose.host.yml"
    else
        test ! -e compose.host.yml
    fi
}

proxy_health() {
    local attempt
    for ((attempt=0; attempt<10; attempt++)); do
        # Explicit IPv4: nginx listens on 0.0.0.0; BusyBox wget may try only ::1 for localhost.
        if docker compose exec -T frontend wget -q -T 3 -O /dev/null http://127.0.0.1/api/health; then return 0; fi
        sleep 1
    done
    return 1
}

restore_previous() {
    # Do not partially roll back code when an operator changed secrets/configuration mid-deploy.
    unchanged_config || return
    git switch --detach "$previous" || return
    normalize_source || return
    docker image tag "$previous_image" "$image" || return
    check_config || return
    if (( services_changed )); then
        docker compose up -d --no-deps --force-recreate --wait --wait-timeout 120 backend || return
        docker compose up -d --no-deps --force-recreate --wait --wait-timeout 60 frontend || return
        docker compose exec -T frontend nginx -t || return
        proxy_health || return
    fi
}

recover() {
    local code=$1
    trap - ERR INT TERM
    set +e
    umask 077
    docker compose logs --no-color --tail 100 backend > "$backup/failed-backend.log" 2>&1
    failed_backend=$(docker compose ps --all -q backend 2>/dev/null)
    if [[ -n "$failed_backend" ]]; then
        docker inspect "$failed_backend" --format '{{json .State.Health}}' > "$backup/failed-health.json" 2>/dev/null
    fi
    printf 'Deployment failed; restoring previous code/image (not database contents).\n' >&2
    umask 022
    if restore_previous; then
        printf 'ROLLBACK_OK\n' > "$state/status"
    else
        printf 'ROLLBACK_NEEDS_ATTENTION\n' > "$state/status"
        printf 'Automatic rollback incomplete; inspect the private backup: %s\n' "$backup" >&2
    fi
    exit "$code"
}

main() {
    if [[ $# -lt 1 || $# -gt 2 || ! $1 =~ ^[0-9a-f]{40}$ ]]; then
        printf 'Usage: %s FULL_COMMIT_SHA [LOCAL_GIT_BUNDLE]\nRun from the server checkout; test/review the commit first.\n' "$0" >&2
        exit 2
    fi
    target=$1
    repo=$(git rev-parse --show-toplevel)
    cd "$repo"
    test -z "$(git status --porcelain)" || { echo 'Checkout must be clean' >&2; exit 1; }
    test -f .env && test "$(stat -c %a .env)" = 600 || { echo '.env must exist with mode 0600' >&2; exit 1; }
    state=$(realpath -m "${ALITA_DEPLOY_STATE_DIR:-$repo/../deployments}")
    [[ $state != "$repo" && $state != "$repo/"* ]] || { echo 'Backups must be outside the checkout' >&2; exit 1; }
    umask 077
    install -d -m 700 "$state"
    exec 9> "$state/lock"
    flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
    previous=$(git rev-parse HEAD)
    if [[ $# = 2 ]]; then
        test -f "$2" || { echo 'Bundle must be a local file' >&2; exit 1; }
        (umask 022; git fetch --no-tags "$2" refs/heads/main)
        test "$(git rev-parse FETCH_HEAD)" = "$target" || { echo 'Bundle main does not match requested commit' >&2; exit 1; }
    fi
    git cat-file -e "$target^{commit}"
    git merge-base --is-ancestor "$previous" "$target" || { echo 'Only fast-forward code updates are allowed' >&2; exit 1; }
    test -z "$(git ls-tree --name-only "$target" -- .env .secrets compose.host.yml)" || {
        echo 'Target must not track private host configuration' >&2; exit 1;
    }
    check_config
    backend=$(docker compose ps -q backend)
    test -n "$backend"
    previous_image=$(docker inspect "$backend" --format '{{.Image}}')
    image=$(docker inspect "$backend" --format '{{.Config.Image}}')
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    backup=$(mktemp -d "$state/$stamp-XXXXXX")
    install -m 600 .env "$backup/.env"
    if [[ -f compose.host.yml ]]; then install -m 600 compose.host.yml "$backup/compose.host.yml"; fi
    printf '%s\n' "$previous" > "$backup/revision"
    printf '%s\n' "$previous_image" > "$backup/backend-image"
    printf '%s\n' "$image" > "$backup/image-tag"
    printf '%s\n' "$backup" > "$state/current-backup"
    docker image tag "$previous_image" "research-rag-backend:rollback-$stamp"
    counts > "$backup/counts-before.json"
    printf 'Backup: %s\n' "$backup"
    services_changed=0
    trap 'recover "$?"' ERR
    trap 'recover 130' INT
    trap 'recover 143' TERM
    printf 'RUNNING\n' > "$state/status"
    # Keep .env private, but make Git-created source readable to non-root containers.
    umask 022
    git switch --detach "$target"
    normalize_source
    umask 077
    check_config
    docker compose build backend
    docker run --rm --network none --entrypoint python "$image" -c 'from app.main import app; print("Candidate API import passed")'
    services_changed=1
    docker compose up -d --no-deps --wait --wait-timeout 120 backend
    # Recreate: a reload can retain the old single-file bind-mount inode after Git updates nginx.conf.
    docker compose up -d --no-deps --force-recreate --wait --wait-timeout 60 frontend
    docker compose exec -T frontend nginx -t
    proxy_health
    counts > "$backup/counts-after.json"
    cmp -s "$backup/counts-before.json" "$backup/counts-after.json"
    unchanged_config
    printf 'DEPLOYED\n' > "$state/status"
    trap - ERR INT TERM
    printf 'Deployed %s. Verify public login/read/chat/logout before sharing the release.\n' "$target"
}

# Parse the whole implementation before checkout changes can replace this script on disk.
main "$@"
