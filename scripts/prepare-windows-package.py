"""Create build metadata, version resources and installed-runtime notices."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def runtime_distributions() -> list[metadata.Distribution]:
    pending = ["face-swap-studio"]
    found: dict[str, metadata.Distribution] = {}
    while pending:
        name = canonicalize_name(pending.pop())
        if name in found:
            continue
        dist = metadata.distribution(name)
        found[name] = dist
        for raw in dist.requires or []:
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return [found[name] for name in sorted(found)]


def prepare(output: Path) -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = config["project"]["version"]
    if metadata.version("face-swap-studio") != version:
        raise RuntimeError("Installed version does not match pyproject.toml; run uv sync again.")
    output.mkdir(parents=True, exist_ok=True)
    parsed = Version(version)
    release = tuple((list(parsed.release) + [0, 0, 0])[:3])
    file_version = (*release, parsed.pre[1] if parsed.pre else 0)
    resource = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={file_version!r}, prodvers={file_version!r},
    mask=0x3f, flags={2 if parsed.is_prerelease else 0}, OS=0x40004,
    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'FaceSwap Studio'),
    StringStruct('FileDescription', 'FaceSwap Studio'),
    StringStruct('FileVersion', {version!r}),
    StringStruct('InternalName', 'FaceSwapStudio'),
    StringStruct('OriginalFilename', 'FaceSwapStudio.exe'),
    StringStruct('ProductName', 'FaceSwap Studio'),
    StringStruct('ProductVersion', {version!r})
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"""
    (output / "version_info.txt").write_text(resource, encoding="utf-8")
    notices = output / "THIRD-PARTY-NOTICES"
    if notices.exists():
        shutil.rmtree(notices)
    notices.mkdir()
    manifest = []
    for dist in runtime_distributions():
        name = dist.metadata["Name"]
        entry = {
            "name": name,
            "version": dist.version,
            "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", ""),
            "project_urls": dist.metadata.get_all("Project-URL") or [],
            "notice_files": [],
        }
        if canonicalize_name(name) != "face-swap-studio":
            for relative in dist.files or []:
                parts = [part.lower() for part in relative.parts]
                filename = relative.name.lower()
                if not (
                    "licenses" in parts
                    or filename.startswith(("license", "licence", "copying", "notice", "copyright"))
                ):
                    continue
                source = Path(dist.locate_file(relative))
                if not source.is_file():
                    continue
                # Preserve meaningful paths while preventing metadata paths
                # containing '..' from escaping the generated notice directory.
                safe_parts = [part for part in relative.parts if part not in (".", "..")]
                target = notices / canonicalize_name(name) / Path(*safe_parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                entry["notice_files"].append(target.relative_to(notices).as_posix())
        manifest.append(entry)
    for candidate in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
        if candidate.is_file():
            shutil.copy2(candidate, notices / "PYTHON-LICENSE.txt")
            break
    (notices / "runtime-components.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (notices / "README.txt").write_text(
        "These are installed runtime dependency notices collected from package metadata.\n"
        "This inventory is not a complete legal assessment or a model license.\n"
        "No third-party face engine or face model is included in this build.\n"
        "Qt/PySide6 runtime libraries remain separate DLLs in _internal.\n"
        "Before public distribution, review each dependency's redistribution obligations.\n",
        encoding="utf-8",
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.strip()
    info = {
        "product": "FaceSwap Studio",
        "version": version,
        "git_revision": revision,
        "built_at_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pyinstaller": metadata.version("pyinstaller"),
        "runtime_components": [{"name": x["name"], "version": x["version"]} for x in manifest],
        "bundled_face_engines": [],
        "bundled_face_models": [],
        "validation_scope": "Windows package and GUI startup; no GPU quality or call compatibility claim",
    }
    (output / "build-info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "version.txt").write_text(version, encoding="utf-8")
    activation = {
        "activation_url": os.environ.get("FSS_ACTIVATION_URL", "").strip().rstrip("/"),
        "license_public_key": os.environ.get("FSS_LICENSE_PUBLIC_KEY", "").strip(),
    }
    (output / "activation.json").write_text(
        json.dumps(activation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "packaging")
    prepare(parser.parse_args().output.resolve())
