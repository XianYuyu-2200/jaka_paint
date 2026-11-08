"""Convert black-on-white line art into an ordered JAKA ZU drawing script."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def zhang_suen(binary: np.ndarray) -> np.ndarray:
    """Thin a binary image to approximately one-pixel-wide centerlines."""
    img = binary.copy().astype(bool)
    h, w = img.shape
    changed = True
    while changed:
        changed = False
        for phase in (0, 1):
            p = np.pad(img, 1, mode="constant", constant_values=False)
            p2, p3, p4 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:]
            p5, p6, p7 = p[2:, 2:], p[2:, 1:-1], p[2:, :-2]
            p8, p9 = p[1:-1, :-2], p[:-2, :-2]
            neighbors = (p2.astype(np.uint8) + p3.astype(np.uint8) + p4.astype(np.uint8)
                         + p5.astype(np.uint8) + p6.astype(np.uint8) + p7.astype(np.uint8)
                         + p8.astype(np.uint8) + p9.astype(np.uint8))
            seq = np.stack([p2, p3, p4, p5, p6, p7, p8, p9, p2], axis=0)
            transitions = np.sum((~seq[:-1]) & seq[1:], axis=0)
            keep = img & (neighbors >= 2) & (neighbors <= 6) & (transitions == 1)
            if phase == 0:
                keep &= ~(p2 & p4 & p6) & ~(p4 & p6 & p8)
            else:
                keep &= ~(p2 & p4 & p8) & ~(p2 & p6 & p8)
            if np.any(keep):
                img[keep] = False
                changed = True
    return img


NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def graph_neighbors(point, points):
    """8-neighborhood without redundant diagonal corner edges.

    A diagonal is ignored when an orthogonal pixel already connects the same
    corner. This prevents tiny triangular graph cycles introduced by raster
    skeletonization and sharply reduces false branches.
    """
    y, x = point
    result = []
    for dy, dx in NEIGHBORS:
        nxt = (y + dy, x + dx)
        if nxt not in points:
            continue
        if dy and dx and ((y + dy, x) in points or (y, x + dx) in points):
            continue
        result.append(nxt)
    return result


def _eye_component_candidates(binary: np.ndarray):
    """Find compact face-band components for conservative eye-pair detection."""
    ys_all, xs_all = np.where(binary)
    if len(xs_all) == 0:
        return [], (0, 0, binary.shape[1] - 1, binary.shape[0] - 1)
    min_x, max_x = int(xs_all.min()), int(xs_all.max())
    min_y, max_y = int(ys_all.min()), int(ys_all.max())
    span_x = max(1, max_x - min_x)
    span_y = max(1, max_y - min_y)
    h, w = binary.shape
    seen = np.zeros_like(binary, dtype=bool)
    candidates = []
    for seed_y, seed_x in zip(ys_all, xs_all):
        seed_y, seed_x = int(seed_y), int(seed_x)
        if seen[seed_y, seed_x]:
            continue
        seen[seed_y, seed_x] = True
        stack = [(seed_y, seed_x)]
        component = []
        while stack:
            y, x = stack.pop()
            component.append((y, x))
            for dy, dx in NEIGHBORS:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and binary[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        xs = [x for _, x in component]; ys = [y for y, _ in component]
        x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys)
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if not (5 <= bw <= max(100, int(0.18 * span_x)) and 5 <= bh <= max(70, int(0.10 * span_y))):
            continue
        aspect = bw / max(1, bh)
        if not 0.45 <= aspect <= 8.5:
            continue
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        nx = (cx - min_x) / span_x
        ny = (cy - min_y) / span_y
        # Keep a broad upper-face band so a forehead eye can be detected and
        # removed. The true eye pair selector below still requires the normal
        # paired row and therefore does not confuse hair or eyebrows with eyes.
        if not (0.24 <= nx <= 0.76 and 0.18 <= ny <= 0.55):
            continue
        fill = len(component) / max(1, bw * bh)
        roundness = min(bw, bh) / max(bw, bh)
        candidates.append((cx, cy, min(bw, bh) / 2.0, fill, roundness, bw, bh, x0, y0, x1, y1, component))
    return candidates, (min_x, min_y, max_x, max_y)


def detect_eye_centers(binary: np.ndarray):
    """Return two stable eye centers, with a normalized portrait fallback."""
    candidates, bbox = _eye_component_candidates(binary)
    min_x, min_y, max_x, max_y = bbox
    span_x = max(1, max_x - min_x)
    span_y = max(1, max_y - min_y)
    # Select eyes as a pair, never independently. This prevents a left eyebrow
    # and a right eye (or two hallucinated eye symbols on different rows) from
    # becoming the template anchors.
    left = [c for c in candidates if min_x + 0.25 * span_x <= c[0] < min_x + 0.50 * span_x
            and c[5] >= 55 and c[6] >= 20]
    right = [c for c in candidates if min_x + 0.50 * span_x < c[0] <= min_x + 0.75 * span_x
             and c[5] >= 55 and c[6] >= 20]
    pairs = []
    for lft in left:
        for rgt in right:
            separation = (rgt[0] - lft[0]) / span_x
            row_gap = abs(rgt[1] - lft[1]) / span_y
            if not (0.15 <= separation <= 0.34 and row_gap <= 0.055):
                continue
            mean_y = ((lft[1] + rgt[1]) / 2.0 - min_y) / span_y
            size_mismatch = abs(lft[5] - rgt[5]) / max(lft[5], rgt[5]) + abs(lft[6] - rgt[6]) / max(lft[6], rgt[6])
            aspect_l = lft[5] / max(1, lft[6]); aspect_r = rgt[5] / max(1, rgt[6])
            eyebrow_penalty = max(0.0, aspect_l - 3.8) + max(0.0, aspect_r - 3.8)
            low_fill_penalty = 1.5 * (max(0.0, 0.20 - lft[3]) + max(0.0, 0.20 - rgt[3]))
            target_penalty = abs(mean_y - 0.40) + 0.7 * abs(separation - 0.22)
            eye_shape_reward = 0.35 * (lft[4] + rgt[4]) + 0.20 * (lft[3] + rgt[3])
            score = (3.0 * row_gap + 0.8 * size_mismatch + 0.35 * eyebrow_penalty
                     + low_fill_penalty + target_penalty - eye_shape_reward)
            pairs.append((score, lft, rgt))
    if pairs:
        _, lft, rgt = min(pairs, key=lambda item: item[0])
        return [(lft[0], lft[1]), (rgt[0], rgt[1])], bbox
    cy = min_y + 0.42 * span_y
    return [(min_x + 0.39 * span_x, cy), (min_x + 0.61 * span_x, cy)], bbox


def _select_eye_component_pair(candidates, bbox):
    """Choose the two model-drawn eye components as one structural pair."""
    min_x, min_y, max_x, max_y = bbox
    span_x = max(1, max_x - min_x); span_y = max(1, max_y - min_y)
    left = [c for c in candidates if min_x + 0.25 * span_x <= c[0] < min_x + 0.50 * span_x
            and c[5] >= 55 and c[6] >= 20]
    right = [c for c in candidates if min_x + 0.50 * span_x < c[0] <= min_x + 0.75 * span_x
             and c[5] >= 55 and c[6] >= 20]
    pairs = []
    for lft in left:
        for rgt in right:
            separation = (rgt[0] - lft[0]) / span_x
            row_gap = abs(rgt[1] - lft[1]) / span_y
            if not (0.15 <= separation <= 0.34 and row_gap <= 0.055):
                continue
            mean_y = ((lft[1] + rgt[1]) / 2.0 - min_y) / span_y
            size_mismatch = abs(lft[5] - rgt[5]) / max(lft[5], rgt[5]) + abs(lft[6] - rgt[6]) / max(lft[6], rgt[6])
            aspect_l = lft[5] / max(1, lft[6]); aspect_r = rgt[5] / max(1, rgt[6])
            eyebrow_penalty = max(0.0, aspect_l - 3.8) + max(0.0, aspect_r - 3.8)
            low_fill_penalty = 1.5 * (max(0.0, 0.20 - lft[3]) + max(0.0, 0.20 - rgt[3]))
            target_penalty = abs(mean_y - 0.40) + 0.7 * abs(separation - 0.22)
            eye_shape_reward = 0.35 * (lft[4] + rgt[4]) + 0.20 * (lft[3] + rgt[3])
            score = (3.0 * row_gap + 0.8 * size_mismatch + 0.35 * eyebrow_penalty
                     + low_fill_penalty + target_penalty - eye_shape_reward)
            pairs.append((score, lft, rgt))
    if not pairs:
        return []
    _, lft, rgt = min(pairs, key=lambda item: item[0])
    return [lft, rgt]


def normalize_thin_lineart_array(gray: np.ndarray) -> np.ndarray:
    """Render every visible stroke as one clean, thin centreline.

    The generator sometimes returns 6-10 px black bands even when the prompt
    asks for line art. Skeletonizing removes that model-dependent width; a
    single 3x3 expansion gives a stable roughly 2-3 px final stroke at 1024px.
    """
    skeleton = zhang_suen(gray < 180)
    paths = semantic_contour_trails(skeleton, min_pixels=3)
    scale = 4
    h, w = gray.shape
    image = Image.new("L", (w * scale, h * scale), 255)
    draw = ImageDraw.Draw(image)

    def chaikin(points, closed):
        if len(points) < 4:
            return points
        core = points[:-1] if closed and points[0] == points[-1] else points
        if closed:
            output = []
            for index, point in enumerate(core):
                nxt = core[(index + 1) % len(core)]
                output.extend(((0.75 * point[0] + 0.25 * nxt[0], 0.75 * point[1] + 0.25 * nxt[1]),
                               (0.25 * point[0] + 0.75 * nxt[0], 0.25 * point[1] + 0.75 * nxt[1])))
            output.append(output[0])
            return output
        output = [core[0]]
        for point, nxt in zip(core, core[1:]):
            output.extend(((0.75 * point[0] + 0.25 * nxt[0], 0.75 * point[1] + 0.25 * nxt[1]),
                           (0.25 * point[0] + 0.75 * nxt[0], 0.25 * point[1] + 0.75 * nxt[1])))
        output.append(core[-1])
        return output

    for path in paths:
        xy = [(float(x), float(y)) for y, x in path]
        closed = len(xy) >= 4 and math.dist(xy[0], xy[-1]) <= 1.5
        if len(xy) >= 6:
            xy = chaikin(xy, closed)
        coords = [(round(x * scale), round(y * scale)) for x, y in xy]
        if len(coords) >= 2:
            draw.line(coords, fill=0, width=7, joint="curve")
    image = image.resize((w, h), Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.uint8)


def preserve_eye_semantics_array(gray: np.ndarray) -> np.ndarray:
    """Preserve the model-drawn human eye and delete only extra eye symbols.

    The preferred reference uses a complete layered eye: natural upper/lower
    eyelids, a visible iris arc and a compact pupil.  Clearing that structure
    and inserting a deterministic oval made every portrait look vacant, so the
    postprocessor now leaves the true eyes and eyebrows intact and performs
    only a conservative search for a clearly separate extra eye symbol.
    """
    if gray.ndim != 2:
        raise ValueError("眼睛语义清理只接受灰度图像。")
    h, w = gray.shape
    binary = gray < 180
    candidates, bbox = _eye_component_candidates(binary)
    eye_pair = _select_eye_component_pair(candidates, bbox)
    # If the two real eyes are not confidently identified, make no change.
    # A false positive is much more damaging than leaving a rare decorative
    # mark for manual review.
    if not eye_pair:
        return gray.astype(np.uint8, copy=True)
    mean_eye_width = sum(eye[5] for eye in eye_pair) / 2.0
    mean_eye_height = sum(eye[6] for eye in eye_pair) / 2.0
    stroke = max(2, int(round(min(h, w) / 420.0)))
    canvas = Image.fromarray(gray.astype(np.uint8), mode="L")
    draw = ImageDraw.Draw(canvas)
    # Remove a hallucinated eye only when both parts are present: an eye-sized
    # horizontal shell comparable to the selected true eyes, plus a compact
    # round iris/pupil core inside that shell. Small round hair, eyebrow or ear
    # marks alone can never trigger deletion.
    selected_components = {id(eye[11]) for eye in eye_pair}
    round_marks = [
        candidate for candidate in candidates
        if candidate[4] >= 0.68
        and 5 <= candidate[5] <= 0.38 * mean_eye_width
        and 5 <= candidate[6] <= 0.95 * mean_eye_height
    ]
    false_groups = []
    for shell in candidates:
        if id(shell[11]) in selected_components:
            continue
        aspect = shell[5] / max(1, shell[6])
        if not (0.62 * mean_eye_width <= shell[5] <= 1.45 * mean_eye_width
                and 0.60 * mean_eye_height <= shell[6] <= 1.45 * mean_eye_height
                and 1.8 <= aspect <= 5.5
                and shell[3] >= 0.12):
            continue
        cores = [
            core for core in round_marks
            if abs(core[0] - shell[0]) <= 0.28 * shell[5]
            and abs(core[1] - shell[1]) <= 0.38 * shell[6]
        ]
        if cores:
            false_groups.append((shell, cores))
    erase_radius = max(1, stroke // 2 + 1)
    for shell, cores in false_groups:
        for component in [shell[11], *(core[11] for core in cores)]:
            for y, x in component:
                draw.rectangle((x - erase_radius, y - erase_radius,
                                x + erase_radius, y + erase_radius), fill=255)
    # This is intentionally a rollback to the human-looking reference style:
    # retain the model's natural layered eyebrows, eyelids, iris and pupil.
    # Point extraction will skeletonize these strokes later; altering the PNG
    # here made the visible portrait increasingly abstract.
    return np.asarray(canvas, dtype=np.uint8)


def preserve_lineart_eyes(image: str | Path, output: str | Path | None = None) -> Path:
    """Delete obvious extra eye icons while preserving the two real eyes."""
    src = Path(image).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(src)
    target = Path(output).expanduser().resolve() if output else src
    gray = np.asarray(Image.open(src).convert("L"))
    result = preserve_eye_semantics_array(gray)
    Image.fromarray(result, mode="L").save(target)
    return target


# Backwards-compatible names for older scripts. Both aliases now perform only
# subtractive extra-eye cleanup; they never apply a standard eye template.
standardize_eye_template_array = preserve_eye_semantics_array
standardize_lineart_eyes = preserve_lineart_eyes


def _binary_erode(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    """Small dependency-free square erosion used only for shape measurement."""
    result = mask.astype(bool, copy=True)
    for _ in range(max(0, iterations)):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        result = np.minimum.reduce([
            padded[dy:dy + result.shape[0], dx:dx + result.shape[1]]
            for dy in range(3) for dx in range(3)
        ])
    return result


def _binary_dilate(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    """Small dependency-free square dilation paired with ``_binary_erode``."""
    result = mask.astype(bool, copy=True)
    for _ in range(max(0, iterations)):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        result = np.maximum.reduce([
            padded[dy:dy + result.shape[0], dx:dx + result.shape[1]]
            for dy in range(3) for dx in range(3)
        ])
    return result


def _largest_binary_component(mask: np.ndarray) -> np.ndarray:
    """Return only the largest 8-connected component in ``mask``."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    largest = []
    for seed_y, seed_x in zip(*np.where(mask)):
        seed_y, seed_x = int(seed_y), int(seed_x)
        if seen[seed_y, seed_x]:
            continue
        seen[seed_y, seed_x] = True
        stack = [(seed_y, seed_x)]
        component = []
        while stack:
            y, x = stack.pop()
            component.append((y, x))
            for dy, dx in NEIGHBORS:
                ny, nx = y + dy, x + dx
                if (0 <= ny < height and 0 <= nx < width
                        and mask[ny, nx] and not seen[ny, nx]):
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if len(component) > len(largest):
            largest = component
    result = np.zeros_like(mask, dtype=bool)
    for y, x in largest:
        result[y, x] = True
    return result


def _fill_binary_holes(mask: np.ndarray) -> np.ndarray:
    """Fill only holes enclosed by a compact source-derived foreground mask."""
    height, width = mask.shape
    background = ~mask
    exterior = np.zeros_like(mask, dtype=bool)
    stack = []
    for x in range(width):
        if background[0, x]:
            stack.append((0, x))
        if height > 1 and background[height - 1, x]:
            stack.append((height - 1, x))
    for y in range(1, max(1, height - 1)):
        if background[y, 0]:
            stack.append((y, 0))
        if width > 1 and background[y, width - 1]:
            stack.append((y, width - 1))
    while stack:
        y, x = stack.pop()
        if exterior[y, x] or not background[y, x]:
            continue
        exterior[y, x] = True
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width and not exterior[ny, nx]:
                stack.append((ny, nx))
    return mask | (background & ~exterior)


def _source_filled_pupil_regions(binary: np.ndarray, min_core_ratio: float = 0.075):
    """Return source-derived solid pupil regions and their normalized scores."""
    candidates, bbox = _eye_component_candidates(binary)
    eye_pair = _select_eye_component_pair(candidates, bbox)
    if not eye_pair:
        return []
    regions = []
    for eye in eye_pair:
        x0, y0, x1, y1 = eye[7], eye[8], eye[9], eye[10]
        roi = binary[y0:y1 + 1, x0:x1 + 1]
        if roi.size == 0:
            continue
        depth = max(2, min(4, int(round(min(eye[5], eye[6]) * 0.07))))
        compact_core = _largest_binary_component(_binary_erode(roi, depth))
        core_area = int(np.count_nonzero(compact_core))
        core_ratio = core_area / roi.size
        if core_area == 0 or core_ratio < min_core_ratio:
            continue
        ys, xs = np.where(compact_core)
        core_width = int(xs.max() - xs.min() + 1)
        core_height = int(ys.max() - ys.min() + 1)
        core_cx = (float(xs.min()) + float(xs.max())) / 2.0
        core_cy = (float(ys.min()) + float(ys.max())) / 2.0
        if not (0.14 * roi.shape[1] <= core_cx <= 0.86 * roi.shape[1]
                and 0.08 * roi.shape[0] <= core_cy <= 0.92 * roi.shape[0]
                and core_width <= 0.48 * roi.shape[1]
                and core_height <= 0.88 * roi.shape[0]
                and 0.42 <= core_width / max(1, core_height) <= 1.85):
            continue
        source_mass = _binary_dilate(compact_core, depth + 1) & roi
        source_mass = _fill_binary_holes(source_mass)
        regions.append((x0, y0, x1, y1, source_mass, core_ratio))
    return regions


def filled_pupil_mass_score(image: str | Path | np.ndarray) -> float:
    """Measure large solid iris/pupil masses for generation quality control."""
    if isinstance(image, np.ndarray):
        gray = image
    else:
        gray = np.asarray(Image.open(Path(image)).convert("L"))
    if gray.ndim != 2:
        raise ValueError("眼睛质量检测只接受灰度图像。")
    return float(sum(region[5] for region in _source_filled_pupil_regions(gray < 180)))


def has_confident_eye_pair(image: str | Path | np.ndarray) -> bool:
    """Return whether two source eye components are structurally identifiable."""
    if isinstance(image, np.ndarray):
        gray = image
    else:
        gray = np.asarray(Image.open(Path(image)).convert("L"))
    if gray.ndim != 2:
        return False
    candidates, bbox = _eye_component_candidates(gray < 180)
    return len(_select_eye_component_pair(candidates, bbox)) == 2


def outline_source_filled_pupil_regions(binary: np.ndarray) -> np.ndarray:
    """Trace a source pupil mass once instead of skeletonizing it into branches.

    A large solid iris/pupil patch has no meaningful centreline. Direct thinning
    turns it into triangular forks and multiple retraced loops. This routine is
    deliberately limited to a confidently selected real eye pair and to a very
    thick, compact source region inside each eye. It keeps that region's own
    outer silhouette and position, but removes its filled interior before path
    extraction. It never stamps an ellipse, moves a pupil, or invents a spiral.
    The visible PNG is not changed.
    """
    result = binary.copy()
    # Path extraction also outlines a moderate compact filled pupil. The lower
    # threshold is safe here because the compact-core aspect test rejects long
    # eyelid and iris strokes; quality-control retries remain limited to large
    # masses via the higher default threshold above.
    for x0, y0, x1, y1, source_mass, _score in _source_filled_pupil_regions(binary, min_core_ratio=0.035):
        boundary = source_mass & ~_binary_erode(source_mass, 1)
        eye_result = result[y0:y1 + 1, x0:x1 + 1]
        eye_result[source_mass] = False
        eye_result[boundary] = True
        result[y0:y1 + 1, x0:x1 + 1] = eye_result
    return result


def prepare_eye_interiors_for_paths(binary: np.ndarray):
    """Preserve native eyelid, iris and pupil contours for robot tracing.

    A confidently detected large solid pupil patch is reduced to its own outer
    contour so thinning cannot create internal forks. Otherwise the real eye is
    untouched. Only eyebrow bands receive a one-pixel closing pass. No synthetic
    pupil, iris, highlight, or template path is created.
    """
    return close_eyebrow_raster_gaps(outline_source_filled_pupil_regions(binary))


def close_eyebrow_raster_gaps(binary: np.ndarray) -> np.ndarray:
    """Close one-pixel gaps only inside source-derived eyebrow bands."""
    candidates, bbox = _eye_component_candidates(binary)
    eye_pair = _select_eye_component_pair(candidates, bbox)
    if not eye_pair:
        return binary
    result = binary.copy()
    height, width = binary.shape
    for eye in eye_pair:
        cx, cy, eye_width, eye_height = eye[0], eye[1], eye[5], eye[6]
        x0 = max(0, int(round(cx - 0.62 * eye_width)))
        x1 = min(width, int(round(cx + 0.62 * eye_width)) + 1)
        # Derive this band from the detected eye height so it remains clearly
        # above the upper eyelid for both narrow and open eyes.
        y0 = max(0, int(round(cy - 2.55 * eye_height)))
        y1 = min(height, int(round(cy - 0.72 * eye_height)) + 1)
        if x1 - x0 < 3 or y1 - y0 < 3:
            continue
        roi = binary[y0:y1, x0:x1]
        padded = np.pad(roi, 1, mode="constant", constant_values=False)
        dilated = np.maximum.reduce([
            padded[dy:dy + roi.shape[0], dx:dx + roi.shape[1]]
            for dy in range(3) for dx in range(3)
        ])
        padded = np.pad(dilated, 1, mode="constant", constant_values=False)
        closed = np.minimum.reduce([
            padded[dy:dy + roi.shape[0], dx:dx + roi.shape[1]]
            for dy in range(3) for dx in range(3)
        ])
        result[y0:y1, x0:x1] = closed
    return result


def prune_hair_terminal_spurs(skel: np.ndarray, max_length_px: int = 20) -> np.ndarray:
    """Remove only tiny outward terminal branches in the upper hair region.

    These branches are commonly introduced where a thick cartoon hair stroke
    intersects another stroke during raster thinning. The main contour is
    protected: only an endpoint-to-junction branch of at most
    ``max_length_px`` pixels is removed, and only when its endpoint points
    radially away from the head centre. Facial features and long hair locks
    are never touched.
    """
    points = {(int(y), int(x)) for y, x in zip(*np.where(skel))}
    if not points:
        return skel
    adjacency = {point: graph_neighbors(point, points) for point in points}
    min_y = min(y for y, _ in points)
    max_y = max(y for y, _ in points)
    span_y = max(1, max_y - min_y)
    centre_x = (min(x for _, x in points) + max(x for _, x in points)) / 2.0
    hair_centre_y = min_y + 0.20 * span_y
    remove = set()
    for endpoint, neighbours in adjacency.items():
        if len(neighbours) != 1:
            continue
        path = [endpoint]
        previous = None
        current = endpoint
        while True:
            choices = [nxt for nxt in adjacency[current] if nxt != previous]
            if not choices:
                break
            nxt = choices[0]
            path.append(nxt)
            previous, current = current, nxt
            if len(adjacency[current]) != 2 or len(path) > max_length_px + 1:
                break
        if len(path) < 2 or len(path) > max_length_px + 1 or len(adjacency[current]) < 3:
            continue
        endpoint_y, endpoint_x = endpoint
        norm_y = (endpoint_y - min_y) / span_y
        if norm_y > 0.36:
            continue
        # Endpoint-to-junction radial direction; positive dot means outward.
        radial = (endpoint_x - centre_x, endpoint_y - hair_centre_y)
        branch = (endpoint_x - current[1], endpoint_y - current[0])
        radial_norm = math.hypot(*radial)
        branch_norm = math.hypot(*branch)
        if radial_norm == 0 or branch_norm == 0:
            continue
        if (radial[0] * branch[0] + radial[1] * branch[1]) / (radial_norm * branch_norm) < 0.20:
            continue
        remove.update(path[:-1])
    if not remove:
        return skel
    result = skel.copy()
    for y, x in remove:
        result[y, x] = False
    return result


def simplify_eyebrow_components(skel: np.ndarray) -> np.ndarray:
    """Reduce each thick eyebrow skeleton to one continuous centreline."""
    points = {(int(y), int(x)) for y, x in zip(*np.where(skel))}
    if not points:
        return skel
    min_y = min(y for y, _ in points); max_y = max(y for y, _ in points)
    min_x = min(x for _, x in points); max_x = max(x for _, x in points)
    span_y = max(1, max_y - min_y); span_x = max(1, max_x - min_x)
    remaining = set(points)
    components = []
    while remaining:
        seed = min(remaining); remaining.remove(seed)
        component = {seed}; stack = [seed]
        while stack:
            point = stack.pop()
            for nxt in graph_neighbors(point, points):
                if nxt in remaining:
                    remaining.remove(nxt); component.add(nxt); stack.append(nxt)
        components.append(component)

    def shortest_path(component, start, goal):
        import heapq
        queue = [(0.0, start)]
        distance = {start: 0.0}
        parent = {}
        while queue:
            cost, point = heapq.heappop(queue)
            if cost != distance.get(point):
                continue
            if point == goal:
                break
            for nxt in graph_neighbors(point, component):
                step = math.hypot(nxt[1] - point[1], nxt[0] - point[0])
                new_cost = cost + step
                if new_cost < distance.get(nxt, float("inf")):
                    distance[nxt] = new_cost; parent[nxt] = point
                    heapq.heappush(queue, (new_cost, nxt))
        if goal not in distance:
            return []
        path = [goal]
        while path[-1] != start:
            path.append(parent[path[-1]])
        path.reverse()
        return path

    result = skel.copy()
    for component in components:
        xs = [x for _, x in component]; ys = [y for y, _ in component]
        adjacency = {point: graph_neighbors(point, component) for point in component}
        endpoints = [point for point, neighbours in adjacency.items() if len(neighbours) == 1]
        has_junction = any(len(neighbours) > 2 for neighbours in adjacency.values())
        width = (max(xs) - min(xs)) / span_x
        height = (max(ys) - min(ys)) / span_y
        centre_y = ((min(ys) + max(ys)) / 2.0 - min_y) / span_y
        centre_x = ((min(xs) + max(xs)) / 2.0 - min_x) / span_x
        is_eyebrow = (
            0.33 <= centre_y <= 0.42
            and 0.08 <= width <= 0.24
            and height <= 0.055
            and (0.22 <= centre_x <= 0.48 or 0.52 <= centre_x <= 0.78)
            # A drawable eyebrow is an open, non-branching stroke.  Eye
            # outlines, irises and pupils are closed loops or form junctions
            # when their thick raster lines touch.  Never collapse those
            # structures into a left-to-right centreline.
            and len(endpoints) >= 2
            and not has_junction
        )
        if not is_eyebrow:
            continue
        candidates = endpoints
        left = min(candidates, key=lambda point: point[1])
        right = max(candidates, key=lambda point: point[1])
        centreline = shortest_path(component, left, right)
        if len(centreline) < 2:
            continue
        for y, x in component:
            result[y, x] = False
        for y, x in centreline:
            result[y, x] = True

    # Some model outputs encode one eyebrow as many short hatch strokes. If
    # those strokes are dense in a source-derived eyebrow band, keep their
    # median envelope as one smooth cubic-like arc. This affects only robot
    # paths; the visible PNG and the real eye contours remain untouched.
    eye_candidates, eye_bbox = _eye_component_candidates(skel)
    eye_pair = _select_eye_component_pair(eye_candidates, eye_bbox)
    if eye_pair:
        height, width = skel.shape
        for eye in eye_pair:
            cx, cy, eye_width, eye_height = eye[0], eye[1], eye[5], eye[6]
            x0 = max(0, int(round(cx - 0.85 * eye_width)))
            x1 = min(width - 1, int(round(cx + 0.85 * eye_width)))
            y0 = max(0, int(round(cy - 2.80 * eye_height)))
            y1 = min(height - 1, int(round(cy - 0.78 * eye_height)))
            roi = skel[y0:y1 + 1, x0:x1 + 1]
            occupied = np.count_nonzero(np.any(roi, axis=0))
            density = np.count_nonzero(roi) / max(occupied, 1)
            if occupied < 12 or density <= 2.0:
                continue
            samples = []
            for x in range(x0, x1 + 1):
                ys = np.where(skel[y0:y1 + 1, x])[0] + y0
                if len(ys):
                    samples.append((x, float(np.percentile(ys, 45))))
            if len(samples) < 10:
                continue
            xs = np.asarray([item[0] for item in samples], dtype=float)
            ys = np.asarray([item[1] for item in samples], dtype=float)
            span = max(float(np.ptp(xs)), 1.0)
            centre_x = xs.mean()
            normalized = (xs - centre_x) / span
            degree = 3 if len(samples) >= 18 else 2
            coefficients = np.polyfit(normalized, ys, degree)
            fitted_xs = np.arange(int(xs.min()), int(xs.max()) + 1, dtype=float)
            fitted = np.polyval(coefficients, (fitted_xs - centre_x) / span)
            fitted = np.clip(fitted, y0, y1)
            for y, x in np.argwhere(roi):
                result[y0 + int(y), x0 + int(x)] = False
            curve = [(int(round(y)), int(round(x))) for x, y in zip(fitted_xs, fitted)]
            for (y_a, x_a), (y_b, x_b) in zip(curve, curve[1:]):
                steps = max(abs(y_b - y_a), abs(x_b - x_a), 1)
                for index in range(steps + 1):
                    y = round(y_a + (y_b - y_a) * index / steps)
                    x = round(x_a + (x_b - x_a) * index / steps)
                    result[y, x] = True
    return result


def regularize_front_hairline(skel: np.ndarray, binary: np.ndarray) -> np.ndarray:
    """Replace a fragmented central fringe with one continuous centreline."""
    ys_all, xs_all = np.where(skel)
    if len(xs_all) == 0:
        return skel
    min_x, max_x = int(xs_all.min()), int(xs_all.max())
    min_y, max_y = int(ys_all.min()), int(ys_all.max())
    span_x = max(1, max_x - min_x); span_y = max(1, max_y - min_y)
    x0 = int(round(min_x + 0.27 * span_x)); x1 = int(round(min_x + 0.73 * span_x))
    y0 = int(round(min_y + 0.20 * span_y)); y1 = int(round(min_y + 0.355 * span_y))
    samples = {}
    for x in range(x0, x1 + 1):
        candidates = np.where(binary[y0:y1 + 1, x])[0]
        if len(candidates) == 0:
            continue
        bottom = y0 + int(candidates[-1])
        top = bottom
        while top > y0 and binary[top - 1, x]:
            top -= 1
        samples[x] = (top + bottom) / 2.0
    if len(samples) < 0.35 * (x1 - x0 + 1):
        return skel

    # Interpolate modest gaps, then keep the longest dense run.
    known = sorted(samples)
    for left, right in zip(known, known[1:]):
        gap = right - left
        if 1 < gap <= 28:
            ya, yb = samples[left], samples[right]
            for x in range(left + 1, right):
                samples[x] = ya + (yb - ya) * (x - left) / gap
    runs = []
    current = []
    for x in sorted(samples):
        if current and x != current[-1] + 1:
            runs.append(current); current = []
        current.append(x)
    if current:
        runs.append(current)
    run = max(runs, key=len)
    if len(run) < 0.30 * (x1 - x0 + 1):
        return skel

    values = [samples[x] for x in run]
    # Median removes pixel spikes; a short moving average keeps broad locks.
    median = []
    for index in range(len(values)):
        window = values[max(0, index - 3):min(len(values), index + 4)]
        median.append(float(np.median(window)))
    smooth = []
    for index in range(len(median)):
        window = median[max(0, index - 4):min(len(median), index + 5)]
        smooth.append(sum(window) / len(window))

    result = skel.copy()
    curve = {x: int(round(y)) for x, y in zip(run, smooth)}
    # Remove the old thick-line skeleton only in a narrow fringe corridor.
    for x, centre_y in curve.items():
        lo = max(0, centre_y - 11); hi = min(result.shape[0], centre_y + 12)
        result[lo:hi, x] = False

    def draw_segment(a, b):
        y0p, x0p = a; y1p, x1p = b
        steps = max(abs(y1p - y0p), abs(x1p - x0p))
        if steps == 0:
            result[y0p, x0p] = True
            return
        for step in range(steps + 1):
            y = round(y0p + (y1p - y0p) * step / steps)
            x = round(x0p + (x1p - x0p) * step / steps)
            result[y, x] = True

    points = [(curve[x], x) for x in run]
    for a, b in zip(points, points[1:]):
        draw_segment(a, b)
    return result


def edge_disjoint_component_trails(
    skel: np.ndarray,
    min_pixels: int,
) -> list[list[tuple[int, int]]]:
    """Cover every skeleton edge exactly once without pen-down retracing.

    Each connected component is converted into a minimum-size set of Euler
    trails. At graph branches, the current pen-down stroke ends and a later
    stroke resumes from another branch; no existing edge is traversed back to
    the start. This avoids the physical double lines caused by backtracking.
    """
    all_points = {(int(y), int(x)) for y, x in zip(*np.where(skel))}
    remaining = set(all_points)
    components = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        component = {seed}
        stack = [seed]
        while stack:
            point = stack.pop()
            for nxt in graph_neighbors(point, all_points):
                if nxt in remaining:
                    remaining.remove(nxt)
                    component.add(nxt)
                    stack.append(nxt)
        if len(component) >= min_pixels:
            components.append(component)

    trails = []
    for component_index, component in enumerate(components):
        edges = []
        adjacency = {point: [] for point in component}
        for point in sorted(component):
            for nxt in graph_neighbors(point, component):
                if point < nxt:
                    edge_id = len(edges)
                    edges.append((point, nxt, False))
                    adjacency[point].append((nxt, edge_id))
                    adjacency[nxt].append((point, edge_id))
        if not edges:
            continue

        odd = [point for point in component if len(adjacency[point]) % 2 == 1]
        super_node = (-10_000_000 - component_index, -10_000_000)
        virtual_ids = set()
        if odd:
            adjacency[super_node] = []
            for point in odd:
                edge_id = len(edges)
                edges.append((super_node, point, True))
                virtual_ids.add(edge_id)
                adjacency[super_node].append((point, edge_id))
                adjacency[point].append((super_node, edge_id))
            start = super_node
        else:
            start = min(component)

        # Hierholzer Euler circuit over actual + virtual edges.
        local_adj = {point: list(items) for point, items in adjacency.items()}
        used_edges = set()
        vertex_stack = [start]
        incoming_stack = []
        reverse_vertices = []
        reverse_edges = []
        while vertex_stack:
            point = vertex_stack[-1]
            while local_adj[point] and local_adj[point][-1][1] in used_edges:
                local_adj[point].pop()
            if local_adj[point]:
                nxt, edge_id = local_adj[point].pop()
                if edge_id in used_edges:
                    continue
                used_edges.add(edge_id)
                vertex_stack.append(nxt)
                incoming_stack.append(edge_id)
            else:
                reverse_vertices.append(vertex_stack.pop())
                if incoming_stack:
                    reverse_edges.append(incoming_stack.pop())

        vertices = list(reversed(reverse_vertices))
        ordered_edges = list(reversed(reverse_edges))
        if not odd:
            if len(vertices) >= 2:
                trails.append(vertices)
            continue

        # Removing virtual super-node edges splits the Euler circuit into
        # open trails. All remaining actual edges occur exactly once.
        current = []
        for index, edge_id in enumerate(ordered_edges):
            a, b = vertices[index], vertices[index + 1]
            if edge_id in virtual_ids:
                if len(current) >= 2:
                    trails.append(current)
                current = []
                continue
            if not current:
                current = [a]
            current.append(b)
        if len(current) >= 2:
            trails.append(current)

    trails.sort(key=lambda path: (min(y for y, _ in path), min(x for _, x in path)))
    return trails


def semantic_contour_trails(
    skel: np.ndarray,
    min_pixels: int,
    *,
    max_pair_cosine: float = 0.25,
) -> list[list[tuple[int, int]]]:
    """Trace each semantic contour once, continuing straight at junctions.

    The skeleton is first divided into segments between endpoints/junctions.
    At each junction, incident segment ends are paired by tangent direction:
    the most nearly opposite tangent vectors are treated as the same visual
    contour. Branches that do not continue naturally become separate pen-down
    strokes. Every skeleton segment is emitted exactly once, so there is no
    physical backtracking and no forced fragmentation at every junction.
    """
    all_points = {(int(y), int(x)) for y, x in zip(*np.where(skel))}
    global_min_y = min((y for y, _ in all_points), default=0)
    global_max_y = max((y for y, _ in all_points), default=1)
    global_span_y = max(1, global_max_y - global_min_y)
    remaining = set(all_points)
    components = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        component = {seed}
        stack = [seed]
        while stack:
            point = stack.pop()
            for nxt in graph_neighbors(point, all_points):
                if nxt in remaining:
                    remaining.remove(nxt)
                    component.add(nxt)
                    stack.append(nxt)
        if len(component) >= min_pixels:
            components.append(component)

    def edge_key(a, b):
        return (a, b) if a <= b else (b, a)

    output = []
    for component in components:
        adjacency = {point: graph_neighbors(point, component) for point in component}
        nodes = {point for point, neighbors in adjacency.items() if len(neighbors) != 2}
        visited_edges = set()
        segments = []

        # Open/junction-to-junction segments.
        for node in sorted(nodes):
            for first in adjacency[node]:
                edge = edge_key(node, first)
                if edge in visited_edges:
                    continue
                visited_edges.add(edge)
                path = [node, first]
                prev, current = node, first
                while current not in nodes:
                    choices = [nxt for nxt in adjacency[current] if nxt != prev]
                    if not choices:
                        break
                    nxt = choices[0]
                    edge = edge_key(current, nxt)
                    if edge in visited_edges:
                        break
                    visited_edges.add(edge)
                    path.append(nxt)
                    prev, current = current, nxt
                if len(path) >= 2:
                    segments.append(path)

        # Pure closed loops, or any edges not reached above.
        for point in sorted(component):
            for first in adjacency[point]:
                edge = edge_key(point, first)
                if edge in visited_edges:
                    continue
                visited_edges.add(edge)
                path = [point, first]
                prev, current = point, first
                while True:
                    choices = [
                        nxt for nxt in adjacency[current]
                        if nxt != prev and edge_key(current, nxt) not in visited_edges
                    ]
                    if not choices:
                        break
                    nxt = choices[0]
                    visited_edges.add(edge_key(current, nxt))
                    path.append(nxt)
                    prev, current = current, nxt
                    if current == point:
                        break
                if len(path) >= 2:
                    segments.append(path)

        if not segments:
            continue

        # Record each segment-end tangent pointing away from its junction.
        incidence = {}
        endpoint_nodes = {}
        for segment_id, path in enumerate(segments):
            if path[0] == path[-1]:
                continue
            lookahead = min(6, len(path) - 1)
            for side in (0, 1):
                if side == 0:
                    node = path[0]
                    sample = path[lookahead]
                else:
                    node = path[-1]
                    sample = path[-1 - lookahead]
                endpoint_nodes[(segment_id, side)] = node
                vector = (float(sample[1] - node[1]), float(sample[0] - node[0]))
                incidence.setdefault(node, []).append((segment_id, side, vector))

        transitions = {}
        for node, ends in incidence.items():
            node_norm_y = (node[0] - global_min_y) / global_span_y
            # Hair and eyebrow strokes are intentionally broad cartoon curves;
            # raster junctions there often meet at a sharper angle than a
            # mathematical straight continuation. Permit those local turns to
            # stay in one pen-down contour, while keeping stricter pairing for
            # eyes, nose, mouth and clothing.
            pair_limit = 0.65 if node_norm_y < 0.42 else max_pair_cosine
            available = list(ends)
            while len(available) >= 2:
                best = None
                for i in range(len(available)):
                    for j in range(i + 1, len(available)):
                        a = available[i][2]
                        b = available[j][2]
                        na = math.hypot(*a); nb = math.hypot(*b)
                        if na == 0 or nb == 0:
                            continue
                        score = (a[0] * b[0] + a[1] * b[1]) / (na * nb)
                        if best is None or score < best[0]:
                            best = (score, i, j)
                if best is None or best[0] > pair_limit:
                    break
                _, i, j = best
                left = available[i][:2]
                right = available[j][:2]
                transitions[left] = right
                transitions[right] = left
                for index in sorted((i, j), reverse=True):
                    del available[index]

        used_segments = set()

        def trace(start_segment, start_side):
            trail = []
            segment_id = start_segment
            side = start_side
            while segment_id not in used_segments:
                used_segments.add(segment_id)
                path = segments[segment_id]
                oriented = path if side == 0 else list(reversed(path))
                if trail:
                    trail.extend(oriented[1:] if trail[-1] == oriented[0] else oriented)
                else:
                    trail.extend(oriented)
                exit_side = 1 - side
                nxt = transitions.get((segment_id, exit_side))
                if nxt is None or nxt[0] in used_segments:
                    break
                segment_id, side = nxt
            return trail

        # Start with natural open ends, so semantic contours are not cut in
        # the middle merely because of segment ordering.
        open_ends = []
        for segment_id, path in enumerate(segments):
            if path[0] == path[-1]:
                continue
            for side in (0, 1):
                if (segment_id, side) not in transitions:
                    open_ends.append((segment_id, side))
        open_ends.sort(key=lambda item: endpoint_nodes.get(item, (0, 0)))
        for segment_id, side in open_ends:
            if segment_id not in used_segments:
                trail = trace(segment_id, side)
                if len(trail) >= 2:
                    output.append(trail)

        # Remaining paired cycles and pure closed loops.
        for segment_id, path in enumerate(segments):
            if segment_id in used_segments:
                continue
            if path[0] == path[-1]:
                used_segments.add(segment_id)
                output.append(path)
            else:
                trail = trace(segment_id, 0)
                if len(trail) >= 2:
                    output.append(trail)

    output.sort(key=lambda path: (min(y for y, _ in path), min(x for _, x in path)))
    return output


def skeleton_paths(skel: np.ndarray, min_pixels: int) -> list[list[tuple[int, int]]]:
    points = {(int(y), int(x)) for y, x in zip(*np.where(skel))}
    if not points:
        return []

    def nbrs(p):
        y, x = p
        return [(y + dy, x + dx) for dy, dx in NEIGHBORS if (y + dy, x + dx) in points]

    degree = {p: len(nbrs(p)) for p in points}
    nodes = {p for p, d in degree.items() if d != 2}
    visited_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    paths: list[list[tuple[int, int]]] = []

    def edge_key(a, b):
        return (a, b) if a <= b else (b, a)

    def trace(start, first):
        path = [start]
        prev, cur = start, first
        visited_edges.add(edge_key(prev, cur))
        path.append(cur)
        while cur not in nodes:
            choices = [q for q in nbrs(cur) if q != prev]
            if not choices:
                break
            nxt = choices[0]
            e = edge_key(cur, nxt)
            if e in visited_edges:
                break
            visited_edges.add(e)
            prev, cur = cur, nxt
            path.append(cur)
        return path

    for node in sorted(nodes):
        for nxt in nbrs(node):
            if edge_key(node, nxt) not in visited_edges:
                path = trace(node, nxt)
                if len(path) >= min_pixels:
                    paths.append(path)

    # Components made entirely of degree-2 pixels are closed loops. Find each
    # remaining component once; avoid quadratic set construction on large art.
    used = {p for path in paths for p in path}
    remaining = points - used
    while remaining:
        seed = min(remaining)
        component = {seed}
        stack = [seed]
        while stack:
            cur = stack.pop()
            for nxt in nbrs(cur):
                if nxt in remaining and nxt not in component:
                    component.add(nxt)
                    stack.append(nxt)
        remaining -= component
        if len(component) < min_pixels:
            continue
        start = min(component)
        loop = [start]
        prev = None
        cur = start
        while True:
            choices = [q for q in nbrs(cur) if q != prev and q in component]
            if not choices:
                break
            nxt = choices[0]
            if nxt == start and len(loop) > 2:
                loop.append(start)
                break
            if nxt in loop:
                break
            loop.append(nxt)
            prev, cur = cur, nxt
        if len(loop) >= min_pixels:
            paths.append(loop)
    return paths


def stitch_paths(
    paths: list[list[tuple[int, int]]],
    *,
    max_gap_px: float = 2.0,
    min_cosine: float = -0.5,
) -> list[list[tuple[int, int]]]:
    """Join skeleton fragments that meet at a node or a tiny raster gap.

    Zhang-Suen skeletons are split at every junction.  For pen plotting, two
    fragments can remain one continuous pen-down stroke when their endpoints
    are close and their tangents continue in roughly the same direction.  This
    pass joins only such compatible endpoint pairs; it never connects distant
    facial features or separate connected components.
    """
    work = [list(path) for path in paths if len(path) >= 2]

    def tangent(path: list[tuple[int, int]], at_start: bool) -> tuple[float, float]:
        if at_start:
            a, b = path[0], path[1]
        else:
            a, b = path[-2], path[-1]
        return float(b[1] - a[1]), float(b[0] - a[0])

    def cosine(a: tuple[float, float], b: tuple[float, float]) -> float:
        na = math.hypot(*a); nb = math.hypot(*b)
        if na == 0 or nb == 0:
            return -1.0
        return (a[0] * b[0] + a[1] * b[1]) / (na * nb)

    def candidate(i: int, j: int):
        best = None
        for rev_i in (False, True):
            left = work[i][::-1] if rev_i else work[i]
            for rev_j in (False, True):
                right = work[j][::-1] if rev_j else work[j]
                a, b = left[-1], right[0]
                distance = math.hypot(b[1] - a[1], b[0] - a[0])
                if distance > max_gap_px:
                    continue
                score_cos = cosine(tangent(left, False), tangent(right, True))
                if score_cos < min_cosine:
                    continue
                score = distance + (1.0 - score_cos) * 0.75
                item = (score, left, right)
                if best is None or score < best[0]:
                    best = item
        return best

    while len(work) > 1:
        best_pair = None
        for i in range(len(work)):
            for j in range(i + 1, len(work)):
                item = candidate(i, j)
                if item is not None and (best_pair is None or item[0] < best_pair[0]):
                    best_pair = (item[0], i, j, item[1], item[2])
        if best_pair is None:
            break
        _, i, j, left, right = best_pair
        if left[-1] != right[0]:
            # Bridge only a tiny rasterization gap with integer pixels.
            y1, x1 = left[-1]
            y2, x2 = right[0]
            steps = max(abs(y2 - y1), abs(x2 - x1))
            bridge = [
                (round(y1 + (y2 - y1) * k / steps), round(x1 + (x2 - x1) * k / steps))
                for k in range(1, steps)
            ] if steps else []
        else:
            bridge = []
        merged = left + bridge + right[1:]
        work[i] = merged
        del work[j]
    return work


def continuous_component_walks(
    skel: np.ndarray,
    min_pixels: int,
) -> list[list[tuple[int, int]]]:
    """Return one continuous pen-down walk for each skeleton component.

    The walk covers every skeleton edge. At branches it backtracks along the
    existing line instead of lifting the pen or drawing a shortcut across
    white space. This deliberately trades some retracing for continuity.
    """
    all_points = {(int(y), int(x)) for y, x in zip(*np.where(skel))}
    components: list[set[tuple[int, int]]] = []
    remaining = set(all_points)
    while remaining:
        seed = min(remaining)
        component = {seed}
        stack = [seed]
        remaining.remove(seed)
        while stack:
            y, x = stack.pop()
            for dy, dx in NEIGHBORS:
                nxt = (y + dy, x + dx)
                if nxt in remaining:
                    remaining.remove(nxt)
                    component.add(nxt)
                    stack.append(nxt)
        if len(component) >= min_pixels:
            components.append(component)

    walks: list[list[tuple[int, int]]] = []
    for component in components:
        def neighbors(point):
            y, x = point
            return sorted(
                (y + dy, x + dx)
                for dy, dx in NEIGHBORS
                if (y + dy, x + dx) in component
            )

        degree = {point: len(neighbors(point)) for point in component}
        endpoints = [point for point, value in degree.items() if value == 1]
        start = min(endpoints) if endpoints else min(component)
        visited_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
        walk = [start]

        def edge_key(a, b):
            return (a, b) if a <= b else (b, a)

        # Iterative depth-first edge traversal. Appending the parent after
        # returning creates an adjacent-pixel backtrack, never a jump.
        stack = [(start, iter(neighbors(start)))]
        while stack:
            point, choices = stack[-1]
            try:
                nxt = next(choices)
            except StopIteration:
                stack.pop()
                if stack:
                    walk.append(stack[-1][0])
                continue
            edge = edge_key(point, nxt)
            if edge in visited_edges:
                continue
            visited_edges.add(edge)
            walk.append(nxt)
            stack.append((nxt, iter(neighbors(nxt))))
        if len(walk) >= 2:
            walks.append(walk)
    walks.sort(key=lambda path: (min(y for y, _ in path), min(x for _, x in path)))
    return walks


def resample(path_xy, spacing_mm: float):
    if len(path_xy) < 2:
        return path_xy
    out = [path_xy[0]]
    carry = 0.0
    for a, b in zip(path_xy, path_xy[1:]):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        dist = spacing_mm - carry
        while dist <= length:
            t = dist / length
            out.append((ax + dx * t, ay + dy * t))
            dist += spacing_mm
        carry = length - (dist - spacing_mm)
    if out[-1] != path_xy[-1]:
        out.append(path_xy[-1])
    return out


def smooth_eye_path(path_xy, closed: bool):
    """Apply one conservative Chaikin pass to a small eye contour.

    The robot executes straight segments between TXT points. A single corner
    cutting pass removes raster stair-steps while retaining the original eye
    position and scale. Endpoints of open eyelid strokes stay fixed; closed
    iris/pupil rings remain closed.
    """
    if len(path_xy) < 4:
        return path_xy
    core = list(path_xy[:-1]) if closed and path_xy[0] == path_xy[-1] else list(path_xy)
    if len(core) < 3:
        return path_xy
    result = []
    if closed:
        for i, point in enumerate(core):
            nxt = core[(i + 1) % len(core)]
            q = (0.75 * point[0] + 0.25 * nxt[0], 0.75 * point[1] + 0.25 * nxt[1])
            r = (0.25 * point[0] + 0.75 * nxt[0], 0.25 * point[1] + 0.75 * nxt[1])
            result.extend((q, r))
        result.append(result[0])
    else:
        result = [core[0]]
        for point, nxt in zip(core, core[1:]):
            result.extend((
                (0.75 * point[0] + 0.25 * nxt[0], 0.75 * point[1] + 0.25 * nxt[1]),
                (0.25 * point[0] + 0.75 * nxt[0], 0.25 * point[1] + 0.75 * nxt[1]),
            ))
        result.append(core[-1])
    return result


def image_to_paths(
    image: str | Path,
    width_mm: float = 152.4,
    height_mm: float = 152.4,
    margin_mm: float = 5.0,
    spacing_mm: float = 1.0,
    threshold: int = 180,
    min_pixels: int = 8,
    min_stroke_mm: float = 0.0,
    stitch_gap_px: float = 2.0,
    continuous_components: bool = False,
    origin: str = "top-left",
):
    """Return ordered paths in drawing-area millimetres and the pixel scale."""
    src = Path(image).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"找不到输入图片：{src}")
    gray = np.asarray(Image.open(src).convert("L"))
    # The preview and robot trajectory share the model-drawn eye semantics.
    # Only obvious extra eye icons may be deleted; real eyelids, iris, pupil,
    # eye white and gaze are never replaced by a deterministic template.
    gray = preserve_eye_semantics_array(gray)
    source_binary = gray < threshold
    binary = prepare_eye_interiors_for_paths(source_binary)
    skeleton = zhang_suen(binary)
    skeleton = prune_hair_terminal_spurs(skeleton)
    skeleton = simplify_eyebrow_components(skeleton)
    if continuous_components:
        paths_px = continuous_component_walks(skeleton, min_pixels)
    else:
        paths_px = semantic_contour_trails(skeleton, min_pixels)
        if paths_px:
            path_min_y = min(y for path in paths_px for y, _ in path)
            path_max_y = max(y for path in paths_px for y, _ in path)
            path_span_y = max(1, path_max_y - path_min_y)
            upper_limit = path_min_y + 0.43 * path_span_y
            upper = [path for path in paths_px if max(y for y, _ in path) <= upper_limit]
            lower = [path for path in paths_px if max(y for y, _ in path) > upper_limit]
            upper = stitch_paths(
                upper,
                max_gap_px=max(1.0, stitch_gap_px),
                min_cosine=-0.95,
            )
            paths_px = upper + lower
    if not paths_px:
        raise SystemExit("没有检测到可绘制线条，请降低 --threshold 或检查输入图片。")

    all_xy = [(x, y) for path in paths_px for y, x in path]
    min_x = min(x for x, _ in all_xy); max_x = max(x for x, _ in all_xy)
    min_y = min(y for _, y in all_xy); max_y = max(y for _, y in all_xy)
    span_x = max(1, max_x - min_x); span_y = max(1, max_y - min_y)
    if width_mm <= 2 * margin_mm or height_mm <= 2 * margin_mm:
        raise ValueError("画布尺寸必须大于两倍边距。")
    if spacing_mm <= 0:
        raise ValueError("点间距必须大于 0。")
    if min_stroke_mm < 0:
        raise ValueError("最短线段长度不能小于 0。")
    scale = min((width_mm - 2 * margin_mm) / span_x, (height_mm - 2 * margin_mm) / span_y)
    used_w, used_h = span_x * scale, span_y * scale
    off_x = (width_mm - used_w) / 2
    off_y = (height_mm - used_h) / 2

    def to_mm(p):
        y, x = p
        xx = off_x + (x - min_x) * scale
        yy = off_y + (y - min_y) * scale
        if origin == "bottom-left":
            yy = height_mm - yy
        return xx, yy

    paths_mm = []
    for path in paths_px:
        converted = [to_mm(p) for p in path]
        physical_length = sum(
            math.hypot(bx - ax, by - ay)
            for (ax, ay), (bx, by) in zip(converted, converted[1:])
        )
        # Thick raster strokes can leave tiny terminal spurs around sharp
        # corners after thinning. They are not meaningful semantic strokes at
        # plotter scale and create unnecessary pen lifts. Filtering only these
        # very short standalone paths preserves all normal contours and never
        # joins unrelated parts of the drawing.
        if min_stroke_mm > 0 and physical_length < min_stroke_mm:
            continue
        # Orient each open stroke from upper/left endpoint; closed loops use their top-left point.
        if converted[-1][1] < converted[0][1] or (converted[-1][1] == converted[0][1] and converted[-1][0] < converted[0][0]):
            converted.reverse()
        # Keep small closed eye contours round instead of reducing them to a
        # 4-5 point polygon. Only these tiny loops receive denser sampling;
        # all long semantic contours retain the requested global spacing.
        is_closed = len(converted) >= 3 and math.dist(converted[0], converted[-1]) < 1e-6
        local_spacing = spacing_mm
        detail_xs = [point[0] for point in converted]
        detail_ys = [point[1] for point in converted]
        detail_width = max(detail_xs) - min(detail_xs)
        detail_height = max(detail_ys) - min(detail_ys)
        detail_centre_x = (min(detail_xs) + max(detail_xs)) / 2.0
        detail_centre_y = (min(detail_ys) + max(detail_ys)) / 2.0
        detail_norm_x = (detail_centre_x - off_x) / max(used_w, 1e-6)
        detail_norm_y = (detail_centre_y - off_y) / max(used_h, 1e-6)
        in_eye_band = 0.20 <= detail_norm_x <= 0.80 and 0.24 <= detail_norm_y <= 0.48
        detail_length = sum(
            math.hypot(bx - ax, by - ay)
            for (ax, ay), (bx, by) in zip(converted, converted[1:])
        )
        if in_eye_band and detail_width <= 20.0 and detail_height <= 12.0 and detail_length <= 30.0:
            local_spacing = min(local_spacing, 0.35)
        if is_closed and in_eye_band:
            perimeter = sum(
                math.hypot(bx - ax, by - ay)
                for (ax, ay), (bx, by) in zip(converted, converted[1:])
            )
            # Use a few more samples for the tiny circular eye contours so a
            # robot joining straight segments does not turn them into a
            # visibly angular polygon. This only affects small closed loops.
            local_spacing = min(spacing_mm, max(0.25, perimeter / 20.0))
        elif is_closed:
            perimeter = sum(
                math.hypot(bx - ax, by - ay)
                for (ax, ay), (bx, by) in zip(converted, converted[1:])
            )
            centre_y = (min(detail_ys) + max(detail_ys)) / 2.0
            norm_y = (centre_y - off_y) / max(used_h, 1e-6)
            # Thick, intersecting hair strokes can create small closed cycles
            # during raster skeletonization. The source line art has no
            # intentional loops in this upper hair band; discard only those
            # compact cycles so they cannot become artificial circles in the
            # robot trajectory. Closed eyes, earrings and other regions stay.
            if norm_y < 0.34 and perimeter < 18.0:
                continue
        if in_eye_band and detail_width <= 28.0 and detail_height <= 18.0 and detail_length <= 45.0:
            converted = smooth_eye_path(converted, is_closed)
        sampled = resample(converted, local_spacing)
        if len(sampled) >= 2:
            paths_mm.append(sampled)
    paths_mm.sort(key=lambda p: (min(y for _, y in p), min(x for x, _ in p)))
    return paths_mm, scale


def write_jaka_script(
    paths_mm,
    output: str | Path,
    *,
    canvas_width_mm: float = 152.4,
    canvas_height_mm: float = 152.4,
    spacing_mm: float = 1.0,
    robot_x: float = -6.771302,
    robot_y: float = -6.384003,
    touch_z: float = -9.0,
    pose_rx: float = 180.0,
    pose_ry: float = 0.0,
    pose_rz: float = 180.0,
    lift_dy: float = 0.0,
    lift_dz: float = 7.0,
    lift_drx: float = 0.0,
    draw_vel: float = 30.0,
    draw_acc: float = 90.0,
    travel_vel: float = 60.0,
    travel_acc: float = 180.0,
    tolerance: float = 1.0,
    tool_id: int = 4,
    user_frame_id: int = 6,
    mirror_x: bool = False,
    home: str = "[90, 0, -90, 0, -90, 0]",
):
    """Write paths using the JAKA ZU Script structure supplied by the user.

    ``mirror_x`` exists because a taught user frame may have its +X axis
    pointing to the physical left of the drawing. The image is then mapped
    with ``robot_x - x``, which reproduces the image on the paper exactly
    (a rigid frame cannot otherwise undo that flip).
    """
    out = Path(output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    point_paths = []
    point_no = 1
    for path in paths_mm:
        ids = list(range(point_no, point_no + len(path)))
        point_paths.append((ids, path))
        point_no += len(path)

    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# JAKA ZU Script\n\n")
        f.write("# 变量声明\n\n")
        f.write(f"Z = {touch_z:.6f}\t\t# 触纸高度\n\n")
        f.write(f"vel1 = {draw_vel:.6f}\t\t# 绘图速度\n")
        f.write(f"acc1 = {draw_acc:.6f}\t\t# 绘图加速度\n\n")
        f.write(f"vel2 = {travel_vel:.6f}\t\t# 抬笔移动速度\n")
        f.write(f"acc2 = {travel_acc:.6f}\t\t# 抬笔移动加速度\n\n")
        f.write(f"tol = {tolerance:.6f}\t\t# 转弯半径\n\n")
        f.write(f"tol_detail = {min(tolerance, 0.2):.6f}\t\t# 眼睛/五官小曲线转弯半径\n\n")
        f.write("# 平面变换，抬笔偏移\n")
        f.write(f"dy = {lift_dy:.6f}\n")
        f.write(f"dz = {lift_dz:.6f}\n")
        f.write(f"drx = {lift_drx:.6f}\n\n")
        f.write("# ====================== 元数据 ======================\n")
        f.write(f"# canvas_mm={canvas_width_mm:.3f}x{canvas_height_mm:.3f}\n")
        f.write(f"# spacing_mm={spacing_mm:.3f}; paths={len(paths_mm)}; points={point_no - 1}\n")
        f.write(f"# mirror_x={bool(mirror_x)}\n")
        f.write(f"# robot_canvas_origin_xy=[{robot_x:.6f}, {robot_y:.6f}]\n\n")
        f.write("# ====================== 点位 ======================\n")
        f.write(f"Home = {home}\n\n")
        for path_index, (ids, path) in enumerate(point_paths, 1):
            f.write(f"# 第 {path_index} 条线\n")
            for point_id, (x, y) in zip(ids, path):
                robot_point_x = robot_x - x if mirror_x else robot_x + x
                robot_point_y = robot_y + y
                f.write(
                    f"P{point_id} = [{robot_point_x:.6f}, {robot_point_y:.6f}, Z, "
                    f"{pose_rx:.6f}, {pose_ry:.6f}, {pose_rz:.6f}]\n"
                )
            f.write("\n")

        f.write("# ====================== 轨迹 ======================\n\n")
        f.write(f"set_tool_id({tool_id})\n")
        f.write(f"set_user_frame_id({user_frame_id})\n\n")
        f.write("# 关节运动到原点\n")
        f.write("movj(Home, 0, vel2, acc2, 0)\n\n")
        for path_index, (ids, _path) in enumerate(point_paths, 1):
            first_id, last_id = ids[0], ids[-1]
            xs = [point[0] for point in _path]
            ys = [point[1] for point in _path]
            path_length = sum(math.dist(a, b) for a, b in zip(_path, _path[1:]))
            centre_x = (min(xs) + max(xs)) / 2.0
            centre_y = (min(ys) + max(ys)) / 2.0
            in_eye_band = (
                0.20 <= centre_x / max(canvas_width_mm, 1e-6) <= 0.80
                and 0.24 <= centre_y / max(canvas_height_mm, 1e-6) <= 0.48
            )
            is_detail = (
                in_eye_band
                and max(xs) - min(xs) <= 20.0
                and max(ys) - min(ys) <= 12.0
                and path_length <= 30.0
            )
            blend = "tol_detail" if is_detail else "tol"
            f.write(f"# 第 {path_index} 条线：落笔并绘制\n")
            f.write(f"P0 = yz_plane_trans(P{first_id}, dy, dz, drx)  # 起点上方\n")
            f.write("movl(P0, 0, vel2, acc2, 0)\n")
            f.write(f"movl(P{first_id}, 0, vel1, acc1, 0)  # 落笔\n")
            for index, point_id in enumerate(ids[1:], 1):
                corner = "0" if index == len(ids) - 1 else blend
                f.write(f"movl(P{point_id}, 0, vel1, acc1, {corner})\n")
            f.write(f"P0 = yz_plane_trans(P{last_id}, dy, dz, drx)  # 抬笔\n")
            f.write("movl(P0, 0, vel2, acc2, 0)\n\n")
        f.write("# 关节运动到原点\n")
        f.write("movj(Home, 0, vel2, acc2, 0)\n")
    return out, point_no - 1


def convert_to_jaka(
    image: str | Path,
    output: str | Path,
    **kwargs,
):
    path_keys = {"width_mm", "height_mm", "margin_mm", "spacing_mm", "threshold", "min_pixels", "min_stroke_mm", "stitch_gap_px", "continuous_components", "origin"}
    path_args = {key: value for key, value in kwargs.items() if key in path_keys}
    script_args = {key: value for key, value in kwargs.items() if key not in path_keys}
    paths_mm, scale = image_to_paths(image, **path_args)
    out, point_count = write_jaka_script(
        paths_mm,
        output,
        canvas_width_mm=path_args.get("width_mm", 152.4),
        canvas_height_mm=path_args.get("height_mm", 152.4),
        spacing_mm=path_args.get("spacing_mm", 1.0),
        **script_args,
    )
    return out, len(paths_mm), point_count, scale


def main():
    ap = argparse.ArgumentParser(description="PNG line art to JAKA ZU Script")
    ap.add_argument("image")
    ap.add_argument("--output", default=None)
    ap.add_argument("--width-mm", type=float, default=152.4)
    ap.add_argument("--height-mm", type=float, default=152.4)
    ap.add_argument("--margin-mm", type=float, default=5.0)
    ap.add_argument("--spacing-mm", type=float, default=1.0)
    ap.add_argument("--threshold", type=int, default=180)
    ap.add_argument("--min-pixels", type=int, default=8)
    ap.add_argument("--min-stroke-mm", type=float, default=0.0)
    ap.add_argument("--stitch-gap-px", type=float, default=2.0)
    ap.add_argument("--origin", choices=("top-left", "bottom-left"), default="top-left")
    ap.add_argument("--robot-x", type=float, default=-6.771302)
    ap.add_argument("--robot-y", type=float, default=-6.384003)
    ap.add_argument("--touch-z", type=float, default=-9.0)
    ap.add_argument("--lift-dz", type=float, default=7.0)
    ap.add_argument("--rx", type=float, default=180.0)
    ap.add_argument("--ry", type=float, default=0.0)
    ap.add_argument("--rz", type=float, default=180.0)
    ap.add_argument("--tool-id", type=int, default=4)
    ap.add_argument("--user-frame-id", type=int, default=6)
    ap.add_argument("--mirror-x", action="store_true", help="图像左右镜像（坐标系 X 方向与图像相反时使用）")
    args = ap.parse_args()

    src = Path(args.image).expanduser().resolve()
    out = Path(args.output or (src.parent / f"{src.stem}_jaka.txt"))
    out, path_count, point_count, scale = convert_to_jaka(
        src, out,
        width_mm=args.width_mm,
        height_mm=args.height_mm,
        margin_mm=args.margin_mm,
        spacing_mm=args.spacing_mm,
        threshold=args.threshold,
        min_pixels=args.min_pixels,
        min_stroke_mm=args.min_stroke_mm,
        origin=args.origin,
        robot_x=args.robot_x,
        robot_y=args.robot_y,
        touch_z=args.touch_z,
        lift_dz=args.lift_dz,
        pose_rx=args.rx,
        pose_ry=args.ry,
        pose_rz=args.rz,
        tool_id=args.tool_id,
        user_frame_id=args.user_frame_id,
        mirror_x=args.mirror_x,
    )
    print(out)
    print(f"paths={path_count} points={point_count} scale={scale:.5f}mm/px")


if __name__ == "__main__":
    main()
