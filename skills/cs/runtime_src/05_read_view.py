"""Read a Git index or commit without checking out or writing any files."""

from __future__ import annotations

# CODESTABLE-RUNTIME-SECTION
from contextlib import contextmanager
from contextvars import ContextVar
from fnmatch import fnmatchcase


class GitReadView:
    def __init__(self, root: Path, revision: str):
        self.root = root
        self.revision = revision
        self.files: dict[str, tuple[str, str]] = {}
        self.directories = {"."}
        self.contents: dict[str, bytes] = {}
        arguments = ["ls-files", "--stage", "-z"] if revision == ":" else ["ls-tree", "-r", "-z", "--full-tree", revision]
        for entry in run_git(root, arguments).stdout.split("\0"):
            if not entry:
                continue
            header, path = entry.split("\t", 1)
            mode, middle, last = header.split()
            if revision == ":":
                if last != "0":
                    raise KnowledgeError(f"unmerged Git index entry: {path}")
                oid = middle
            else:
                oid = last
            self.files[path] = (mode, oid)
            self.directories.update(str(parent) for parent in PurePosixPath(path).parents)

    def relative(self, path: Path) -> str | None:
        try:
            return path.absolute().relative_to(self.root).as_posix()
        except ValueError:
            return None

    def read(self, relative: str) -> bytes:
        record = self.files.get(relative)
        if record is None:
            raise FileNotFoundError(relative)
        mode, oid = record
        if mode not in {"100644", "100755"}:
            raise KnowledgeError(f"Git snapshot cannot read a symlink or submodule as a regular file: {relative}")
        if oid not in self.contents:
            process = subprocess.run(["git", "cat-file", "blob", oid], cwd=self.root, capture_output=True, check=False)
            if process.returncode:
                raise KnowledgeError(f"cannot read Git blob for {relative}")
            self.contents[oid] = process.stdout
        return self.contents[oid]


READ_VIEW: ContextVar[GitReadView | None] = ContextVar("codestable_read_view", default=None)


@contextmanager
def git_read_view(root: Path, revision: str):
    token = READ_VIEW.set(GitReadView(root, revision))
    try:
        yield
    finally:
        READ_VIEW.reset(token)


def viewed_path(path: Path) -> tuple[GitReadView | None, str | None]:
    view = READ_VIEW.get()
    relative = view.relative(path) if view else None
    return (view, relative) if relative is not None else (None, None)


def source_bytes(path: Path) -> bytes:
    view, relative = viewed_path(path)
    return view.read(relative) if view is not None else path.read_bytes()


def source_text(path: Path, encoding: str = "utf-8", errors: str = "strict") -> str:
    return source_bytes(path).decode(encoding, errors)


def source_is_file(path: Path) -> bool:
    view, relative = viewed_path(path)
    return view.files.get(relative, ("", ""))[0] in {"100644", "100755"} if view else path.is_file()


def source_is_dir(path: Path) -> bool:
    view, relative = viewed_path(path)
    return relative in view.directories if view else path.is_dir()


def source_exists(path: Path) -> bool:
    view, relative = viewed_path(path)
    return relative in view.files or relative in view.directories if view else path.exists()


def source_size(path: Path) -> int:
    view, relative = viewed_path(path)
    return len(view.read(relative)) if view else path.stat().st_size


def source_glob(path: Path, pattern: str, recursive: bool = False) -> Iterator[Path]:
    view, relative = viewed_path(path)
    if view is None:
        yield from (path.rglob(pattern) if recursive else path.glob(pattern))
        return
    prefix = "" if relative == "." else relative + "/"
    for value in sorted(set(view.files) | view.directories):
        if not value.startswith(prefix) or value == relative:
            continue
        tail = value[len(prefix):]
        if (recursive or "/" not in tail) and fnmatchcase(PurePosixPath(tail).name, pattern):
            yield view.root / value


def source_children(path: Path) -> Iterator[Path]:
    yield from source_glob(path, "*")
