from face_swap_studio.engines.deepfacelive_stub import create_engine
from face_swap_studio.engines.modes import MODE_ENGINE_IDS, WorkMode


def test_mode_engine_mapping():
    assert MODE_ENGINE_IDS[WorkMode.SIMPLE] == "facefusion"
    assert MODE_ENGINE_IDS[WorkMode.PRO] == "deepfacelive"


def test_factory_simple_and_pro():
    assert create_engine("facefusion").capabilities().name == "facefusion"
    assert create_engine("deepfacelive").capabilities().name == "deepfacelive"
