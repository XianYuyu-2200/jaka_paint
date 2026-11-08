"""Render JAKA ZU Script point declarations and movl paths as preview PNGs."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw


POINT_RE = re.compile(
    r"^P(\d+)\s*=\s*\[\s*([-+\d.]+)\s*,\s*([-+\d.]+)\s*,\s*"
    r"(?:Z|[-+\d.]+)\s*,"
)
MOVE_RE = re.compile(r"^movl\(P(\d+)\s*,")
PATH_RE = re.compile(r"^#\s*第\s*(\d+)\s*条线")


def parse_jaka_script(path: str | Path):
    text = Path(path).read_text(encoding="utf-8")
    points: dict[int, tuple[float, float]] = {}
    for line in text.splitlines():
        match = POINT_RE.match(line.strip())
        if match:
            points[int(match.group(1))] = (float(match.group(2)), float(match.group(3)))

    # Read only the trajectory section. P0 lift moves are intentionally ignored.
    trajectory = text.split("# ====================== 轨迹", 1)[-1]
    paths: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] | None = None
    for raw in trajectory.splitlines():
        line = raw.strip()
        if PATH_RE.match(line):
            if current:
                paths.append(current)
            current = []
            continue
        match = MOVE_RE.match(line)
        if match and current is not None:
            point_id = int(match.group(1))
            if point_id != 0 and point_id in points:
                current.append(points[point_id])
    if current:
        paths.append(current)
    paths = [path for path in paths if path]
    if not paths:
        raise ValueError("没有从脚本轨迹段中解析到 movl(Pn...) 绘图路径。")
    return points, paths


def render(
    script: str | Path,
    output_dir: str | Path,
    size: int = 2048,
    padding: int = 60,
):
    src = Path(script).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    points, paths = parse_jaka_script(src)
    used = [point for path in paths for point in path]
    min_x = min(x for x, _ in used)
    max_x = max(x for x, _ in used)
    min_y = min(y for _, y in used)
    max_y = max(y for _, y in used)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    scale = min((size - 2 * padding) / span_x, (size - 2 * padding) / span_y)
    offset_x = (size - span_x * scale) / 2
    offset_y = (size - span_y * scale) / 2

    def pixel(point):
        x, y = point
        return (
            round(offset_x + (x - min_x) * scale),
            round(offset_y + (y - min_y) * scale),
        )

    # Exact point map: every DOWN point becomes one black dot.
    point_image = Image.new("RGB", (size, size), "white")
    point_draw = ImageDraw.Draw(point_image)
    point_radius = max(1, round(size / 2048))
    for path in paths:
        for p in path:
            x, y = pixel(p)
            point_draw.ellipse(
                (x - point_radius, y - point_radius, x + point_radius, y + point_radius),
                fill="black",
            )

    # Expected pen result: connect only points within the same DOWN path.
    trace_image = Image.new("RGB", (size, size), "white")
    trace_draw = ImageDraw.Draw(trace_image)
    for path in paths:
        coords = [pixel(p) for p in path]
        if len(coords) == 1:
            trace_draw.point(coords[0], fill="black")
        else:
            trace_draw.line(coords, fill="black", width=2, joint="curve")

    # Diagnostic map: actual pen paths black, lift travel light gray dashed,
    # starts red, ends green. The black path connects every point in order.
    diagnostic = trace_image.copy()
    diag_draw = ImageDraw.Draw(diagnostic)
    previous_end = None
    for path in paths:
        start = pixel(path[0])
        end = pixel(path[-1])
        if previous_end is not None:
            # Dashed lift travel between independent strokes.
            x1, y1 = previous_end
            x2, y2 = start
            steps = max(abs(x2 - x1), abs(y2 - y1), 1)
            for i in range(0, steps, 14):
                j = min(i + 7, steps)
                a = (x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
                b = (x1 + (x2 - x1) * j / steps, y1 + (y2 - y1) * j / steps)
                diag_draw.line((a, b), fill=(190, 190, 190), width=1)
        r = 5
        if start == end:
            # Closed continuous walks return to their starting point. Keep
            # both labels visible: red outer start ring, green end center.
            diag_draw.ellipse((start[0]-r, start[1]-r, start[0]+r, start[1]+r), outline=(220, 40, 40), width=2)
            inner = 3
            diag_draw.ellipse((end[0]-inner, end[1]-inner, end[0]+inner, end[1]+inner), fill=(30, 170, 70))
        else:
            diag_draw.ellipse((start[0]-r, start[1]-r, start[0]+r, start[1]+r), fill=(220, 40, 40))
            diag_draw.ellipse((end[0]-r, end[1]-r, end[0]+r, end[1]+r), fill=(30, 170, 70))
        previous_end = end

    point_path = out_dir / f"{src.stem}_points.png"
    trace_path = out_dir / f"{src.stem}_trajectory.png"
    diagnostic_path = out_dir / f"{src.stem}_diagnostic.png"
    point_image.save(point_path)
    trace_image.save(trace_path)
    diagnostic.save(diagnostic_path)
    return {
        "points": point_path,
        "trajectory": trace_path,
        "diagnostic": diagnostic_path,
        "path_count": len(paths),
        "point_count": sum(len(path) for path in paths),
        "short_paths": sum(len(path) <= 10 for path in paths),
        "bounds": (min_x, min_y, max_x, max_y),
    }


def main():
    parser = argparse.ArgumentParser(description="JAKA TXT/JKS to point and trajectory PNG")
    parser.add_argument("script")
    parser.add_argument("--output-dir", default="pointmap_output")
    parser.add_argument("--size", type=int, default=2048)
    args = parser.parse_args()
    result = render(args.script, args.output_dir, args.size)
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
