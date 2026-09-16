"""Contract/lifecycle tests, including the actual worker in a subprocess.

The tiny fake FaceFusion package emulates its audited API, not its neural model.
These tests do NOT establish real face quality, camera compatibility or GPU FPS.
"""
from __future__ import annotations

import io
import json
import os
import struct
import sys
import time
import zlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from face_swap_studio.engines.base import EngineConfig, EngineStatus
from face_swap_studio.engines.facefusion import (
    FaceFusionEngine,
    read_facefusion_version,
    resolve_facefusion_python,
    resolve_facefusion_root,
)
from face_swap_studio.engines.facefusion_protocol import (
    MAX_HEADER_BYTES,
    ProtocolError,
    read_message,
    write_message,
)
from face_swap_studio.engines.facefusion_worker import validate_local_sources


def eventually(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for worker")


@pytest.fixture
def install(tmp_path):
    root = tmp_path / "FaceFusion 中文 space"
    root.mkdir()

    def put(name, content):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    put("facefusion.py", "# Test install only\n")
    put("facefusion/metadata.py", "METADATA = {'version': '3.9.0'}\ndef get(key): return METADATA.get(key)\n")
    put("onnxruntime.py", "def get_available_providers(): return ['CPUExecutionProvider']\n")
    put("facefusion/__init__.py", '''
import cv2, numpy as np, time
from pathlib import Path
ROOT = Path(__file__).parent.parent
class Camera:
    def __init__(self, index):
        self.index = index
        self.count = 0
    def isOpened(self): return self.index != 99
    def set(self, *_): return True
    def read(self):
        time.sleep(0.015)
        self.count += 1
        if (ROOT / 'disconnect').exists(): return False, None
        return True, np.full((120,160,3), 40, dtype=np.uint8)
    def release(self): (ROOT / 'released').touch()
cv2.VideoCapture = Camera
''')
    put("facefusion/state_manager.py", "STATE={}\ndef init_item(k,v): STATE[k]=v\n")
    put("facefusion/download.py", '''
def conditional_download_hashes(*a): raise AssertionError('network download called')
def conditional_download_sources(*a): raise AssertionError('network download called')
''')
    put("facefusion/content_analyser.py", '''
from pathlib import Path
ROOT = Path(__file__).parent.parent
def analyse_frame(image): return (ROOT/'blocked').exists()
class Session:
    def get_providers(self): return ['CPUExecutionProvider']
def get_inference_pool(): return {'fake': Session()}
''')
    put("facefusion/face_creator.py", '''
from pathlib import Path
ROOT=Path(__file__).parent.parent
def get_many_faces(frames):
    if frames[0].shape[0] > 100:
        if (ROOT/'no_face').exists(): return []
        if (ROOT/'multiple_faces').exists(): return [object(),object()]
    return [object()]
def average_face_identity(faces): return faces[0] if faces else None
''')
    put("facefusion/vision.py", "import cv2\ndef read_static_images(paths): return [cv2.imread(p) for p in paths]\n")
    for name in ("facefusion/processors/__init__.py", "facefusion/processors/modules/__init__.py",
                 "facefusion/processors/modules/face_swapper/__init__.py"):
        put(name, "")
    put("facefusion/processors/modules/face_swapper/core.py", '''
from pathlib import Path
from facefusion import content_analyser, download
ROOT = Path(__file__).parents[4]
def pre_check():
    download.conditional_download_hashes({'m':{'path':str(ROOT/'model.hash')}})
    return download.conditional_download_sources({'m':{'path':str(ROOT/'model.onnx')}})
def get_common_modules(): return [content_analyser]
def get_inference_pool(): return content_analyser.get_inference_pool()
def swap_face(source, target, source_image, frame):
    if (ROOT/'crash').exists(): raise RuntimeError('simulated inference failure')
    if (ROOT/'unchanged').exists(): return frame
    frame[:,:,:] = 140
    return frame
''')
    (root / "model.onnx").write_bytes(b"synthetic test model, not neural weights")
    checksum = zlib.crc32((root / "model.onnx").read_bytes())
    (root / "model.hash").write_text(f"{checksum:08x}")
    source = root / "source.png"
    assert cv2.imwrite(str(source), np.full((32, 32, 3), 200, dtype=np.uint8))
    cfg = EngineConfig(width=160, height=120, gpu_device="cpu", source_face_paths=[str(source)],
                       extra={"facefusion_root": str(root), "facefusion_python": sys.executable,
                              "facefusion_execution_provider": "cpu"})
    return root, cfg


@pytest.fixture
def engine():
    instance = FaceFusionEngine()
    yield instance
    instance.shutdown()


def test_protocol_roundtrip_and_clean_eof():
    buffer = io.BytesIO()
    write_message(buffer, {"type": "ready", "engine_version": "3.9.0"})
    write_message(buffer, {"type": "frame", "width": 2, "height": 1, "format": "bgr24",
                           "meta": {"frame_id": 1}}, b"123456")
    buffer.seek(0)
    assert read_message(buffer)[0]["type"] == "ready"
    assert read_message(buffer)[1] == b"123456"
    assert read_message(buffer) is None


@pytest.mark.parametrize("data", [b"\x00", struct.pack("!I", MAX_HEADER_BYTES + 1),
                                     struct.pack("!I", 2) + b"{!", struct.pack("!I", 2) + b"[]"])
def test_protocol_rejects_corrupt_or_oversized_messages(data):
    with pytest.raises(ProtocolError):
        read_message(io.BytesIO(data))


def test_protocol_rejects_oversized_payload_before_reading():
    header = {"protocol": 1, "type": "frame", "payload_size": 2**40,
              "width": 160, "height": 120, "format": "bgr24", "meta": {}}
    data = json.dumps(header).encode()
    with pytest.raises(ProtocolError):
        read_message(io.BytesIO(struct.pack("!I", len(data)) + data))


def test_metadata_is_parsed_without_executing(install):
    root, _ = install
    marker = root / "executed"
    with (root / "facefusion/metadata.py").open("a") as stream:
        stream.write(f"\nopen({str(marker)!r}, 'w').write('bad')\n")
    assert read_facefusion_version(root) == "3.9.0"
    assert not marker.exists()


def test_explicit_invalid_paths_never_fallback(install, monkeypatch):
    root, _ = install
    monkeypatch.setenv("FACEFUSION_ROOT", str(root))
    monkeypatch.setenv("FACEFUSION_PYTHON", sys.executable)
    assert resolve_facefusion_root(root / "missing") is None
    assert resolve_facefusion_python(root, root / "missing-python") is None


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks may require Windows privileges")
def test_python_detection_preserves_virtualenv_symlink(install):
    root, _ = install
    python = root / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    assert resolve_facefusion_python(root, python) == python


def test_initialize_rejects_missing_install_and_does_not_start(engine, install):
    root, cfg = install
    cfg.extra["facefusion_root"] = str(root / "missing")
    with pytest.raises(RuntimeError, match="找不到 FaceFusion"):
        engine.initialize(cfg)
    assert engine.status() == EngineStatus.ERROR
    assert engine._proc is None
    with pytest.raises(RuntimeError):
        engine.start()


def test_unsupported_version_rejected(engine, install):
    root, cfg = install
    (root / "facefusion/metadata.py").write_text("METADATA={'version':'3.8.3'}")
    with pytest.raises(RuntimeError, match="3.8.3"):
        engine.initialize(cfg)


def test_real_worker_protocol_first_frame_and_latest_slot(engine, install):
    _, cfg = install
    engine.initialize(cfg)
    assert engine.status() == EngineStatus.READY
    assert engine.read_frame() is None
    start = time.monotonic()
    engine.start()
    assert time.monotonic() - start < 0.3
    assert engine.status() == EngineStatus.STARTING
    eventually(lambda: engine.status() == EngineStatus.RUNNING)
    first = engine.read_frame()
    assert first.meta["face_swapped"] is True
    assert first.meta["safe_to_output"] is True
    assert first.meta["stub"] is False
    assert first.meta["processing_ms"] >= 0
    assert first.meta["captured_at_ns"] <= first.meta["processed_at_ns"]
    assert first.image.shape == (120, 160, 3)
    assert first.image[0, 0, 0] == 140  # Fake swap result, never the raw 40 camera pixel.
    time.sleep(0.2)
    later = engine.read_frame()
    assert later.meta["frame_id"] > first.meta["frame_id"] + 1
    assert not hasattr(engine, "_frame_queue")
    proc = engine._proc
    start = time.monotonic()
    engine.stop()
    assert time.monotonic() - start < 0.3
    assert engine.status() == EngineStatus.READY
    assert engine.read_frame() is None
    eventually(lambda: proc.poll() is not None)


@pytest.mark.parametrize("marker,reason", [("no_face", "no_face"),
                                            ("multiple_faces", "multiple_faces"),
                                            ("unchanged", "unchanged_output")])
def test_worker_uncertain_frames_are_placeholders_not_running(engine, install, marker, reason):
    root, cfg = install
    (root / marker).touch()
    engine.initialize(cfg)
    engine.start()
    frame = eventually(engine.read_frame)
    assert engine.status() == EngineStatus.STARTING
    assert frame.meta["safe_to_output"] is False
    assert frame.meta["face_swapped"] is False
    assert frame.meta["placeholder"] is True
    assert frame.meta["reason"] == reason
    assert frame.image[0, 0, 0] == 24
    (root / marker).unlink()
    eventually(lambda: engine.status() == EngineStatus.RUNNING)


@pytest.mark.parametrize("cause,expected", [("missing-model", "缺少模型"),
                                            ("blocked", "内容检查"),
                                            ("crash", "simulated inference failure"),
                                            ("bad-camera", "摄像头无法打开")])
def test_worker_errors_propagate_without_output(engine, install, cause, expected):
    root, cfg = install
    if cause == "missing-model":
        (root / "model.onnx").unlink()
    elif cause == "bad-camera":
        cfg.camera_index = 99
    else:
        (root / cause).touch()
    engine.initialize(cfg)
    engine.start()
    eventually(lambda: engine.status() == EngineStatus.ERROR)
    assert expected in engine.last_error()
    assert engine.read_frame() is None


def test_gpu_backend_missing_is_not_silently_cpu(engine, install):
    _, cfg = install
    cfg.extra["facefusion_execution_provider"] = "cuda"
    engine.initialize(cfg)
    engine.start()
    eventually(lambda: engine.status() == EngineStatus.ERROR)
    assert "CUDAExecutionProvider" in engine.last_error()


def test_model_hash_failure_preserves_file(install):
    root, _ = install
    model = root / "model.onnx"
    model.write_bytes(b"corrupt model")
    with pytest.raises(RuntimeError, match="校验不通过"):
        validate_local_sources({"m": {"path": str(model)}})
    assert model.read_bytes() == b"corrupt model"


def test_stopped_generation_cannot_restore_old_output(engine, install):
    _, cfg = install
    engine.initialize(cfg)
    engine.start()
    old_generation = engine._generation
    eventually(lambda: engine.status() == EngineStatus.RUNNING)
    engine.stop()
    engine._accept_message(old_generation, {"type": "error", "message": "stale"}, b"")
    engine._accept_message(old_generation, {"type": "ready", "engine_version": "3.9.0"}, b"")
    assert engine.status() == EngineStatus.READY
    assert engine.read_frame() is None
    engine.start()
    eventually(lambda: engine.status() == EngineStatus.RUNNING)


def test_capture_disconnect_clears_last_output(engine, install):
    root, cfg = install
    engine.initialize(cfg)
    engine.start()
    eventually(lambda: engine.status() == EngineStatus.RUNNING)
    (root / "disconnect").touch()
    eventually(lambda: engine.status() == EngineStatus.ERROR)
    assert engine.read_frame() is None
    assert "断开" in engine.last_error()


def test_watermark_option_is_respected_by_worker(engine, install):
    _, cfg = install
    cfg.watermark_text = None
    engine.initialize(cfg)
    engine.start()
    eventually(lambda: engine.status() == EngineStatus.RUNNING)
    assert np.all(engine.read_frame().image == 140)
    engine.stop()
    cfg.watermark_text = "Test preview"
    engine.initialize(cfg)
    engine.start()
    eventually(lambda: engine.status() == EngineStatus.RUNNING)
    assert np.any(engine.read_frame().image != 140)


def test_startup_watchdog_terminates_silent_process(engine, install, monkeypatch):
    _, cfg = install
    engine.initialize(cfg)
    engine._startup_timeout = 0.05
    monkeypatch.setattr(engine, "_launch_command", lambda: [sys.executable, "-c", "import time; time.sleep(60)"])
    engine.start()
    eventually(lambda: engine.status() == EngineStatus.ERROR)
    assert "加载超时" in engine.last_error()
    proc = engine._proc
    assert proc is not None
    eventually(lambda: proc.poll() is not None)


@pytest.mark.skipif(os.name == "nt", reason="Windows TerminateProcess cannot be ignored like SIGTERM")
def test_stop_kills_worker_that_ignores_termination(engine, install, monkeypatch):
    root, cfg = install
    marker = root / "signal-handler-ready"
    script = ("import signal,time,pathlib; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
              f"pathlib.Path({str(marker)!r}).touch(); time.sleep(60)")
    engine.initialize(cfg)
    monkeypatch.setattr(engine, "_launch_command", lambda: [sys.executable, "-c", script])
    engine.start()
    eventually(marker.exists)
    proc = engine._proc
    engine.stop()
    eventually(lambda: proc.poll() is not None, timeout=5)
    assert engine.status() == EngineStatus.READY


def test_changing_source_stops_worker_and_validates_new_source(engine, install):
    _, cfg = install
    engine.initialize(cfg)
    engine.start()
    eventually(lambda: engine.status() == EngineStatus.RUNNING)
    proc = engine._proc
    with pytest.raises(RuntimeError, match="至少一张"):
        engine.set_source_faces([])
    assert engine.status() == EngineStatus.ERROR
    assert engine.read_frame() is None
    eventually(lambda: proc.poll() is not None)


def test_launch_env_does_not_leak_frozen_bundle_paths(install, monkeypatch):
    from face_swap_studio.engines.facefusion import _worker_env

    root, _ = install
    bundle = root / "frozen-bundle"
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([str(bundle / "Qt"), "/usr/bin"]))
    monkeypatch.setenv("LD_LIBRARY_PATH", str(bundle))
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/system-libs")
    monkeypatch.setenv("PYTHONPATH", str(bundle))
    monkeypatch.setenv("QT_PLUGIN_PATH", str(bundle / "Qt/plugins"))
    env = _worker_env(Path(sys.executable))
    assert str(bundle) not in env["PATH"]
    assert "PYTHONPATH" not in env
    assert "QT_PLUGIN_PATH" not in env
    assert env["LD_LIBRARY_PATH"] == "/system-libs"
