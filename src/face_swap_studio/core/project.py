"""Project management — local folder + metadata JSON."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AuthorizedAsset:
    """An authorized face asset imported into a project."""

    path: str
    label: str
    consent_confirmed: bool = False
    notes: str = ""
    imported_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ProjectMeta:
    """Persisted project metadata."""

    name: str
    created_at: str
    assets: list[dict[str, Any]] = field(default_factory=list)
    consent_checklist_acked: bool = False
    watermark_enabled: bool = True
    notes: str = ""


class ProjectStore:
    """Create / open / save projects under a root directory."""

    META_FILENAME = "project.json"

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[str]:
        names: list[str] = []
        if not self.root.exists():
            return names
        for p in sorted(self.root.iterdir()):
            if p.is_dir() and (p / self.META_FILENAME).exists():
                names.append(p.name)
        return names

    def project_dir(self, name: str) -> Path:
        return self.root / name

    def create(self, name: str, notes: str = "") -> ProjectMeta:
        safe = _safe_name(name)
        d = self.project_dir(safe)
        if d.exists():
            raise FileExistsError(f"项目已存在: {safe}")
        d.mkdir(parents=True)
        (d / "assets").mkdir()
        (d / "exports").mkdir()
        meta = ProjectMeta(
            name=safe,
            created_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
            watermark_enabled=True,
        )
        self.save(meta)
        return meta

    def load(self, name: str) -> ProjectMeta:
        path = self.project_dir(name) / self.META_FILENAME
        data = json.loads(path.read_text(encoding="utf-8"))
        return ProjectMeta(
            name=data["name"],
            created_at=data["created_at"],
            assets=data.get("assets", []),
            consent_checklist_acked=data.get("consent_checklist_acked", False),
            watermark_enabled=data.get("watermark_enabled", True),
            notes=data.get("notes", ""),
        )

    def save(self, meta: ProjectMeta) -> None:
        d = self.project_dir(meta.name)
        d.mkdir(parents=True, exist_ok=True)
        path = d / self.META_FILENAME
        path.write_text(
            json.dumps(asdict(meta), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_asset(
        self,
        meta: ProjectMeta,
        source: Path | str,
        label: str,
        consent_confirmed: bool,
        notes: str = "",
    ) -> ProjectMeta:
        """Copy asset into project assets/ and record metadata."""
        import shutil

        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(str(source))
        dest_dir = self.project_dir(meta.name) / "assets"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source.name
        if dest.exists():
            stem, suffix = source.stem, source.suffix
            dest = dest_dir / f"{stem}_{datetime.now(timezone.utc).strftime('%H%M%S')}{suffix}"
        shutil.copy2(source, dest)
        asset = AuthorizedAsset(
            path=str(dest.relative_to(self.project_dir(meta.name))),
            label=label or source.stem,
            consent_confirmed=consent_confirmed,
            notes=notes,
        )
        meta.assets.append(asdict(asset))
        self.save(meta)
        return meta


def _safe_name(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name.strip())
    cleaned = cleaned.strip().replace(" ", "_")
    if not cleaned:
        raise ValueError("项目名称无效")
    return cleaned
