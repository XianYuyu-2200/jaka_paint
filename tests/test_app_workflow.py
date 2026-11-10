"""Check parameter editing and offline TXT generation through the real Tk UI."""
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

import jaka_paint_app as app_module
from core.parameters import DEFAULTS


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def button(window, label):
    return next(child for child in descendants(window)
                if isinstance(child, ttk.Button) and child.cget("text") == label)


def entry_for(window, label):
    field_label = next(child for child in descendants(window)
                       if isinstance(child, ttk.Label) and child.cget("text") == label)
    grid = field_label.grid_info()
    return next(child for child in field_label.master.grid_slaves(
        row=grid["row"], column=grid["column"] + 1
    ) if isinstance(child, ttk.Entry))


def replace(entry, text):
    entry.delete(0, "end")
    entry.insert(0, text)


class AppWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.network = patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Unexpected network call"))
        self.open_request = self.network.start()
        self.environment = patch.dict("os.environ", {"XIANJIJI_API_KEY": ""})
        self.environment.start()
        try:
            self.app = app_module.JakaPaintApp()
        except tk.TclError as exc:
            self.environment.stop()
            self.network.stop()
            self.skipTest(f"Tk display unavailable: {exc}")
        self.app.withdraw()
        self.addCleanup(self.app.destroy)
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.network.stop)

    def test_invalid_edit_is_rejected_and_valid_parameters_reach_txt_without_network(self):
        self.app.show_settings()
        window = self.app.settings_window
        width = entry_for(window, "画布宽度 (mm)")
        replace(width, "nan")
        with patch.object(app_module.messagebox, "showerror") as error:
            button(window, "应用").invoke()
        error.assert_called_once()
        self.assertEqual(self.app.conversion_parameters, DEFAULTS)
        self.assertTrue(window.winfo_exists())
        replace(width, "180")
        button(window, "应用").invoke()
        self.assertIsNone(self.app.settings_window)
        self.assertEqual(self.app.conversion_parameters["width_mm"], 180)
        self.assertIn("180", self.app.parameter_summary.get())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "line.png"
            image = Image.new("L", (64, 64), 255)
            ImageDraw.Draw(image).line((10, 15, 50, 15, 50, 45), fill=0, width=1)
            image.save(source)
            self.app.lineart_path = source
            with patch.object(app_module, "OUTPUT_DIR", root / "output"), \
                    patch.object(app_module.messagebox, "showerror") as error:
                self.app.generate()
            error.assert_not_called()
            script = root / "output" / "line_jaka.txt"
            self.assertIn("# canvas_mm=180.000x152.400", script.read_text(encoding="utf-8"))
            self.assertTrue((root / "output" / "preview" / "line_jaka_trajectory.png").is_file())
            self.assertIsNotNone(self.app.preview)
        self.open_request.assert_not_called()

    def test_cancel_discards_draft_and_service_key_is_only_in_memory(self):
        with self.assertRaisesRegex(ValueError, "API Key"):
            self.app.get_image_generation_options()
        self.app.show_settings()
        window = self.app.settings_window
        replace(entry_for(window, "画布宽度 (mm)"), "200")
        replace(entry_for(window, "API Key"), "fake-local-test-key")
        button(window, "取消").invoke()
        self.assertEqual(self.app.conversion_parameters, DEFAULTS)
        self.assertEqual(self.app.api_key_var.get(), "")
        self.app.show_settings()
        window = self.app.settings_window
        key = entry_for(window, "API Key")
        self.assertEqual(key.cget("show"), "*")
        replace(key, "fake-local-test-key")
        with patch.object(Path, "write_text", side_effect=AssertionError("Must not persist API key")), \
                patch.object(Path, "write_bytes", side_effect=AssertionError("Must not persist API key")):
            button(window, "应用").invoke()
        self.assertEqual(self.app.get_image_generation_options(), {
            "api_key": "fake-local-test-key", "quality": "high",
        })
        self.open_request.assert_not_called()

    def test_conversion_failure_preserves_previous_preview_and_reports_error(self):
        self.app.preview_label.configure(text="previous preview")
        self.app.status.configure(text="previous result")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "blank.png"
            Image.new("L", (64, 64), 255).save(source)
            self.app.lineart_path = source
            with patch.object(app_module, "OUTPUT_DIR", Path(tmp) / "output"), \
                    patch.object(app_module.messagebox, "showerror") as error:
                self.app.generate()
            error.assert_called_once()
            self.assertIn("没有检测到", error.call_args.args[1])
        self.assertEqual(self.app.preview_label.cget("text"), "previous preview")
        self.assertEqual(self.app.status.cget("text"), "previous result")


if __name__ == "__main__":
    unittest.main()
