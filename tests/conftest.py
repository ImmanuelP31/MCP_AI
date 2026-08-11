import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("ENVIRONMENT", "test")
os.environ["GITHUB_TOKEN"] = ""  # nosec B105

SOURCE_ROOTS = [
    ROOT / "apps" / "api" / "src",
    ROOT / "packages" / "auth" / "src",
    ROOT / "packages" / "common" / "src",
    ROOT / "packages" / "mcp" / "src",
    ROOT / "packages" / "observability" / "src",
    ROOT / "packages" / "policy" / "src",
    ROOT / "packages" / "schemas" / "src",
    ROOT / "services" / "device-mcp" / "src",
    ROOT / "services" / "diagnostics-mcp" / "src",
    ROOT / "services" / "ai-agent" / "src",
    ROOT / "services" / "knowledge-mcp" / "src",
    ROOT / "services" / "mcp-gateway" / "src",
    ROOT / "services" / "repository-mcp" / "src",
    ROOT / "services" / "simulator-gateway" / "src",
    ROOT / "services" / "ticket-mcp" / "src",
]

for source_root in SOURCE_ROOTS:
    sys.path.insert(0, str(source_root))


def isolated_database_path(name: str) -> Path:
    database_dir = ROOT / "logs" / "test-databases"
    database_dir.mkdir(parents=True, exist_ok=True)
    database_path = database_dir / name
    if database_path.exists():
        database_path.unlink()
    return database_path
