#!/usr/bin/env python3
"""Build the dependency-free single-file CodeStable runtime from maintenance sections."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "skills" / "cs" / "runtime_src"
TARGET = ROOT / "skills" / "cs" / "assets" / "project" / ".codestable" / "tools" / "cs_knowledge.py"
SECTION_MARKER = "# CODESTABLE-RUNTIME-SECTION"
SECTIONS = (
    "00_core.py",
    "10_capture.py",
    "20_storage.py",
    "30_learning.py",
    "40_retrieval.py",
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


def build(check: bool) -> int:
    expected = source_bytes()
    actual = TARGET.read_bytes() if TARGET.is_file() else b""
    if check:
        if actual != expected:
            print(f"out of sync: {TARGET.relative_to(ROOT)}")
            return 1
        print(f"in sync: {TARGET.relative_to(ROOT)}")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if actual != expected:
        TARGET.write_bytes(expected)
        print(f"updated: {TARGET.relative_to(ROOT)}")
    else:
        print(f"unchanged: {TARGET.relative_to(ROOT)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when the generated runtime differs from maintenance sources")
    return build(parser.parse_args(argv).check)


if __name__ == "__main__":
    raise SystemExit(main())
