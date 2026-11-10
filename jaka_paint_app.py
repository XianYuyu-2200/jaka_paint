"""JAKA line-art to TXT point-script application."""
from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageTk

from core.development_prompt import extract_prompt
from core.image_client import API_URL, MODEL, SUPPORTED_QUALITIES
from core.lineart_to_points import convert_to_jaka
from core.jaka_txt_to_pointmap import render
from core.parameters import DEFAULTS, FIELD_SPECS, PARAMETER_GROUPS, validate_parameters


ROOT = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
SAMPLE_IMAGE = ROOT / "samples" / "lineart_sample.png"
OUTPUT_DIR = APP_DIR / "output"
PROMPT_PATH = ROOT / "AI_DEVELOPMENT_PROMPT.md"


class JakaPaintApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("JAKA 线稿绘图工作台")
        self.geometry("980x700")
        self.minsize(820, 620)
        self.preview: ImageTk.PhotoImage | None = None
        self.lineart_path = SAMPLE_IMAGE
        self.conversion_parameters = validate_parameters(DEFAULTS)
        self.api_key_var = tk.StringVar(value=os.environ.get("XIANJIJI_API_KEY", ""))
        self.image_quality_var = tk.StringVar(value="high")
        self.parameter_summary = tk.StringVar(value=self._parameter_summary())
        self.settings_window: tk.Toplevel | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=24)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="JAKA 线稿转 TXT 点位", font=("Microsoft YaHei UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text="线稿转换为 JAKA ZU Script TXT 点位程序。",
        ).pack(anchor="w", pady=(4, 18))

        workflow = ttk.LabelFrame(root, text="线稿转换", padding=14)
        workflow.pack(fill="x")
        ttk.Label(workflow, text=f"当前线稿：{SAMPLE_IMAGE.relative_to(ROOT)}").pack(anchor="w")
        ttk.Label(workflow, textvariable=self.parameter_summary, wraplength=850).pack(anchor="w", pady=(5, 0))
        actions = ttk.Frame(workflow)
        actions.pack(anchor="w", pady=(14, 0))
        ttk.Button(actions, text="生成 TXT 点位", command=self.generate).pack(side="left")
        ttk.Button(actions, text="参数设置", command=self.show_settings).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="打开输出文件夹", command=self.open_output_directory).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="开发助手", command=self.show_development_prompt).pack(side="left", padx=(10, 0))

        preview_frame = ttk.LabelFrame(root, text="线稿预览", padding=10)
        preview_frame.pack(fill="both", expand=True, pady=(18, 0))
        self.preview_label = ttk.Label(preview_frame, text="点击“生成 TXT 点位”查看样例")
        self.preview_label.pack(expand=True)
        self.status = ttk.Label(root, text="等待生成", foreground="#555555")
        self.status.pack(anchor="w", pady=(12, 0))

        todo = ttk.LabelFrame(root, text="功能状态", padding=10)
        todo.pack(fill="x", pady=(14, 0))
        ttk.Label(todo, text="当前支持：样例线稿转 TXT 点位、参数设置；已预置图像服务接口。").pack(anchor="w")
        ttk.Label(todo, text="输出位置：" + str(OUTPUT_DIR), wraplength=850).pack(anchor="w", pady=(4, 0))

    def _parameter_summary(self) -> str:
        p = self.conversion_parameters
        origin = "左上" if p["origin"] == "top-left" else "左下"
        mirror = "开启" if p["mirror_x"] else "关闭"
        return (
            f"画布 {p['width_mm']:g} × {p['height_mm']:g} mm · 边距 {p['margin_mm']:g} mm · "
            f"点间距 {p['spacing_mm']:g} mm · 阈值 {p['threshold']} · 原点{origin} · 镜像{mirror}\n"
            f"位置 ({p['robot_x']:g}, {p['robot_y']:g}, {p['touch_z']:g}) mm · "
            f"姿态 ({p['pose_rx']:g}, {p['pose_ry']:g}, {p['pose_rz']:g})° · "
            f"抬笔 Z 偏移 {p['lift_dz']:g} mm\n"
            f"绘图速度/加速度 {p['draw_vel']:g}/{p['draw_acc']:g} · "
            f"移动速度/加速度 {p['travel_vel']:g}/{p['travel_acc']:g} · "
            f"Tool {p['tool_id']} · User Frame {p['user_frame_id']}"
        )

    def get_image_generation_options(self) -> dict:
        """Read on the UI thread before passing this snapshot to an image worker."""
        key = self.api_key_var.get().strip()
        if not key:
            raise ValueError("请在“参数设置 → 图像服务”中填写 API Key，或配置 XIANJIJI_API_KEY 环境变量。")
        if any(character.isspace() for character in key):
            raise ValueError("API Key 不能包含空白字符。")
        quality = self.image_quality_var.get()
        if quality not in SUPPORTED_QUALITIES:
            raise ValueError("生成质量必须为 medium 或 high。")
        return {"api_key": key, "quality": quality}

    def show_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        window = tk.Toplevel(self)
        self.settings_window = window
        window.title("参数设置")
        window.geometry("900x590")
        window.minsize(820, 540)
        window.transient(self)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        ttk.Label(
            window,
            text="设备参数沿用示例配置；实际使用前请核对现场坐标系、画笔高度和运动范围。",
            wraplength=840,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 10))
        notebook = ttk.Notebook(window)
        notebook.grid(row=1, column=0, sticky="nsew", padx=16)
        draft_vars = {}
        for title, keys in PARAMETER_GROUPS:
            page = ttk.Frame(notebook, padding=16)
            notebook.add(page, text=title)
            for column in (1, 3):
                page.columnconfigure(column, weight=1)
            for index, key in enumerate(keys):
                spec = FIELD_SPECS[key]
                row, pair = divmod(index, 2)
                column = pair * 2
                value = self.conversion_parameters[key]
                variable = (tk.BooleanVar(value=value) if spec.kind == "bool"
                            else tk.StringVar(value=str(value)))
                draft_vars[key] = variable
                ttk.Label(page, text=spec.label).grid(row=row, column=column, sticky="w", padx=(0, 8), pady=10)
                if spec.kind == "bool":
                    widget = ttk.Checkbutton(page, text="开启", variable=variable)
                elif spec.kind == "choice":
                    widget = ttk.Combobox(page, textvariable=variable, values=spec.choices, state="readonly", width=16)
                else:
                    widget = ttk.Entry(page, textvariable=variable, width=16)
                widget.grid(row=row, column=column + 1, sticky="ew", padx=(0, 20), pady=10)
            if title == PARAMETER_GROUPS[0][0]:
                ttk.Label(page, text="图像原点：top-left 为左上，bottom-left 为左下。", wraplength=760).grid(
                    row=(len(keys) + 1) // 2, column=0, columnspan=4, sticky="w", pady=(12, 0)
                )

        service = ttk.Frame(notebook, padding=16)
        notebook.add(service, text="图像服务")
        service.columnconfigure(1, weight=1)
        draft_key = tk.StringVar(value=self.api_key_var.get())
        draft_quality = tk.StringVar(value=self.image_quality_var.get())
        ttk.Label(service, text="服务地址").grid(row=0, column=0, sticky="w", pady=8, padx=(0, 16))
        ttk.Label(service, text=API_URL).grid(row=0, column=1, sticky="w", pady=8)
        ttk.Label(service, text="模型标识").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Label(service, text=MODEL).grid(row=1, column=1, sticky="w", pady=8)
        ttk.Label(service, text="生成质量").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Combobox(service, textvariable=draft_quality, values=SUPPORTED_QUALITIES, state="readonly", width=16).grid(
            row=2, column=1, sticky="w", pady=8
        )
        ttk.Label(service, text="API Key").grid(row=3, column=0, sticky="w", pady=8)
        key_entry = ttk.Entry(service, textvariable=draft_key, show="*")
        key_entry.grid(row=3, column=1, sticky="ew", pady=8)
        show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            service, text="显示", variable=show_key,
            command=lambda: key_entry.configure(show="" if show_key.get() else "*"),
        ).grid(row=3, column=2, padx=(10, 0))
        ttk.Label(
            service,
            text="API Key 仅在本次运行中使用，不保存到文件。也可从 XIANJIJI_API_KEY 环境变量读取。\n"
                 "图像尺寸：1024 × 1024。应用参数不会发送请求；实际调用需联网并使用个人服务账户。",
            wraplength=780,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(16, 0))

        def close() -> None:
            self.settings_window = None
            window.destroy()

        def apply() -> None:
            try:
                values = validate_parameters({key: variable.get() for key, variable in draft_vars.items()})
                key = draft_key.get().strip()
                if any(character.isspace() for character in key):
                    raise ValueError("API Key 不能包含空白字符。")
                quality = draft_quality.get()
                if quality not in SUPPORTED_QUALITIES:
                    raise ValueError("生成质量必须为 medium 或 high。")
            except ValueError as exc:
                messagebox.showerror("参数无效", str(exc), parent=window)
                return
            self.conversion_parameters = values
            self.api_key_var.set(key)
            self.image_quality_var.set(quality)
            self.parameter_summary.set(self._parameter_summary())
            self.status.configure(text="参数已应用；重新生成 TXT 后生效")
            close()

        def restore() -> None:
            for key, value in DEFAULTS.items():
                draft_vars[key].set(value)
            draft_quality.set("high")

        buttons = ttk.Frame(window, padding=16)
        buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(buttons, text="恢复默认参数", command=restore).pack(side="left")
        ttk.Button(buttons, text="取消", command=close).pack(side="right", padx=(10, 0))
        ttk.Button(buttons, text="应用", command=apply).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", close)
        window.grab_set()

    def open_output_directory(self) -> None:
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(OUTPUT_DIR)
        except OSError as exc:
            messagebox.showerror("无法打开输出文件夹", str(exc))

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
        try:
            content = extract_prompt(PROMPT_PATH.read_text(encoding="utf-8"))
        except ValueError as exc:
            prompt_window.destroy()
            messagebox.showerror("提示词格式错误", str(exc))
            return
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
        source = Path(self.lineart_path)
        if not source.is_file():
            messagebox.showerror("缺少线稿", f"找不到线稿图片：\n{source}")
            return
        try:
            parameters = validate_parameters(self.conversion_parameters)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            txt_path = OUTPUT_DIR / f"{source.stem}_jaka.txt"
            out, path_count, point_count, scale = convert_to_jaka(
                source,
                txt_path,
                **parameters,
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
        except (Exception, SystemExit) as exc:
            messagebox.showerror("生成失败", str(exc))


def main() -> None:
    JakaPaintApp().mainloop()


if __name__ == "__main__":
    main()
