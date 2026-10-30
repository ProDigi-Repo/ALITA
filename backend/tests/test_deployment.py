"""Check the effective production Compose configuration, not just the override text."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("small_vm", [False, True])
def test_hetzner_compose_has_no_origin_bypass(small_vm):
    if not shutil.which("docker") or subprocess.run(["docker", "compose", "version"], capture_output=True).returncode:
        pytest.skip("Docker Compose not installed")
    env = dict(os.environ, NEO4J_PASSWORD="test-password-not-for-deployment", ACCESS_ENABLED="false",
               ACCESS_TEAM_DOMAIN="alita-test.cloudflareaccess.com", ACCESS_AUDIENCE="test-audience",
               PUBLIC_ORIGIN="https://alita.example.org", ADMIN_EMAILS="admin@example.org")
    files = ["-f", "docker-compose.yml", "-f", "deploy/hetzner/docker-compose.hetzner.yml"]
    if small_vm:
        files += ["-f", "deploy/hetzner/docker-compose.4gb.yml"]
    result = subprocess.run(["docker", "compose", "--env-file", "/dev/null", *files,
                             "--profile", "*", "config", "--format", "json"],
                            cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    services = json.loads(result.stdout)["services"]
    assert all(not service.get("ports") for service in services.values())
    assert services["backend"]["environment"]["ACCESS_ENABLED"] == "true"
    assert services["backend"]["environment"]["NEO4J_PASSWORD"] == env["NEO4J_PASSWORD"]
    assert "seed" in services["seed"]["profiles"]
    assert set(services["cloudflared"]["networks"]) == {"edge"}
    assert set(services["frontend"]["networks"]) == {"edge", "app"}
    for service in ["neo4j", "qdrant"]:
        assert set(services[service]["networks"]) == {"data"}
    assert services["cloudflared"]["secrets"][0]["source"] == "cloudflare_tunnel_token"
    if small_vm:
        mib = 1024 * 1024
        limits = {"backend": (1280, 2048), "neo4j": (1152, 1536), "qdrant": (1024, 1536),
                  "frontend": (96, 96), "cloudflared": (128, 192), "ingest": (1280, 2048),
                  "migrate": (768, 1024), "seed": (1280, 2048)}
        for name, (memory, swap) in limits.items():
            assert int(services[name]["mem_limit"]) == memory * mib
            assert int(services[name]["memswap_limit"]) == swap * mib
        assert services["qdrant"]["ulimits"]["nofile"] == {"soft": 65536, "hard": 65536}
        assert services["qdrant"]["environment"]["QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS"] == "1"
        assert services["backend"]["command"][-4:] == ["--workers", "1", "--limit-concurrency", "8"]
        for name in ("backend", "ingest"):
            assert services[name]["environment"]["OPENBLAS_NUM_THREADS"] == "1"
        neo4j = services["neo4j"]["environment"]
        assert neo4j["NEO4J_server_memory_heap_max__size"] == "512M"
        assert neo4j["NEO4J_server_memory_pagecache_size"] == "256M"
