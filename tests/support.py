from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = PACKAGE_ROOT / "skills" / "cs" / "scripts" / "bootstrap.py"
ASSET_ROOT = PACKAGE_ROOT / "skills" / "cs" / "assets" / "project"
ASSET_TOOL = ASSET_ROOT / ".codestable" / "tools" / "cs_knowledge.py"


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def bootstrap_module() -> ModuleType:
    return load_module(BOOTSTRAP_PATH, "codestable_bootstrap_test")


def knowledge_module() -> ModuleType:
    return load_module(ASSET_TOOL, "codestable_knowledge_test")


def run_tool(root: Path, *args: str, check: bool = True, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(root / ".codestable" / "tools" / "cs_knowledge.py"), "--root", str(root), *args]
    return subprocess.run(command, input=stdin, text=True, capture_output=True, check=check)


def json_output(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    data = json.loads(process.stdout)
    assert isinstance(data, dict)
    return data


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_payload(root: Path, payload: dict[str, Any], name: str = "learning.json") -> Path:
    path = root / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def base_task(title: str = "订单任务") -> dict[str, Any]:
    return {
        "title": title,
        "kind": "issue",
        "status": "completed",
        "request": "修复订单创建异常",
        "summary": "完成了订单创建路径的修复。",
        "result": "异常路径不再产生部分成功状态。",
        "paths": ["src/orders/service.py"],
        "symbols": ["OrderService.create"],
        "tags": ["orders"],
        "verification": ["python3 -m unittest tests.test_orders"],
        "source": {"issue": "ORDER-17"},
    }
