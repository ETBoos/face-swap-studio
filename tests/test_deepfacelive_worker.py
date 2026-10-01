"""Headless process contract with synthetic models; not a GPU/quality benchmark."""
import io
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from face_swap_studio.engines.base import EngineConfig, EngineStatus
from face_swap_studio.engines.deepfacelive import DeepFaceLiveEngine
from face_swap_studio.engines.deepfacelive_worker import require_cuda, validate_prediction
from face_swap_studio.engines.facefusion_protocol import ProtocolError, read_message, write_message


def until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("worker timed out")


@pytest.fixture
def worker(tmp_path):
    root = tmp_path / "NVIDIA 中文 path"
    source = root / "_internal/DeepFaceLive"

    def put(relative, content):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    put("main.py", "raise AssertionError('GUI must never launch')")
    put("modelhub/__init__.py", '''
import cv2, numpy as np, time
from pathlib import Path
ROOT = Path(__file__).parent.parent
class Camera:
    def __init__(self, index, *args): self.index = index
    def isOpened(self): return self.index != 99
    def set(self, *args): pass
    def read(self):
        time.sleep(0.02)
        if (ROOT/'disconnect').exists(): return False, None
        return True, np.full((120,160,3),40,np.uint8)
    def release(self): (ROOT/'released').touch()
cv2.VideoCapture = Camera
''')
    put("modelhub/onnx.py", '''
from pathlib import Path
import numpy as np
ROOT = Path(__file__).parent.parent
class Session:
    def get_providers(self):
        return ['CPUExecutionProvider'] if (ROOT/'cpu').exists() else ['CUDAExecutionProvider']
    def disable_fallback(self): pass
class YoloV5Face:
    def __init__(self, device): self._sess=Session()
    def extract(self, frame, **kwargs):
        if (ROOT/'no_face').exists(): return [[]]
        if (ROOT/'multiple').exists(): return [[(30,30,100,100)]*2]
        return [[(30,30,100,100)]]
class InsightFace2D106:
    def __init__(self, device): self._sess=Session()
    def extract(self, frame): return np.full((1,106,2),96,np.float32)
''')
    put("modelhub/DFLive/__init__.py", "")
    put("modelhub/DFLive/DFMModel.py", '''
import numpy as np
from modelhub.onnx import Session, ROOT
class DFMModel:
    def __init__(self, path, device): self._sess=Session()
    def get_input_res(self): return 64,64
    def convert(self, frame):
        if (ROOT/'crash').exists(): raise RuntimeError('synthetic inference failure')
        size=frame.shape[0]
        mask=np.ones((1,size,size,1),np.float32)
        if (ROOT/'empty_mask').exists(): mask *= 0
        if (ROOT/'weak_mask').exists(): mask *= 0.54
        if (ROOT/'black_output').exists(): return np.zeros((1,size,size,3),np.float32), mask, mask
        if (ROOT/'unchanged').exists(): return frame[None], mask, mask
        return np.full((1,size,size,3),0.75,np.float32), mask, mask
''')
    put("xlib/__init__.py", "")
    put("xlib/onnxruntime.py", '''
class Device:
    def get_execution_provider(self): return 'CUDAExecutionProvider'
    def get_index(self): return 0
def get_available_devices_info(**kwargs): return [Device()]
''')
    put("xlib/face/FLandmarks2D.py", "# layout marker")
    put("xlib/face/__init__.py", '''
import cv2, numpy as np
from pathlib import Path
ROOT=Path(__file__).parents[2]
class Matrix:
    def invert(self): return self
    def to_exact_mat(self,*args):
        x=140 if (ROOT/'misalign').exists() else 40
        return np.array([[1,0,x],[0,1,20]],np.float32)
class FRect:
    @staticmethod
    def from_ltrb(rect): return FRect()
    def cut(self,frame,coverage,size,**kw): return cv2.resize(frame,(size,size)), Matrix()
class FLandmarks2D(FRect):
    @staticmethod
    def create(kind,points): return FLandmarks2D()
    def transform(self,*args,**kw): return self
    def as_numpy(self,w_h=None): return np.full((106,2),0.5,np.float32) * (w_h or (1,1))
    def get_convexhull_mask(self,h_w,**kw):
        mask=np.zeros((h_w[0],h_w[1],1),np.float32)
        cv2.circle(mask,(h_w[1]//2,h_w[0]//2),h_w[0]//4,1,-1)
        return mask
class ELandmarks2D: L106=106
''')
    python = root / "_internal/python/python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"fixture")
    model = tmp_path / "人物.dfm"
    model.write_bytes(b"\x08\x01onnx" + b"\x00" * 600000)
    eng = DeepFaceLiveEngine()
    cfg = EngineConfig(width=160, height=120,
                       extra={"deepfacelive_root": str(root), "dfm_path": str(model)})
    eng.initialize(cfg)
    eng._python = Path(sys.executable)
    yield eng, source, cfg
    eng.shutdown()


def test_status_protocol_validation():
    stream = io.BytesIO()
    write_message(stream, {"type": "status", "message": "正在加载模型…"})
    stream.seek(0)
    assert read_message(stream)[0]["message"] == "正在加载模型…"
    for invalid in (None, 1, "", "a" * 513):
        with pytest.raises(ProtocolError):
            write_message(io.BytesIO(), {"type": "status", "message": invalid})


def test_cuda_fallback_is_rejected():
    with pytest.raises(RuntimeError, match="未回退 CPU"):
        require_cuda(SimpleNamespace(_sess=SimpleNamespace(get_providers=lambda: ['CPUExecutionProvider'])), "DFM")


def test_prediction_shape_and_nan_rejected():
    valid = [np.ones((1,64,64,c),np.float32) for c in (3,1,1)]
    assert len(validate_prediction(valid, 64, np)) == 3
    valid[0][0,0,0,0] = np.nan
    with pytest.raises(RuntimeError, match="数值无效"):
        validate_prediction(valid, 64, np)


def test_worker_returns_swapped_frames_then_hides_no_face_and_disconnects(worker):
    eng, source, _ = worker
    eng.start()
    until(lambda: eng.status() == EngineStatus.RUNNING)
    frame = until(eng.read_frame)
    assert frame.meta['safe_to_output'] and frame.image[45,65,0] > 40
    (source/'no_face').touch()

    def placeholder():
        frame = eng.read_frame()
        return frame if frame is not None and frame.meta.get('placeholder') else None

    frame = until(placeholder)
    assert np.all(frame.image == 24) and not frame.meta['safe_to_output']
    (source/'disconnect').touch()
    until(lambda: eng.status() == EngineStatus.ERROR)
    assert '摄像头' in eng.last_error()
    assert eng.read_frame() is None
    until(lambda: (source/'released').exists())


@pytest.mark.parametrize('marker', ['multiple', 'empty_mask', 'weak_mask', 'black_output',
                                     'misalign', 'unchanged'])
def test_unsafe_frames_never_enable_output(worker, marker):
    eng, source, _ = worker
    (source/marker).touch()
    eng.start()
    frame = until(eng.read_frame)
    assert frame.meta['placeholder'] and not frame.meta['safe_to_output']
    assert eng.status() == EngineStatus.STARTING
    assert np.all(frame.image == 24)


def test_cpu_fallback_is_reported_before_camera(worker):
    eng, source, _ = worker
    (source/'cpu').touch()
    eng.start()
    until(lambda: eng.status() == EngineStatus.ERROR)
    assert '未启用 NVIDIA CUDA' in eng.last_error()
    assert eng.read_frame() is None
    assert not (source/'released').exists()


def test_stop_restart_has_no_old_frames(worker):
    eng, source, _ = worker
    eng.start()
    until(lambda: eng.status() == EngineStatus.RUNNING)
    start = time.monotonic()
    eng.stop()
    assert time.monotonic() - start < 0.5
    assert eng.read_frame() is None
    (source/'crash').touch()
    eng.start()
    until(lambda: eng.status() == EngineStatus.ERROR)
    assert 'synthetic inference failure' in eng.last_error()
