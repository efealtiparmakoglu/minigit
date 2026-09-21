# minigit

**A from-scratch content-addressed version control system in pure Python — blob/tree/commit objects, branches, log. Zero dependencies.**

[![CI](https://github.com/efealtiparmakoglu/minigit/actions/workflows/ci.yml/badge.svg)](https://github.com/efealtiparmakoglu/minigit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org)

```
$ minigit init
$ minigit add a.txt
$ minigit commit "first commit"
[main 3f2a9c1e] first commit
$ minigit branch dev
$ minigit checkout dev
$ minigit log
```

`minigit` implements Git's core storage model itself: content-addressed
objects (SHA-1 of `type size\0content`, zlib-compressed), trees, commits
with parents, and refs. Checkout materializes the target tree into the
working directory. It is a real VCS for single-user use — and a complete
map of how Git works inside.

## Commands

| Command | Behavior |
|---|---|
| `init` | create `.minigit/` object store |
| `add FILE...` | stage files (blobs written, index updated) |
| `commit MSG` | snapshot the index (tree + commit object, ref updated) |
| `log` | walk the commit graph back through parents |
| `status` | staged changes vs HEAD |
| `branch [NAME]` | list branches or create one |
| `checkout NAME` | switch branches, materializing tracked files |
| `cat-file SHA` | print a raw object |

## Development

```sh
python3 -m unittest discover -s tests
```

Tests drive the real CLI in temp directories: full flow (init → add →
commit → log), status staging, branch + checkout with content restoration,
content addressing, object integrity, and cat-file.

## License

MIT — see [LICENSE](LICENSE).
