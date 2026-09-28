"""Перекодирование записи прогона в .mp4 — чтобы открывалась чем угодно.

Playwright пишет .webm; проигрыватель Windows по умолчанию его не знает, а
жюри лучше не искать плеер. Перекладываем кадр в кадр (кодек mp4v из OpenCV,
ffmpeg отдельно не нужен): ни обрезки, ни ускорения — та же запись, другой
контейнер.

    python scripts/webm_to_mp4.py data/out/demo/page@....webm --out "Демо.mp4"
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

import cv2


def convert(source: pathlib.Path, target: pathlib.Path) -> tuple[int, float]:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise SystemExit(f"не открылось: {source}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), fps,
                             (width, height))
    if not writer.isOpened():
        raise SystemExit("OpenCV не смог создать mp4")

    frames = 0
    started = time.monotonic()
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        writer.write(frame)
        frames += 1
        if frames % 500 == 0:
            print(f"  {frames} кадров…", flush=True)
    capture.release()
    writer.release()
    return frames, frames / fps if fps else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="исходный .webm")
    parser.add_argument("--out", required=True, help="куда положить .mp4")
    args = parser.parse_args()

    source = pathlib.Path(args.source)
    target = pathlib.Path(args.out)
    frames, seconds = convert(source, target)
    size = target.stat().st_size / 1e6
    print(f"готово: {target} — {frames} кадров, {int(seconds // 60)}:{int(seconds % 60):02d}, "
          f"{size:.0f} МБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
