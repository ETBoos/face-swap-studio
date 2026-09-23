import pytest

from face_swap_studio.engines import create_engine
from face_swap_studio.engines.modes import MODE_ENGINE_IDS, WorkMode


def test_mode_engine_mapping():
    assert MODE_ENGINE_IDS[WorkMode.SIMPLE] == "deeplivecam"
    assert MODE_ENGINE_IDS[WorkMode.PRO] == "deepfacelive"


def test_factory_simple_and_pro():
    simple = create_engine("deeplivecam")
    assert simple.capabilities().name == "deeplivecam"
    assert simple.capabilities().is_stub is False
    # Legacy ids must not revive the deleted FaceFusion stub.
    assert create_engine("facefusion").capabilities().name == "deeplivecam"
    assert create_engine("ff").capabilities().name == "deeplivecam"
    assert create_engine("simple").capabilities().name == "deeplivecam"
    pro = create_engine("deepfacelive")
    assert pro.capabilities().name == "deepfacelive"
    assert pro.capabilities().is_stub is False


def test_removed_stub_modules_are_gone():
    with pytest.raises(ModuleNotFoundError):
        __import__("face_swap_studio.engines.facefusion_stub")
    with pytest.raises(ModuleNotFoundError):
        __import__("face_swap_studio.engines.deepfacelive_stub")
