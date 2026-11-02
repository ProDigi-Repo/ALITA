#!/usr/bin/env bash
# Set-up on a fresh Oracle Cloud VM (Ubuntu 24.04, ARM/Ampere A1). Run in the project folder:
#   cd ~/research-rag && bash deploy/oracle/setup.sh
# Can be run several times: what already exists is skipped.
set -euo pipefail
cd "$(dirname "$0")/../.."
echo "== ALITA auf Oracle Cloud: $(pwd)"

# 1) Docker Engine + Compose plugin from the official Docker repository
if ! command -v docker >/dev/null 2>&1; then
  echo "== Docker installieren"
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
  echo "   Docker installiert. Nach dem Skript einmal ab- und wieder anmelden (dann geht docker ohne sudo)."
fi

# 2) swap (4 GB) as a buffer while building the backend image
if ! sudo swapon --show | grep -q /swapfile; then
  echo "== Swap 4 GB anlegen"
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# 3) .env for the server
if [ ! -f .env ]; then cp .env.example .env; echo "== .env aus .env.example angelegt"; fi
setkey() {  # setkey NAME VALUE  (only if not set yet)
  if ! grep -q "^$1=" .env; then echo "$1=$2" >> .env; echo "   $1 gesetzt"; fi
}
setkey COMPOSE_FILE "docker-compose.yml:deploy/oracle/docker-compose.oracle.yml"
if grep -Eq '^NEO4J_PASSWORD=(alita-neo4j)?$' .env && ! docker volume ls 2>/dev/null | grep -q neo4j_data; then
  sed -i "s/^NEO4J_PASSWORD=.*/NEO4J_PASSWORD=$(openssl rand -hex 16)/" .env; echo "   NEO4J_PASSWORD zufällig gesetzt"
fi
setkey NEO4J_PASSWORD "$(openssl rand -hex 16)"
setkey RESEARCH_DIR "./research"
setkey WITH_LIBREOFFICE "true"
if ! grep -q '^CLOUDFLARE_TUNNEL_TOKEN=.\+' .env; then
  sed -i '/^CLOUDFLARE_TUNNEL_TOKEN=/d' .env
  echo "CLOUDFLARE_TUNNEL_TOKEN=" >> .env
  echo
  echo "!! Noch offen: CLOUDFLARE_TUNNEL_TOKEN in .env eintragen (nano .env), dann:"
  echo "   docker compose up -d --build"
  exit 0
fi
mkdir -p migrate research

# 4) start
SUDO=""; docker info >/dev/null 2>&1 || SUDO="sudo"
$SUDO docker compose up -d --build
echo
echo "== Läuft. Status: docker compose ps"
echo "   Index vom alten Rechner einspielen (Ordner ./migrate): docker compose run --rm migrate import"
