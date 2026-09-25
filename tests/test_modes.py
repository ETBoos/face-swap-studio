import importlib

import pytest

from face_swap_studio.engines import create_engine
from face_swap_studio.engines.modes import MODE_ENGINE_IDS, WorkMode


def test_mode_engine_mapping():
    assert MODE_ENGINE_IDS[WorkMode.SIMPLE] == "facefusion"
    assert MODE_ENGINE_IDS[WorkMode.PRO] == "deepfacelive"


def test_factory_simple_and_pro():
    simple = create_engine("facefusion")
    pro = create_engine("deepfacelive")
    assert simple.capabilities().name == "facefusion"
    assert simple.capabilities().is_stub is False
    assert pro.capabilities().name == "deepfacelive"
    assert pro.capabilities().is_stub is False


@pytest.mark.parametrize(
    "name",
    (
        "face_swap_studio.engines.facefusion_stub",
        "face_swap_studio.engines.deepfacelive_stub",
    ),
)
def test_stub_reexport_modules_are_gone(name):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(name)
