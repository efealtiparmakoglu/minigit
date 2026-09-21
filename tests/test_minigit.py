import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def run(workdir: str, *args: str, expect: int = 0) -> str:
    result = subprocess.run(
        [PY, os.path.join(ROOT, "minigit.py"), *args],
        cwd=workdir, capture_output=True, text=True,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"minigit {args} exit {result.returncode} (want {expect}):\n{result.stderr}")
    return result.stdout


class TestMiniGit(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp(prefix="minigit-test-")
        os.chdir(self.dir)

    def tearDown(self):
        os.chdir("/tmp")

    def test_full_flow(self):
        run(self.dir, "init")
        assert os.path.isdir(os.path.join(self.dir, ".minigit"))

        with open("a.txt", "w") as fh:
            fh.write("hello v1\n")
        run(self.dir, "add", "a.txt")
        run(self.dir, "commit", "first commit")

        with open("b.txt", "w") as fh:
            fh.write("file two\n")
        run(self.dir, "add", "b.txt")
        run(self.dir, "add", "a.txt")
        run(self.dir, "commit", "second commit")

        log = run(self.dir, "log")
        assert "first commit" in log
        assert "second commit" in log
        assert log.count("commit ") == 2

    def test_status_staging(self):
        run(self.dir, "init")
        with open("x.txt", "w") as fh:
            fh.write("data\n")
        run(self.dir, "add", "x.txt")
        out = run(self.dir, "status")
        assert "new file: x.txt" in out

    def test_branch_and_checkout(self):
        run(self.dir, "init")
        with open("f.txt", "w") as fh:
            fh.write("base\n")
        run(self.dir, "add", "f.txt")
        run(self.dir, "commit", "base")

        run(self.dir, "branch", "dev")
        out = run(self.dir, "branch")
        assert "* main" in out and "dev" in out

        run(self.dir, "checkout", "dev")
        with open("f.txt", "a") as fh:
            fh.write("dev change\n")
        run(self.dir, "add", "f.txt")
        run(self.dir, "commit", "dev work")

        run(self.dir, "checkout", "main")
        with open("f.txt") as fh:
            assert fh.read() == "base\n"

    def test_object_store_content_addressed(self):
        run(self.dir, "init")
        with open("same.txt", "w") as fh:
            fh.write("identical\n")
        run(self.dir, "add", "same.txt")
        run(self.dir, "commit", "with tree")
        objs = os.listdir(os.path.join(self.dir, ".minigit", "objects"))
        assert len(objs) >= 3  # blob + tree + commit

    def test_not_a_repository(self):
        result = subprocess.run(
            [PY, os.path.join(ROOT, "minigit.py"), "status"],
            cwd=self.dir, capture_output=True, text=True)
        assert result.returncode != 0
        assert "not a repository" in result.stderr

    def test_cat_file(self):
        run(self.dir, "init")
        with open("f.txt", "w") as fh:
            fh.write("content bytes\n")
        run(self.dir, "add", "f.txt")
        # find the blob via index
        idx = open(os.path.join(self.dir, ".minigit", "index")).read()
        sha = idx.split("\t")[0].strip()
        out = subprocess.run(
            [PY, os.path.join(ROOT, "minigit.py"), "cat-file", sha],
            cwd=self.dir, capture_output=True)
        assert out.stdout == b"content bytes\n"


if __name__ == "__main__":
    unittest.main()
