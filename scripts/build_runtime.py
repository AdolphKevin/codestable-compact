#!/usr/bin/env python3
"""Build the dependency-free single-file CodeStable runtime and the skill MANIFEST.json."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "skills" / "cs" / "runtime_src"
SKILL_ROOT = ROOT / "skills" / "cs"
TARGET = SKILL_ROOT / "scripts" / "cs_knowledge.py"
BOOTSTRAP = SKILL_ROOT / "scripts" / "bootstrap.py"
SECTION_MARKER = "# CODESTABLE-RUNTIME-SECTION"
SECTIONS = (
    "00_core.py",
    "05_read_view.py",
    "10_capture.py",
    "20_storage.py",
    "30_learning.py",
    "40_retrieval.py",
    "45_validity.py",
    "47_documents.py",
    "50_drift.py",
    "60_governance.py",
    "70_cli.py",
)


def source_bytes() -> bytes:
    digest = hashlib.sha256()
    chunks: list[str] = []
    for index, name in enumerate(SECTIONS):
        path = SOURCE_ROOT / name
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
        if index == 0:
            body = text.rstrip()
        else:
            if SECTION_MARKER not in text:
                raise RuntimeError(f"missing {SECTION_MARKER!r} in {path}")
            body = text.split(SECTION_MARKER, 1)[1].strip()
        chunks.append(body)
    generated = "\n\n".join(chunks).rstrip() + "\n"
    lines = generated.splitlines()
    lines.insert(1, f"# Generated from skills/cs/runtime_src; source-sha256: {digest.hexdigest()}")
    generated = "\n".join(lines) + "\n"
    compile(generated, str(TARGET), "exec")
    return generated.encode("utf-8")


def manifest_bytes() -> bytes:
    """Hash the shipped skill with the same rules the installed bootstrap uses to check itself."""
    spec = importlib.util.spec_from_file_location("codestable_bootstrap_build", BOOTSTRAP)
    assert spec and spec.loader
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    return bootstrap.render_manifest(bootstrap.skill_manifest(SKILL_ROOT, version)).encode("utf-8")


def sync(path: Path, expected: bytes, check: bool) -> bool:
    actual = path.read_bytes() if path.is_file() else b""
    label = path.relative_to(ROOT)
    if check:
        print(f"{'in sync' if actual == expected else 'out of sync'}: {label}")
        return actual == expected
    path.parent.mkdir(parents=True, exist_ok=True)
    if actual != expected:
        path.write_bytes(expected)
    print(f"{'unchanged' if actual == expected else 'updated'}: {label}")
    return True


def build(check: bool) -> int:
    runtime_ok = sync(TARGET, source_bytes(), check)
    # The manifest hashes the runtime, so it is computed only after the runtime is written.
    try:
        manifest = manifest_bytes()
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 1
    manifest_ok = sync(SKILL_ROOT / "MANIFEST.json", manifest, check)
    return 0 if runtime_ok and manifest_ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when the generated runtime or skills/cs/MANIFEST.json is out of sync")
    return build(parser.parse_args(argv).check)


if __name__ == "__main__":
    raise SystemExit(main())
