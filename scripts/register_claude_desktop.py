"""Register this project's MCP server in Claude Desktop's config.

Close Claude Desktop completely first (it rewrites the file while running), then run:
    python scripts/register_claude_desktop.py
"""

import json
import os
import shutil
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SERVER_NAME = "support-triage"


def config_path() -> Path:
    appdata = Path(os.environ["APPDATA"])
    # Microsoft Store / MSIX installs keep their files in a virtualized folder.
    packages = Path(os.environ["LOCALAPPDATA"]) / "Packages"
    for package in packages.glob("Claude_*"):
        candidate = package / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
        if candidate.exists():
            return candidate
    return appdata / "Claude" / "claude_desktop_config.json"


def main() -> None:
    uv = shutil.which("uv")
    if uv is None:
        sys.exit("uv not found on PATH")

    path = config_path()
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault("mcpServers", {})[SERVER_NAME] = {
        "command": uv,
        "args": ["--directory", str(PROJECT_DIR), "run", "python", "-m", "app.mcp_server"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Registered '{SERVER_NAME}' in {path}")
    print("Now start Claude Desktop.")


if __name__ == "__main__":
    main()
