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
    assert simple.capabilities().is_stub is True
    assert pro.capabilities().name == "deepfacelive"
    assert pro.capabilities().is_stub is False


def test_launched_dfl_adapter_is_not_imported_via_stub_module():
    """Pro adapter shipped; the old stub re-export module must stay gone."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("face_swap_studio.engines.deepfacelive_stub")
