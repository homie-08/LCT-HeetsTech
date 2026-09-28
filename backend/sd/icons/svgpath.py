"""Контуры SVG → отрезки и кубические кривые.

DrawingML умеет `moveTo`, `lnTo`, `cubicBezTo` и `close`; всё остальное из
SVG — квадратичные кривые, дуги, круги и скруглённые прямоугольники —
переводится в эти четыре команды. Дуга разбивается на четверти и каждая
приближается кубической кривой: погрешность меньше толщины обводки.
"""

from __future__ import annotations

import math
import re

from lxml import etree

Point = tuple[float, float]
# Команда контура: ("M", x, y) · ("L", x, y) · ("C", x1, y1, x2, y2, x, y) · ("Z",)
Command = tuple

_TOKEN_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
# Коэффициент кубической кривой, приближающей четверть окружности.
KAPPA = 0.5522847498


def parse_svg(markup: str) -> list[list[Command]]:
    """Все контуры из фрагмента SVG — path, circle, ellipse, rect, line, polyline."""
    root = etree.fromstring(f"<g>{markup}</g>")
    paths: list[list[Command]] = []
    for element in root.iter():
        tag = etree.QName(element).localname
        if tag == "path":
            paths.extend(parse_path(element.get("d", "")))
        elif tag in ("circle", "ellipse"):
            cx, cy = float(element.get("cx", 0)), float(element.get("cy", 0))
            rx = float(element.get("rx", element.get("r", 0)))
            ry = float(element.get("ry", element.get("r", 0)))
            paths.append(ellipse(cx, cy, rx, ry))
        elif tag == "rect":
            x, y = float(element.get("x", 0)), float(element.get("y", 0))
            w, h = float(element.get("width", 0)), float(element.get("height", 0))
            rx = float(element.get("rx", element.get("ry", 0)))
            paths.append(rounded_rect(x, y, w, h, rx))
        elif tag == "line":
            paths.append([("M", float(element.get("x1", 0)), float(element.get("y1", 0))),
                          ("L", float(element.get("x2", 0)), float(element.get("y2", 0)))])
        elif tag in ("polyline", "polygon"):
            numbers = [float(v) for v in re.findall(r"[-+]?\d*\.?\d+", element.get("points", ""))]
            points = list(zip(numbers[::2], numbers[1::2]))
            if points:
                path: list[Command] = [("M", *points[0])]
                path.extend(("L", x, y) for x, y in points[1:])
                if tag == "polygon":
                    path.append(("Z",))
                paths.append(path)
    return paths


def ellipse(cx: float, cy: float, rx: float, ry: float) -> list[Command]:
    kx, ky = rx * KAPPA, ry * KAPPA
    return [
        ("M", cx + rx, cy),
        ("C", cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry),
        ("C", cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy),
        ("C", cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry),
        ("C", cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy),
        ("Z",),
    ]


def rounded_rect(x: float, y: float, w: float, h: float, r: float) -> list[Command]:
    r = max(0.0, min(r, w / 2, h / 2))
    if r == 0:
        return [("M", x, y), ("L", x + w, y), ("L", x + w, y + h), ("L", x, y + h), ("Z",)]
    k = r * KAPPA
    return [
        ("M", x + r, y),
        ("L", x + w - r, y),
        ("C", x + w - r + k, y, x + w, y + r - k, x + w, y + r),
        ("L", x + w, y + h - r),
        ("C", x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h),
        ("L", x + r, y + h),
        ("C", x + r - k, y + h, x, y + h - r + k, x, y + h - r),
        ("L", x, y + r),
        ("C", x, y + r - k, x + r - k, y, x + r, y),
        ("Z",),
    ]


def parse_path(d: str) -> list[list[Command]]:
    """Атрибут `d` → список контуров из абсолютных M/L/C/Z."""
    tokens = _TOKEN_RE.findall(d)
    paths: list[list[Command]] = []
    current: list[Command] = []
    x = y = 0.0                   # текущая точка
    sx = sy = 0.0                 # начало контура
    cx2 = cy2 = None              # вторая контрольная точка последней C/S
    qx = qy = None                # контрольная точка последней Q/T
    command = ""
    index = 0

    def number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def start(px: float, py: float) -> None:
        nonlocal current, sx, sy
        if current:
            paths.append(current)
        current = [("M", px, py)]
        sx, sy = px, py

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
            if command in "Zz":
                if current:
                    current.append(("Z",))
                    paths.append(current)
                    current = []
                x, y = sx, sy
                cx2 = cy2 = qx = qy = None
                continue
        if not command:
            raise ValueError(f"контур без команды: {d!r}")
        relative = command.islower()
        letter = command.upper()

        if letter == "M":
            px, py = number(), number()
            if relative:
                px, py = x + px, y + py
            start(px, py)
            x, y = px, py
            # Дальнейшие пары после M — это L.
            command = "l" if relative else "L"
            cx2 = cy2 = qx = qy = None
            continue
        if letter == "L":
            px, py = number(), number()
            if relative:
                px, py = x + px, y + py
            current.append(("L", px, py))
            x, y = px, py
        elif letter == "H":
            px = number()
            px = x + px if relative else px
            current.append(("L", px, y))
            x = px
        elif letter == "V":
            py = number()
            py = y + py if relative else py
            current.append(("L", x, py))
            y = py
        elif letter in ("C", "S"):
            if letter == "C":
                x1, y1 = number(), number()
                if relative:
                    x1, y1 = x + x1, y + y1
            else:
                # Гладкое продолжение: первая контрольная — отражение второй.
                x1, y1 = (2 * x - cx2, 2 * y - cy2) if cx2 is not None else (x, y)
            x2, y2 = number(), number()
            px, py = number(), number()
            if relative:
                x2, y2, px, py = x + x2, y + y2, x + px, y + py
            current.append(("C", x1, y1, x2, y2, px, py))
            cx2, cy2 = x2, y2
            x, y = px, py
            qx = qy = None
            continue
        elif letter in ("Q", "T"):
            if letter == "Q":
                x1, y1 = number(), number()
                if relative:
                    x1, y1 = x + x1, y + y1
            else:
                x1, y1 = (2 * x - qx, 2 * y - qy) if qx is not None else (x, y)
            px, py = number(), number()
            if relative:
                px, py = x + px, y + py
            # Квадратичная кривая как кубическая — точно, без приближения.
            current.append(("C", x + 2 / 3 * (x1 - x), y + 2 / 3 * (y1 - y),
                            px + 2 / 3 * (x1 - px), py + 2 / 3 * (y1 - py), px, py))
            qx, qy = x1, y1
            x, y = px, py
            cx2 = cy2 = None
            continue
        elif letter == "A":
            rx, ry = number(), number()
            rotation = number()
            large, sweep = int(number()), int(number())
            px, py = number(), number()
            if relative:
                px, py = x + px, y + py
            current.extend(arc_to_cubics(x, y, rx, ry, rotation, large, sweep, px, py))
            x, y = px, py
        else:
            raise ValueError(f"неизвестная команда {command!r}")
        cx2 = cy2 = qx = qy = None

    if current:
        paths.append(current)
    return paths


def arc_to_cubics(x1: float, y1: float, rx: float, ry: float, rotation: float,
                  large: int, sweep: int, x2: float, y2: float) -> list[Command]:
    """Дуга SVG → кубические кривые (SVG 1.1, приложение F.6.5)."""
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [("L", x2, y2)]
    phi = math.radians(rotation)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    # Радиусы могут быть малы для такой хорды — тогда их растягивают.
    scale = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    numerator = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    denominator = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    coefficient = math.sqrt(max(0.0, numerator / denominator)) if denominator else 0.0
    if large == sweep:
        coefficient = -coefficient
    cxp = coefficient * rx * y1p / ry
    cyp = -coefficient * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        length = math.hypot(ux, uy) * math.hypot(vx, vy)
        value = math.acos(max(-1.0, min(1.0, dot / length)))
        return -value if ux * vy - uy * vx < 0 else value

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    segments = max(1, math.ceil(abs(delta) / (math.pi / 2)))
    step = delta / segments
    commands: list[Command] = []
    theta = theta1
    for _ in range(segments):
        alpha = 4 / 3 * math.tan(step / 4)
        cos1, sin1 = math.cos(theta), math.sin(theta)
        cos2, sin2 = math.cos(theta + step), math.sin(theta + step)

        def point(ex: float, ey: float) -> Point:
            return (cos_phi * rx * ex - sin_phi * ry * ey + cx,
                    sin_phi * rx * ex + cos_phi * ry * ey + cy)

        p1 = point(cos1 - alpha * sin1, sin1 + alpha * cos1)
        p2 = point(cos2 + alpha * sin2, sin2 - alpha * cos2)
        end = point(cos2, sin2)
        commands.append(("C", *p1, *p2, *end))
        theta += step
    # Последняя точка — ровно конец дуги, без накопленной погрешности.
    last = commands[-1]
    commands[-1] = ("C", last[1], last[2], last[3], last[4], x2, y2)
    return commands


def bounds(paths: list[list[Command]]) -> tuple[float, float, float, float]:
    """Габариты по опорным и контрольным точкам: (x0, y0, x1, y1)."""
    xs: list[float] = []
    ys: list[float] = []
    for path in paths:
        for command in path:
            xs.extend(command[1::2])
            ys.extend(command[2::2])
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))
