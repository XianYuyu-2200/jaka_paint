"""Drawing parameter definitions and validation, independent of the UI.

Defaults preserve the existing converter's example configuration. Validation
checks types and mathematical consistency, not a robot's safe operating limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Any, Mapping


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: str
    default: Any
    choices: tuple[str, ...] = ()


PARAMETER_GROUPS = (
    ("转换设置", (
        "width_mm", "height_mm", "margin_mm", "spacing_mm", "threshold",
        "min_pixels", "min_stroke_mm", "stitch_gap_px", "origin", "mirror_x",
    )),
    ("位置姿态", (
        "robot_x", "robot_y", "touch_z", "lift_dz", "lift_dy", "lift_drx",
        "pose_rx", "pose_ry", "pose_rz",
    )),
    ("运动参数", (
        "draw_vel", "draw_acc", "travel_vel", "travel_acc", "tolerance",
        "tool_id", "user_frame_id",
    )),
)

FIELD_SPECS = {
    spec.key: spec for spec in (
        FieldSpec("width_mm", "画布宽度 (mm)", "float", 152.4),
        FieldSpec("height_mm", "画布高度 (mm)", "float", 152.4),
        FieldSpec("margin_mm", "边距 (mm)", "float", 5.0),
        FieldSpec("spacing_mm", "点间距 (mm)", "float", 1.0),
        FieldSpec("threshold", "二值化阈值 (0–255)", "int", 180),
        FieldSpec("min_pixels", "最小线条像素数", "int", 8),
        FieldSpec("min_stroke_mm", "最短线段 (mm)", "float", 0.0),
        FieldSpec("stitch_gap_px", "端点拼接间距 (px)", "float", 2.0),
        FieldSpec("origin", "图像坐标原点", "choice", "top-left", ("top-left", "bottom-left")),
        FieldSpec("mirror_x", "左右镜像 X", "bool", False),
        FieldSpec("robot_x", "画布原点 X (mm)", "float", -6.771302),
        FieldSpec("robot_y", "画布原点 Y (mm)", "float", -6.384003),
        FieldSpec("touch_z", "触纸高度 Z (mm)", "float", -9.0),
        FieldSpec("lift_dz", "抬笔偏移 dz (mm)", "float", 7.0),
        FieldSpec("lift_dy", "抬笔偏移 dy (mm)", "float", 0.0),
        FieldSpec("lift_drx", "抬笔姿态偏移 drx (°)", "float", 0.0),
        FieldSpec("pose_rx", "姿态 rx (°)", "float", 180.0),
        FieldSpec("pose_ry", "姿态 ry (°)", "float", 0.0),
        FieldSpec("pose_rz", "姿态 rz (°)", "float", 180.0),
        FieldSpec("draw_vel", "绘图速度 (mm/s)", "float", 30.0),
        FieldSpec("draw_acc", "绘图加速度 (mm/s²)", "float", 90.0),
        FieldSpec("travel_vel", "抬笔移动速度 (mm/s)", "float", 60.0),
        FieldSpec("travel_acc", "抬笔移动加速度 (mm/s²)", "float", 180.0),
        FieldSpec("tolerance", "转弯半径 (mm)", "float", 1.0),
        FieldSpec("tool_id", "Tool ID", "int", 4),
        FieldSpec("user_frame_id", "User Frame ID", "int", 6),
    )
}

DEFAULTS = {key: spec.default for key, spec in FIELD_SPECS.items()}

_POSITIVE = {
    "width_mm", "height_mm", "spacing_mm", "draw_vel", "draw_acc",
    "travel_vel", "travel_acc",
}
_NONNEGATIVE = {
    "margin_mm", "min_stroke_mm", "stitch_gap_px", "tolerance", "tool_id",
    "user_frame_id",
}


def _number(value: Any, spec: FieldSpec) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"{spec.label}必须是{'整数' if spec.kind == 'int' else '有限数值'}。")
    if spec.kind == "int":
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise ValueError(f"{spec.label}必须是整数。") from None
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError(f"{spec.label}必须是有限整数。")
        return int(number)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{spec.label}必须是有限数值。") from None
    if not math.isfinite(number):
        raise ValueError(f"{spec.label}必须是有限数值。")
    return number


def _boolean(value: Any, spec: FieldSpec) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{spec.label}必须是布尔值（true/false）。")


def validate_parameters(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return converter keyword arguments, raising a field-specific ValueError.

    Missing keys use the example defaults. Explicit blank/invalid values are
    rejected instead of silently falling back. Unknown keys are rejected to
    expose misspelled parameter names before they reach the converter.
    """
    unknown = set(raw).difference(FIELD_SPECS)
    if unknown:
        raise ValueError("不支持的参数：" + ", ".join(sorted(map(str, unknown))))
    result: dict[str, Any] = {}
    for key, spec in FIELD_SPECS.items():
        value = raw.get(key, spec.default)
        if spec.kind == "bool":
            result[key] = _boolean(value, spec)
            continue
        if spec.kind == "choice":
            value = str(value).strip()
            if value not in spec.choices:
                raise ValueError(f"{spec.label}必须是 {' / '.join(spec.choices)}。")
            result[key] = value
            continue
        value = _number(value, spec)
        if key in _POSITIVE and value <= 0:
            raise ValueError(f"{spec.label}必须大于 0。")
        if key in _NONNEGATIVE and value < 0:
            raise ValueError(f"{spec.label}不能小于 0。")
        if key == "threshold" and not 0 <= value <= 255:
            raise ValueError(f"{spec.label}必须在 0 到 255 之间。")
        if key == "min_pixels" and value < 1:
            raise ValueError(f"{spec.label}必须大于等于 1。")
        result[key] = value
    for key in ("width_mm", "height_mm"):
        if result[key] <= 2 * result["margin_mm"]:
            raise ValueError(f"{FIELD_SPECS[key].label}必须大于两倍边距。")
    return result
