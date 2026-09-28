"""Хранилище задач сервиса.

Разбор шаблона и сборка презентации занимают десятки секунд (рендер!), поэтому
HTTP-ручки только ставят задачу и отдают идентификатор, а состояние живёт здесь.
Для демонстрации этого достаточно: один процесс, файлы на диске, индекс в памяти.
Если понадобится масштабирование, менять придётся только этот модуль.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

# Тесты обязаны работать в своей песочнице: store.clear() сносит ROOT целиком,
# и без изоляции каждый прогон тестов удалял бы собранные проекты пользователя.
ROOT = Path(os.environ.get("SD_DATA_DIR")
            or Path(__file__).resolve().parents[3] / "data" / "api")

Status = Literal["queued", "running", "ready", "failed"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    kind: Literal["template", "deck"]
    status: Status = "queued"
    stage: str = "в очереди"
    error: str = ""
    created_at: str = field(default_factory=_now)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return ROOT / f"{self.kind}s" / self.id

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "status": self.status,
                "stage": self.stage, "error": self.error,
                "created_at": self.created_at, **self.data}


class Store:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, kind: Literal["template", "deck"]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind)
        job.dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job
        # Индекс живёт в памяти, а файлы — на диске. После перезапуска сервиса
        # ссылки «Поделиться» и скачивания обязаны работать: задача поднимается
        # из своей папки.
        return self._restore(job_id)

    def _restore(self, job_id: str) -> Job | None:
        safe = Path(job_id).name
        for kind in ("template", "deck"):
            folder = ROOT / f"{kind}s" / safe
            if not folder.exists():
                continue
            state = folder / "state.json"
            if state.exists():
                try:
                    payload = json.loads(state.read_text(encoding="utf-8"))
                    job = Job(id=safe, kind=kind,  # type: ignore[arg-type]
                              status=payload.get("status", "ready"),
                              stage=payload.get("stage", ""),
                              error=payload.get("error", ""),
                              created_at=payload.get("created_at", _now()))
                    job.data = {key: value for key, value in payload.items()
                                if key not in ("id", "kind", "status", "stage",
                                               "error", "created_at")}
                except (json.JSONDecodeError, OSError):
                    job = Job(id=safe, kind=kind, status="ready",  # type: ignore[arg-type]
                              stage="восстановлено после перезапуска")
            else:
                # Задача из версии без state.json: файлы есть, подробностей нет.
                job = Job(id=safe, kind=kind, status="ready",  # type: ignore[arg-type]
                          stage="восстановлено после перезапуска")
            with self._lock:
                self._jobs.setdefault(safe, job)
            return job
        return None

    def list(self, kind: str) -> list[Job]:
        with self._lock:
            jobs = [job for job in self._jobs.values() if job.kind == kind]
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for name, value in fields.items():
                if name in ("status", "stage", "error"):
                    setattr(job, name, value)
                else:
                    job.data[name] = value
            snapshot = job.to_json()
        try:
            (job.dir / "state.json").write_text(
                json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass                                   # диск подвёл — индекс в памяти жив

    def fail(self, job_id: str, error: str) -> None:
        self.update(job_id, status="failed", stage="ошибка", error=error)

    def remove(self, job_id: str, kind: str) -> bool:
        """Удаляет задачу вместе с файлами. True — если было что удалять."""
        safe = Path(job_id).name
        with self._lock:
            self._jobs.pop(safe, None)
        folder = ROOT / f"{kind}s" / safe
        if not folder.exists():
            return False
        shutil.rmtree(folder, ignore_errors=True)
        return True

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()
        if ROOT.exists():
            shutil.rmtree(ROOT, ignore_errors=True)


store = Store()
