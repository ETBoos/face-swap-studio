from face_swap_studio.engines.deepfacelive_stub import create_engine
from face_swap_studio.engines.modes import MODE_ENGINE_IDS, WorkMode


def test_mode_engine_mapping():
    assert MODE_ENGINE_IDS[WorkMode.SIMPLE] == "deeplivecam"
    assert MODE_ENGINE_IDS[WorkMode.PRO] == "deepfacelive"


def test_factory_simple_and_pro():
    simple = create_engine("deeplivecam")
    assert simple.capabilities().name == "deeplivecam"
    assert simple.capabilities().is_stub is False
    # Legacy id must not revive the FaceFusion stub.
    assert create_engine("facefusion").capabilities().name == "deeplivecam"
    pro = create_engine("deepfacelive")
    assert pro.capabilities().name == "deepfacelive"
    assert pro.capabilities().is_stub is False
