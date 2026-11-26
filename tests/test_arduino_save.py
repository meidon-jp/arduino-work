"""実NeovimのRPC連携。全ファイル・ソケットは一時ディレクトリ内。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


HELPER = Path(__file__).resolve().parents[1] / "bin" / "arduino-save.lua"


@unittest.skipUnless(shutil.which("nvim"), "Neovimが必要")
class EditorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arduino-save-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.sketch = self.root / "日本語 sketch"
        self.sketch.mkdir()
        self.source = self.sketch / "test.ino"
        self.source.write_text("old\n")
        self.other = self.root / "unrelated.cpp"
        self.other.write_text("unrelated\n")
        self.env = dict(os.environ, XDG_RUNTIME_DIR=str(self.root), NVIM_LOG_FILE=str(self.root / "nvim.log"))

    def editor(self):
        before = set(self.root.glob("**/nvim.*.0"))
        process = subprocess.Popen(["nvim", "--headless", "-u", "NONE", "-i", "NONE", "-n"],
                                   env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def stop():
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self.addCleanup(stop)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            new = set(self.root.glob("**/nvim.*.0")) - before
            if new:
                return str(new.pop())
            time.sleep(0.03)
        self.fail("Neovimのテスト用ソケットを作成できません")

    def lua(self, server, code):
        expr = "luaeval(" + json.dumps(code, ensure_ascii=False) + ")"
        return subprocess.run(["nvim", "--server", server, "--remote-expr", expr],
                              capture_output=True, text=True, env=self.env, timeout=3, check=True)

    def modify(self, server, path, value):
        self.lua(server, "(function() vim.cmd.edit(" + json.dumps(str(path), ensure_ascii=False)
                 + "); vim.api.nvim_buf_set_lines(0, 0, -1, false, {"
                 + json.dumps(value) + "}); return true end)()")

    def save(self):
        result = subprocess.run(["nvim", "--headless", "-u", "NONE", "-i", "NONE", "-n",
                                 "-l", str(HELPER), str(self.sketch)],
                                capture_output=True, text=True, env=self.env, timeout=5, check=True)
        return json.loads(result.stdout)

    def test_discovers_editor_and_saves_only_sketch_sources(self):
        server = self.editor()
        self.modify(server, self.source, "new")
        self.lua(server, "(function() vim.o.hidden = true; return true end)()")
        self.modify(server, self.other, "do not save")
        result = self.save()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["saved"], 1)
        self.assertEqual(self.source.read_text(), "new\n")
        self.assertEqual(self.other.read_text(), "unrelated\n")

    def test_duplicate_unsaved_buffers_abort_without_writing(self):
        first, second = self.editor(), self.editor()
        self.modify(first, self.source, "first")
        self.modify(second, self.source, "second")
        result = self.save()
        self.assertFalse(result["ok"], result)
        self.assertIn("複数", result["error"])
        self.assertEqual(self.source.read_text(), "old\n")

    def test_readonly_stops_save(self):
        server = self.editor()
        self.modify(server, self.source, "new")
        self.lua(server, "(function() vim.bo.readonly = true; return true end)()")
        self.assertFalse(self.save()["ok"])
        self.assertEqual(self.source.read_text(), "old\n")

    def test_no_editor_is_ok(self):
        result = self.save()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["saved"], 0)

    def test_new_header_is_saved(self):
        server = self.editor()
        header = self.sketch / "new.h"
        self.modify(server, header, "#pragma once")
        self.assertTrue(self.save()["ok"])
        self.assertEqual(header.read_text(), "#pragma once\n")

    def test_external_disk_change_is_not_overwritten(self):
        server = self.editor()
        self.modify(server, self.source, "editor")
        self.source.write_text("external change\n")
        # Neovimが記録している読み込み時刻と確実に区別する。
        stamp = time.time() + 2
        os.utime(self.source, (stamp, stamp))
        self.assertFalse(self.save()["ok"])
        self.assertEqual(self.source.read_text(), "external change\n")
