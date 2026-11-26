import importlib.machinery
import importlib.util
import json
import curses
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch, Mock


loader = importlib.machinery.SourceFileLoader(
    "arduino_work", str(Path(__file__).resolve().parents[1] / "bin" / "arduino-work"))
spec = importlib.util.spec_from_loader(loader.name, loader)
work = importlib.util.module_from_spec(spec)
loader.exec_module(work)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.sketch = self.root / "folder with spaces" / "Blink"
        self.sketch.mkdir(parents=True)
        (self.sketch / "Blink.ino").write_text("void setup() {}\nvoid loop() {}\n")
        self.app = work.ArduinoWork(self.root, cli="fake-cli")
        saver = patch.object(self.app, "save_editors")
        self.save_editors = saver.start()
        self.addCleanup(saver.stop)
        self.app.select_sketch(self.sketch)
        self.app.settings.update(fqbn="arduino:avr:uno", baud=9600,
                                 port={"address": "/dev/test", "protocol": "serial"})

    def test_settings_survive_restart_and_sketch_switch(self):
        self.app.save()
        app = work.ArduinoWork(self.root, cli="fake-cli")
        self.assertEqual(app.settings["baud"], 9600)
        with patch("builtins.input", return_value="Other"):
            app.new_sketch()
        self.assertEqual(app.settings["baud"], 9600)
        self.assertEqual(app.settings["port"]["address"], "/dev/test")
        app.select_sketch(self.sketch)
        self.assertEqual(app.settings["fqbn"], "arduino:avr:uno")

    def test_old_settings_migrate_from_current_sketch(self):
        self.app.state_file.write_text(json.dumps({"current": str(self.sketch),
            "sketches": {str(self.sketch): {"baud": 9600, "fqbn": "arduino:avr:uno"}}}))
        app = work.ArduinoWork(self.root, cli="fake-cli")
        self.assertEqual(app.settings, {"baud": 9600, "fqbn": "arduino:avr:uno"})
        self.assertNotIn("settings", json.loads(app.state_file.read_text()))

    def test_save_failure_prevents_build(self):
        self.save_editors.side_effect = RuntimeError("save failed")
        with patch.object(self.app, "cli_run") as cli:
            with self.assertRaisesRegex(RuntimeError, "save failed"):
                self.app.build()
        cli.assert_not_called()

    def test_build_does_not_require_port_and_keeps_path_one_argument(self):
        with patch.object(self.app, "cli_run") as cli, patch.object(self.app, "ports") as ports:
            self.app.build()
        ports.assert_not_called()
        self.assertEqual(cli.call_args.args[-1], str(self.sketch))
        self.assertNotIn("--upload", cli.call_args.args)

    def test_failed_upload_never_opens_monitor(self):
        with patch.object(self.app, "port_args", return_value=["--port", "/dev/test"]), \
                patch.object(self.app, "cli_run", side_effect=RuntimeError("compile failed")), \
                patch.object(self.app, "monitor") as monitor:
            with self.assertRaises(RuntimeError):
                self.app.build(upload=True, monitor=True)
        monitor.assert_not_called()

    def test_upload_then_monitor(self):
        with patch.object(self.app, "port_args", return_value=["--port", "/dev/test"]), \
                patch.object(self.app, "cli_run") as cli:
            self.app.build(upload=True, monitor=True)
        calls = [c.args for c in cli.call_args_list]
        self.assertEqual([c[0] for c in calls], ["compile", "upload", "monitor"])
        output = calls[0][calls[0].index("--output-dir") + 1]
        self.assertEqual(calls[1][calls[1].index("--input-dir") + 1], output)
        self.assertFalse(Path(output).exists())
        self.assertIn("baudrate=9600", calls[2])

    def run_job(self, code, cancel=False):
        ui = work.TerminalUI(self.app)
        frames, processes = [], []
        class Screen:
            def timeout(self, value):
                pass
            def get_wch(self):
                if cancel:
                    return "q"
                if frames and frames[-1] is not None:
                    return "\n"
                time.sleep(0.001)
                raise curses.error()
        def frame(screen, phase, started, logs, result=None, *args, **kwargs):
            frames.append(result)
        original = subprocess.Popen
        def spawn(*args, **kwargs):
            process = original(*args, **kwargs)
            processes.append(process)
            return process
        self.job_processes = processes
        with patch.object(ui, "start"), patch.object(ui, "job_frame", side_effect=frame), \
                patch.object(work.curses, "wrapper", side_effect=lambda run: run(Screen())), \
                patch.object(work.subprocess, "Popen", side_effect=spawn):
            ui.job([sys.executable, "-c", code], "upload")
        return frames

    def test_animated_job_reports_real_success(self):
        frames = self.run_job("print('complete')")
        self.assertEqual(frames[-1], 0)
        self.assertEqual(self.job_processes[0].poll(), 0)

    def test_animated_job_reports_failure(self):
        with self.assertRaisesRegex(RuntimeError, "bad firmware"):
            self.run_job("print('bad firmware'); raise SystemExit(2)")
        self.assertEqual(self.job_processes[0].poll(), 2)

    def test_animated_job_cancellation_reaps_process(self):
        with self.assertRaises(work.Cancelled):
            self.run_job("import time; time.sleep(60)", cancel=True)
        self.assertIsNotNone(self.job_processes[0].poll())
        self.assertTrue(self.job_processes[0].stdout.closed)

    def test_serial_receives_and_sends_text(self):
        ui = work.TerminalUI(self.app)
        ui.colors = [0, 0, 0, 0]
        rendered = []
        keys = iter(["h", "i", "\n"])
        class Screen:
            def keypad(self, value): pass
            def timeout(self, value): pass
            def getmaxyx(self): return (24, 80)
            def erase(self): pass
            def refresh(self): pass
            def addstr(self, y, x, text, style): rendered.append(text)
            def get_wch(self):
                if any("reply:hi" in s for s in rendered): return "\x1b"
                time.sleep(0.01)
                try: return next(keys)
                except StopIteration: raise curses.error()
        script = "import sys; print('ready',flush=True); s=input(); print('reply:'+s,flush=True)"
        with patch.object(ui, "start"), patch.object(work.curses, "wrapper", side_effect=lambda run: run(Screen())):
            ui.serial([sys.executable, "-u", "-c", script])
        self.assertTrue(any("reply:hi" in line for line in rendered))
        self.assertTrue(any("受信！" in line for line in rendered))

    def test_disappeared_port_is_not_silently_replaced(self):
        with patch.object(self.app, "ports", return_value=[
                {"port": {"address": "/dev/other", "protocol": "serial"}}]), \
                patch.object(self.app, "select_port", side_effect=work.Cancelled):
            with self.assertRaises(work.Cancelled):
                self.app.port_args()

    def test_existing_port_is_reused(self):
        with patch.object(self.app, "ports", return_value=[{"port": self.app.settings["port"]}]):
            self.assertEqual(self.app.port_args(), ["--port", "/dev/test", "--protocol", "serial"])

    def test_board_options_come_from_cli(self):
        data = [{"boards": [{"name": "Nano", "fqbn": "arduino:avr:nano"}]},
                {"config_options": [{"option": "cpu", "option_label": "Processor", "values": [
                    {"value_label": "Old Bootloader", "value": "atmega328old"}]}]}]
        with patch.object(self.app, "cli_run", side_effect=data), \
                patch("builtins.input", side_effect=["Nano", "1", "1"]):
            self.app.select_board()
        self.assertEqual(self.app.settings["fqbn"], "arduino:avr:nano:cpu=atmega328old")

    def test_cancel_board_options_keeps_previous_selection(self):
        data = [{"boards": [{"name": "Nano", "fqbn": "arduino:avr:nano"}]},
                {"config_options": [{"option": "cpu", "option_label": "Processor", "values": [
                    {"value_label": "Old", "value": "old"}]}]}]
        with patch.object(self.app, "cli_run", side_effect=data), \
                patch("builtins.input", side_effect=["Nano", "1", ""]):
            with self.assertRaises(work.Cancelled):
                self.app.select_board()
        self.assertEqual(self.app.settings["fqbn"], "arduino:avr:uno")

    def test_bad_settings_are_not_overwritten(self):
        self.app.state_file.write_text('{"current": 42}')
        with self.assertRaises(ValueError):
            work.ArduinoWork(self.root, cli="fake-cli")
        self.assertEqual(json.loads(self.app.state_file.read_text()), {"current": 42})

    def screen(self, keys, size=(30, 110)):
        class Screen:
            def timeout(self, value):
                pass

            def getmaxyx(self):
                return size

            def erase(self):
                pass

            def refresh(self):
                pass

            def addstr(self, y, x, text, style):
                assert 0 <= y < size[0]
                assert 0 <= x < size[1]

            def get_wch(self):
                return next(iterator)
        iterator = iter(keys)
        return Screen()

    def ui_call(self, method, keys, *args, size=(30, 110), **kwargs):
        ui = work.TerminalUI(self.app)
        ui.colors = [0, 0, 0, 0]
        with patch.object(ui, "start"), patch.object(work.curses, "wrapper",
                                                    side_effect=lambda run: run(self.screen(keys, size))):
            return getattr(ui, method)(*args, **kwargs)

    def test_ui_scroll_and_select_long_list(self):
        items = [(f"日本語ボード {i}", i) for i in range(40)]
        result = self.ui_call("choose", [curses.KEY_NPAGE, curses.KEY_DOWN, "\n"],
                              "ボード", items, size=(24, 80))
        self.assertEqual(result, 9)

    def test_ui_number_shortcut_and_exit(self):
        items = [(str(i), i) for i in range(14)]
        self.assertEqual(self.ui_call("choose", ["1", "3", "\n"], "操作", items), 12)
        self.assertIsNone(self.ui_call("choose", ["q"], "操作", items, dashboard=True))
        with self.assertRaises(work.Cancelled):
            self.ui_call("choose", ["\x1b"], "操作", items)

    def test_ui_small_terminal_can_exit(self):
        self.assertIsNone(self.ui_call("choose", ["q"], "操作", [("終了", None)],
                                       dashboard=True, size=(10, 30)))

    def test_ui_input_japanese_and_clear_default(self):
        self.assertEqual(self.ui_call("read", ["\x15", "日", "本", "x", "\x7f", "\n"],
                                      "検索", "default"), "日本")

    def test_japanese_display_width(self):
        self.assertEqual(work.clipped("ab日本語", 7), "ab日本")
        self.assertEqual(work.clipped("e\u0301日本", 3), "e\u0301日")

    def test_loading_returns_cli_json(self):
        process = Mock(returncode=0)
        process.communicate.return_value = ('{"boards": []}', '')
        process.poll.return_value = 0
        with patch.object(work.subprocess, "Popen", return_value=process):
            result = self.ui_call("capture", [], ["cli", "board", "listall", "--json"])
        self.assertEqual(result, {"boards": []})
        process.terminate.assert_not_called()

    def test_loading_cancel_terminates_and_reaps_cli(self):
        process = Mock(returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired("cli", 0.08), ('', '')]
        process.poll.return_value = None
        with patch.object(work.subprocess, "Popen", return_value=process):
            with self.assertRaises(work.Cancelled):
                self.ui_call("capture", ["q"], ["cli", "board", "list", "--json"])
        process.terminate.assert_called_once()
        self.assertEqual(process.communicate.call_count, 2)

    def test_loading_surfaces_cli_errors(self):
        process = Mock(returncode=1)
        process.communicate.return_value = ('', 'CLI failed')
        process.poll.return_value = 1
        with patch.object(work.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "CLI failed"):
                self.ui_call("capture", [], ["cli", "board", "list", "--json"])


if __name__ == "__main__":
    unittest.main()
