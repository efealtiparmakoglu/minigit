"""minigit: a from-scratch, content-addressed mini VCS.

Storage model (all under .minigit/):
    objects/<sha>          zlib-compressed "type size\\0content"
    refs/heads/<name>      branch tip sha (text)
    HEAD                   "ref: refs/heads/<name>"

Object types: blob (file content), tree (sorted list of mode sha name),
commit (tree, parent(s), author, message).
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import zlib

ROOT_NAME = ".minigit"


def find_root() -> str:
    d = os.getcwd()
    while True:
        candidate = os.path.join(d, ROOT_NAME)
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit("minigit: not a repository (run 'minigit init')")
        d = parent


def obj_path(root: str, sha: str) -> str:
    return os.path.join(root, "objects", sha)


def hash_object(root: str, data: bytes, kind: str, write: bool = True) -> str:
    header = f"{kind} {len(data)}\0".encode()
    full = header + data
    sha = hashlib.sha1(full).hexdigest()
    if write:
        path = obj_path(root, sha)
        if not os.path.exists(path):
            with open(path, "wb") as fh:
                fh.write(zlib.compress(full))
    return sha


def read_object(root: str, sha: str) -> tuple[str, bytes]:
    path = obj_path(root, sha)
    if not os.path.exists(path):
        raise SystemExit(f"minigit: object {sha[:8]} not found")
    full = zlib.decompress(open(path, "rb").read())
    header, _, content = full.partition(b"\0")
    kind, size = header.decode().split()
    if int(size) != len(content):
        raise SystemExit(f"minigit: corrupt object {sha[:8]}")
    return kind, content


# --------------------------------------------------------------- commands


def cmd_init(args: list[str]) -> None:
    root = os.path.join(os.getcwd(), ROOT_NAME)
    if os.path.isdir(root):
        print("minigit: repository already exists")
        return
    for sub in ("objects", "refs/heads"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    with open(os.path.join(root, "HEAD"), "w") as fh:
        fh.write("ref: refs/heads/main\n")
    print(f"initialized empty repository in {root}")


def _index_path(root: str) -> str:
    return os.path.join(root, "index")


def _load_index(root: str) -> dict[str, str]:
    path = _index_path(root)
    entries: dict[str, str] = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            sha, name = line.rstrip("\n").split("\t", 1)
            entries[name] = sha
    return entries


def _save_index(root: str, entries: dict[str, str]) -> None:
    with open(_index_path(root), "w", encoding="utf-8") as fh:
        for name in sorted(entries):
            fh.write(f"{entries[name]}\t{name}\n")


def cmd_add(args: list[str]) -> None:
    root = find_root()
    entries = _load_index(root)
    for arg in args:
        if os.path.isdir(arg):
            for base, _, files in os.walk(arg):
                if ROOT_NAME in base:
                    continue
                for f in files:
                    p = os.path.join(base, f)
                    _add_file(root, entries, p)
        elif os.path.isfile(arg):
            _add_file(root, entries, arg)
        else:
            raise SystemExit(f"minigit: {arg}: no such file")
    _save_index(root, entries)


def _add_file(root: str, entries: dict[str, str], path: str) -> None:
    data = open(path, "rb").read()
    sha = hash_object(root, data, "blob")
    rel = os.path.relpath(path)
    entries[rel] = sha


def _write_tree(root: str, entries: dict[str, str]) -> str:
    items = []
    for name in sorted(entries):
        items.append(f"blob {entries[name]}\t{name}")
    return hash_object(root, "\n".join(items).encode(), "tree")


def _read_tree(root: str, sha: str) -> dict[str, str]:
    kind, content = read_object(root, sha)
    assert kind == "tree"
    entries: dict[str, str] = {}
    for line in content.decode().splitlines():
        meta, name = line.split("\t", 1)
        _, sha = meta.split()
        entries[name] = sha
    return entries


def cmd_commit(args: list[str]) -> None:
    root = find_root()
    msg = args[0] if args else _editor_message()
    entries = _load_index(root)
    tree = _write_tree(root, entries)
    head_ref = _head_ref(root)
    parent = _resolve_ref(root, head_ref)
    author = os.environ.get("GIT_AUTHOR_NAME", "minigit")
    ts = int(time.time())
    body = f"tree {tree}\n"
    if parent:
        body += f"parent {parent}\n"
    body += f"author {author} {ts}\n\n{msg}\n"
    sha = hash_object(root, body.encode(), "commit")
    _update_ref(root, head_ref, sha)
    print(f"[{head_ref.split('/')[-1]} {sha[:8]}] {msg.splitlines()[0] if msg else ''}")


def _editor_message() -> str:
    import tempfile
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as fh:
        fh.write("\n")
        fh.flush()
        editor = os.environ.get("EDITOR", "vi")
        os.system(f"{editor} {fh.name}")
        fh.seek(0)
        msg = fh.read().strip()
        os.unlink(fh.name)
    return msg


def cmd_log(args: list[str]) -> None:
    root = find_root()
    ref = _head_ref(root)
    sha = _resolve_ref(root, ref)
    while sha:
        kind, content = read_object(root, sha)
        assert kind == "commit"
        lines = content.decode().splitlines()
        tree_line = next(l for l in lines if l.startswith("tree "))
        parents = [l.split()[1] for l in lines if l.startswith("parent ")]
        msg_start = content.decode().find("\n\n") + 2
        msg = content.decode()[msg_start:].strip()
        print(f"commit {sha}")
        print(f"tree   {tree_line.split()[1]}")
        for p in parents:
            print(f"parent {p}")
        print()
        for line in msg.splitlines():
            print(f"    {line}")
        print()
        sha = parents[0] if parents else None


def cmd_status(args: list[str]) -> None:
    root = find_root()
    entries = _load_index(root)
    ref = _head_ref(root)
    sha = _resolve_ref(root, ref)
    head_tree = _read_tree(root, _commit_tree(root, sha)) if sha else {}
    staged = [n for n, s in entries.items() if head_tree.get(n) != s]
    print(f"On branch {ref.split('/')[-1]}")
    if staged:
        print("Changes to be committed:")
        for n in sorted(staged):
            status = "new file" if n not in head_tree else "modified"
            print(f"  {status}: {n}")
    if not staged:
        print("nothing staged")


def cmd_branch(args: list[str]) -> None:
    root = find_root()
    if not args:
        for head in sorted(os.listdir(os.path.join(root, "refs/heads"))):
            marker = "* " if _head_ref(root).endswith("/" + head) else "  "
            print(f"{marker}{head}")
        return
    name = args[0]
    sha = _resolve_ref(root, _head_ref(root))
    if not sha:
        raise SystemExit("minigit: cannot branch from empty commit")
    with open(os.path.join(root, "refs/heads", name), "w") as fh:
        fh.write(sha)
    print(f"branch {name} created")


def cmd_checkout(args: list[str]) -> None:
    root = find_root()
    name = args[0]
    ref_path = os.path.join(root, "refs/heads", name)
    if not os.path.exists(ref_path):
        raise SystemExit(f"minigit: branch {name!r} not found")
    sha = open(ref_path).read().strip()
    tree = _read_tree(root, _commit_tree(root, sha))
    # materialize tracked files from the target tree
    for fname, blob_sha in tree.items():
        _, content = read_object(root, blob_sha)
        dirname = os.path.dirname(fname)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(fname, "wb") as fh:
            fh.write(content)
    # reset index to the target tree
    _save_index(root, tree)
    with open(os.path.join(root, "HEAD"), "w") as fh:
        fh.write(f"ref: refs/heads/{name}\n")
    print(f"switched to branch {name!r}")


def _head_ref(root: str) -> str:
    head = open(os.path.join(root, "HEAD")).read().strip()
    if head.startswith("ref: "):
        return head[5:]
    return head


def _resolve_ref(root: str, ref: str) -> str | None:
    path = os.path.join(root, ref)
    if os.path.exists(path):
        return open(path).read().strip()
    return None


def _update_ref(root: str, ref: str, sha: str) -> None:
    path = os.path.join(root, ref)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(sha)


def _commit_tree(root: str, sha: str | None) -> str:
    if not sha:
        return ""
    kind, content = read_object(root, sha)
    for line in content.decode().splitlines():
        if line.startswith("tree "):
            return line.split()[1]
    return ""


def cmd_cat_file(args: list[str]) -> None:
    if len(args) != 1:
        raise SystemExit("minigit: cat-file needs a sha")
    root = find_root()
    kind, content = read_object(root, args[0])
    sys.stdout.buffer.write(content)


COMMANDS = {
    "init": cmd_init,
    "add": cmd_add,
    "commit": cmd_commit,
    "log": cmd_log,
    "status": cmd_status,
    "branch": cmd_branch,
    "checkout": cmd_checkout,
    "cat-file": cmd_cat_file,
}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print("minigit 1.0.0\n\nCOMMANDS:", ", ".join(sorted(COMMANDS)))
        return 0
    cmd = args[0]
    fn = COMMANDS.get(cmd)
    if not fn:
        print(f"minigit: unknown command {cmd!r}", file=sys.stderr)
        return 2
    fn(args[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
