from pathlib import Path
import tempfile
import unittest

from core.lineart_to_points import convert_to_jaka
from core.jaka_txt_to_pointmap import parse_jaka_script, render


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "lineart_sample.png"


class CoreConversionTest(unittest.TestCase):
    def test_sample_generates_parseable_jaka_script_and_previews(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "sample.txt"
            script, path_count, point_count, scale = convert_to_jaka(
                SAMPLE,
                output,
                width_mm=152.4,
                height_mm=152.4,
                margin_mm=5.0,
                spacing_mm=1.0,
                threshold=180,
                min_pixels=8,
                continuous_components=False,
            )
            self.assertEqual(script, output.resolve())
            self.assertGreater(path_count, 0)
            self.assertGreater(point_count, 1)
            self.assertGreater(scale, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("# JAKA ZU Script", text)
            self.assertIn("set_tool_id", text)
            points, paths = parse_jaka_script(output)
            self.assertGreater(len(points), 1)
            self.assertEqual(len(paths), path_count)
            rendered = render(output, Path(tmp) / "preview", size=256)
            for key in ("points", "trajectory", "diagnostic"):
                self.assertTrue(Path(rendered[key]).is_file())


if __name__ == "__main__":
    unittest.main()
