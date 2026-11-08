"""JAKA line-art to TXT point-script application."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageTk

from core.lineart_to_points import convert_to_jaka
from core.jaka_txt_to_pointmap import render


ROOT = Path(__file__).resolve().parent
SAMPLE_IMAGE = ROOT / "samples" / "lineart_sample.png"
OUTPUT_DIR = ROOT / "output"
PROMPT_PATH = ROOT / "AI_DEVELOPMENT_PROMPT.md"

# Default drawing parameters used by the current workflow.
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


class JakaPaintApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("JAKA 线稿绘图工作台")
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
            text="线稿转换为 JAKA ZU Script TXT 点位程序。",
        ).pack(anchor="w", pady=(4, 18))

        workflow = ttk.LabelFrame(root, text="当前可用流程", padding=14)
        workflow.pack(fill="x")
        ttk.Label(workflow, text=f"当前线稿：{SAMPLE_IMAGE.relative_to(ROOT)}").pack(anchor="w")
        ttk.Label(workflow, text="转换参数：默认配置").pack(anchor="w", pady=(5, 0))
        actions = ttk.Frame(workflow)
        actions.pack(anchor="w", pady=(14, 0))
        ttk.Button(actions, text="生成 TXT 点位", command=self.generate).pack(side="left")
        ttk.Button(actions, text="开发助手", command=self.show_development_prompt).pack(side="left", padx=(10, 0))

        preview_frame = ttk.LabelFrame(root, text="线稿预览", padding=10)
        preview_frame.pack(fill="both", expand=True, pady=(18, 0))
        self.preview_label = ttk.Label(preview_frame, text="点击“生成 TXT 点位”查看样例")
        self.preview_label.pack(expand=True)
        self.status = ttk.Label(root, text="等待生成", foreground="#555555")
        self.status.pack(anchor="w", pady=(12, 0))

        todo = ttk.LabelFrame(root, text="功能状态", padding=10)
        todo.pack(fill="x", pady=(14, 0))
        ttk.Label(todo, text="当前支持：线稿转 TXT 点位    后续支持：图片输入、参数设置、控制器连接与绘图发送").pack(anchor="w")

    def show_development_prompt(self) -> None:
        """Display the bundled prompt and provide a one-click clipboard copy."""
        if not PROMPT_PATH.is_file():
            messagebox.showerror("文件缺失", f"找不到开发助手提示词：\n{PROMPT_PATH}")
            return
        prompt_window = tk.Toplevel(self)
        prompt_window.title("开发助手提示词")
        prompt_window.geometry("820x620")
        prompt_window.minsize(620, 420)
        prompt_window.transient(self)
        prompt_window.columnconfigure(0, weight=1)
        prompt_window.rowconfigure(0, weight=1)
        text = ScrolledText(prompt_window, wrap="word", padx=12, pady=12)
        text.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))
        content = PROMPT_PATH.read_text(encoding="utf-8")
        text.insert("1.0", content)
        text.configure(state="disabled")

        actions = ttk.Frame(prompt_window, padding=(12, 0, 12, 12))
        actions.grid(row=1, column=0, sticky="ew")

        def copy_prompt() -> None:
            self.clipboard_clear()
            self.clipboard_append(content)
            self.update()
            self.status.configure(text="开发助手提示词已复制到剪贴板")

        ttk.Button(actions, text="复制提示词", command=copy_prompt).pack(side="left")
        ttk.Label(actions, text="复制后粘贴到 Vibe Coding 工具，并在末尾追加当前任务。", foreground="#555555").pack(
            side="left", padx=(12, 0)
        )

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
    JakaPaintApp().mainloop()


if __name__ == "__main__":
    main()
