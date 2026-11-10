from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from core.lineart_to_points import convert_to_jaka
from core.jaka_txt_to_pointmap import parse_jaka_script
from core.parameters import DEFAULTS, FIELD_SPECS, PARAMETER_GROUPS, validate_parameters


class ParametersTest(unittest.TestCase):
    def test_defaults_match_declared_fields_and_accept_text_inputs(self):
        self.assertEqual(validate_parameters({}), DEFAULTS)
        raw = {key: str(value) for key, value in DEFAULTS.items()}
        self.assertEqual(validate_parameters(raw), DEFAULTS)
        self.assertEqual(set(DEFAULTS), {key for _, group in PARAMETER_GROUPS for key in group})
        self.assertEqual(set(DEFAULTS), set(FIELD_SPECS))

    def test_rejects_invalid_numbers_and_inconsistent_canvas(self):
        cases = (
            ("width_mm", "", "画布宽度"),
            ("height_mm", "nan", "画布高度"),
            ("spacing_mm", float("inf"), "点间距"),
            ("robot_x", "-inf", "画布原点 X"),
            ("draw_vel", 0, "绘图速度"),
            ("draw_acc", -1, "绘图加速度"),
            ("travel_vel", 0, "抬笔移动速度"),
            ("travel_acc", "nan", "抬笔移动加速度"),
            ("margin_mm", -1, "边距"),
            ("min_stroke_mm", -1, "最短线段"),
            ("stitch_gap_px", -1, "端点拼接"),
            ("tolerance", -1, "转弯半径"),
            ("tool_id", -1, "Tool ID"),
            ("user_frame_id", "1.5", "User Frame ID"),
            ("threshold", "256", "二值化阈值"),
            ("threshold", "-1", "二值化阈值"),
            ("threshold", True, "二值化阈值"),
            ("min_pixels", "0", "最小线条像素数"),
            ("min_pixels", "nan", "最小线条像素数"),
            ("width_mm", "10", "两倍边距"),
            ("height_mm", "9.9", "两倍边距"),
            ("origin", "center", "图像坐标原点"),
            ("mirror_x", "maybe", "左右镜像"),
        )
        for key, value, label in cases:
            with self.subTest(key=key, value=value):
                with self.assertRaisesRegex(ValueError, label):
                    validate_parameters({key: value})

    def test_accepts_coordinates_and_explicit_boolean_values(self):
        result = validate_parameters({"robot_x": "-12.5", "touch_z": "-9", "mirror_x": "false"})
        self.assertEqual(result["robot_x"], -12.5)
        self.assertEqual(result["touch_z"], -9.0)
        self.assertIs(result["mirror_x"], False)
        self.assertIs(validate_parameters({"mirror_x": "true"})["mirror_x"], True)
        self.assertIs(validate_parameters({"mirror_x": 0})["mirror_x"], False)
        self.assertEqual(validate_parameters({"threshold": "0"})["threshold"], 0)
        self.assertEqual(validate_parameters({"threshold": "255"})["threshold"], 255)
        self.assertEqual(validate_parameters({"tool_id": "0"})["tool_id"], 0)
        with self.assertRaisesRegex(ValueError, "不支持的参数"):
            validate_parameters({"widht_mm": 100})

    def test_parameters_change_script_geometry_and_motion_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "line.png"
            image = Image.new("L", (64, 64), 255)
            ImageDraw.Draw(image).line((10, 15, 50, 15, 50, 45), fill=0, width=1)
            image.save(source)
            baseline = root / "baseline.txt"
            changed = root / "changed.txt"
            convert_to_jaka(source, baseline, **validate_parameters({}), continuous_components=False)
            options = validate_parameters({
                "width_mm": "100", "height_mm": "90", "spacing_mm": "2",
                "draw_vel": "15", "draw_acc": "45", "travel_vel": "25",
                "travel_acc": "75", "touch_z": "-4.5", "tool_id": "2",
                "user_frame_id": "3", "mirror_x": "true", "pose_rx": "175",
            })
            convert_to_jaka(source, changed, **options, continuous_components=False)
            before = baseline.read_text(encoding="utf-8")
            after = changed.read_text(encoding="utf-8")
            self.assertNotEqual(before, after)
            for expected in (
                "# canvas_mm=100.000x90.000", "# spacing_mm=2.000", "# mirror_x=True",
                "Z = -4.500000", "vel1 = 15.000000", "acc1 = 45.000000",
                "vel2 = 25.000000", "acc2 = 75.000000", "set_tool_id(2)",
                "set_user_frame_id(3)",
            ):
                self.assertIn(expected, after)
            before_points, _ = parse_jaka_script(baseline)
            after_points, _ = parse_jaka_script(changed)
            self.assertNotEqual(before_points, after_points)
            self.assertGreater(len(after_points), 1)


if __name__ == "__main__":
    unittest.main()
