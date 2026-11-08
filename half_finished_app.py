"""Teaching starter: fixed line-art input to JAKA TXT point script.

This intentionally small application is the starting point for the Vibe Coding
training. The conversion algorithm is supplied; the surrounding workflow is
left as TODO work for learners.
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from core.lineart_to_points import convert_to_jaka
from core.jaka_txt_to_pointmap import render


ROOT = Path(__file__).resolve().parent
SAMPLE_IMAGE = ROOT / "samples" / "lineart_sample.png"
OUTPUT_DIR = ROOT / "output"

# Fixed teaching defaults. Learners will expose these in a parameter panel.
DEFAULTS = {
    "width_mm": 152.4,
    "height_mm": 152.4,
    "margin_mm": 5.0,
    "spacing_mm": 1.0,
    "threshold": 180,
    "min_pixels": 8,
    "min_stroke_mm": 0.0,
    "origin": "top-left",
    "robot_x": -6.771302,
    "robot_y": -6.384003,
    "touch_z": -9.0,
    "lift_dz": 7.0,
    "pose_rx": 180.0,
    "pose_ry": 0.0,
    "pose_rz": 180.0,
    "tool_id": 4,
    "user_frame_id": 6,
    "mirror_x": False,
}


class HalfFinishedApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("JAKA 线稿转 TXT 点位 · 教学半成品")
        self.geometry("900x650")
        self.minsize(760, 560)
        self.preview: ImageTk.PhotoImage | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=24)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="JAKA 线稿转 TXT 点位", font=("Microsoft YaHei UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="当前版本只保留核心转换：固定线稿样例 → JAKA ZU Script TXT。",
        ).pack(anchor="w", pady=(4, 18))

        workflow = ttk.LabelFrame(root, text="当前可用流程", padding=14)
        workflow.pack(fill="x")
        ttk.Label(workflow, text=f"输入样例：{SAMPLE_IMAGE.relative_to(ROOT)}").pack(anchor="w")
        ttk.Label(workflow, text="转换参数：内置教学默认值（暂未开放设置面板）").pack(anchor="w", pady=(5, 0))
        ttk.Button(workflow, text="生成 TXT 点位", command=self.generate).pack(anchor="w", pady=(14, 0))

        preview_frame = ttk.LabelFrame(root, text="线稿预览", padding=10)
        preview_frame.pack(fill="both", expand=True, pady=(18, 0))
        self.preview_label = ttk.Label(preview_frame, text="点击“生成 TXT 点位”查看样例")
        self.preview_label.pack(expand=True)
        self.status = ttk.Label(root, text="等待生成", foreground="#555555")
        self.status.pack(anchor="w", pady=(12, 0))

        todo = ttk.LabelFrame(root, text="Vibe Coding 待完成模块", padding=10)
        todo.pack(fill="x", pady=(14, 0))
        ttk.Label(todo, text="1. 图片选择与预览    2. 参数设置    3. JAKA IP 连接、发送与启动绘图").pack(anchor="w")

    def generate(self) -> None:
        if not SAMPLE_IMAGE.is_file():
            messagebox.showerror("缺少样例", f"找不到样例线稿：\n{SAMPLE_IMAGE}")
            return
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            txt_path = OUTPUT_DIR / "lineart_sample_jaka.txt"
            out, path_count, point_count, scale = convert_to_jaka(
                SAMPLE_IMAGE,
                txt_path,
                **DEFAULTS,
                continuous_components=False,
            )
            preview_dir = OUTPUT_DIR / "preview"
            rendered = render(out, preview_dir, size=900)
            image = Image.open(rendered["trajectory"]).convert("RGB")
            image.thumbnail((560, 390))
            self.preview = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self.preview, text="")
            self.status.configure(
                text=f"已生成：{out.name} · {path_count} 条线 · {point_count} 个点 · {scale:.4f} mm/px"
            )
        except Exception as exc:
            messagebox.showerror("生成失败", str(exc))


def main() -> None:
    HalfFinishedApp().mainloop()


if __name__ == "__main__":
    main()
