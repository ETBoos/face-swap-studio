"""Launch upstream Deep-Live-Cam's GUI with a source face already selected.

This file is executed with Deep-Live-Cam's own Python (its venv), not the
FaceSwap Studio interpreter. It must stay stdlib-only.

Deep-Live-Cam treats ``-s/--source`` as headless batch mode and skips the
window that owns the Live webcam button (``modules.globals.headless``).
Live mode therefore starts ``run.py`` with no source/target/output args,
then pins ``modules.globals.source_path`` after ``parse_args()``.

No face-swap code lives here. ``run.py`` still performs CUDA DLL setup and
``modules.core`` still runs the upstream pipeline.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def build_child_argv(
    run_py: Path,
    *,
    provider: str,
    live_mirror: bool = False,
    lang: str = "en",
) -> list[str]:
    """Argv for upstream ``run.py``. Must not include source/target/output."""
    argv = [
        str(run_py),
        "--execution-provider",
        provider,
        "-l",
        lang or "en",
    ]
    if live_mirror:
        argv.append("--live-mirror")
    return argv


def apply_source_pin(globals_mod: ModuleType, source: str) -> None:
    globals_mod.source_path = source
    globals_mod.headless = False


class _PinCoreLoader:
    def __init__(self, inner: object, source: str) -> None:
        self._inner = inner
        self._source = source

    def create_module(self, spec: object) -> object:
        create = getattr(self._inner, "create_module", None)
        if create is None:
            return None
        return create(spec)

    def exec_module(self, module: ModuleType) -> None:
        exec_module = getattr(self._inner, "exec_module")
        exec_module(module)
        real_parse = module.parse_args
        source = self._source

        def parse_args() -> None:
            real_parse()
            import modules.globals as globals_mod

            apply_source_pin(globals_mod, source)

        module.parse_args = parse_args  # type: ignore[method-assign]


class _PinCoreFinder:
    """After ``modules.core`` loads, wrap ``parse_args`` to keep the GUI."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._busy = False

    def find_spec(self, fullname: str, path: object = None, target: object = None) -> object:
        if fullname != "modules.core" or self._busy:
            return None
        self._busy = True
        try:
            sys.meta_path.remove(self)
            spec = importlib.util.find_spec(fullname)
        finally:
            self._busy = False
        if spec is None or spec.loader is None:
            sys.meta_path.insert(0, self)
            return None
        spec.loader = _PinCoreLoader(spec.loader, self._source)  # type: ignore[assignment]
        return spec


def install_core_source_pin(source: str) -> _PinCoreFinder:
    finder = _PinCoreFinder(source)
    sys.meta_path.insert(0, finder)
    return finder


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Open Deep-Live-Cam Live UI with a source face")
    parser.add_argument("--dlc-root", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--execution-provider", default="cuda")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--live-mirror", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.dlc_root).expanduser().resolve()
    run_py = root / "run.py"
    source = str(Path(args.source).expanduser().resolve())
    if not run_py.is_file():
        raise SystemExit(f"Deep-Live-Cam run.py not found: {run_py}")
    if not Path(source).is_file():
        raise SystemExit(f"source face image not found: {source}")

    import os

    os.chdir(root)
    sys.path.insert(0, str(root))
    install_core_source_pin(source)
    sys.argv = build_child_argv(
        run_py,
        provider=str(args.execution_provider),
        live_mirror=bool(args.live_mirror),
        lang=str(args.lang),
    )

    import runpy

    runpy.run_path(str(run_py), run_name="__main__")


if __name__ == "__main__":
    main()
