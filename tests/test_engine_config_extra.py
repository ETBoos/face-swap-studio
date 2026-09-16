"""Item 2: EngineConfig.extra must retain dfm_path from settings."""

from face_swap_studio.engines.config_builder import build_engine_config


def test_dfm_path_survives_settings_to_config():
    cfg = build_engine_config(
        {
            "camera_index": 0,
            "width": 1280,
            "height": 720,
            "gpu_device": "cuda:0",
            "dfm_path": r"D:\models\actor.dfm",
            "deepfacelive_root": r"D:\DeepFaceLive",
        },
        source_face_paths=["a.png"],
        watermark_text=None,
    )
    assert cfg.extra["dfm_path"] == r"D:\models\actor.dfm"
    assert cfg.extra["deepfacelive_root"] == r"D:\DeepFaceLive"
    assert cfg.source_face_paths == ["a.png"]


def test_nested_extra_merged():
    cfg = build_engine_config(
        {
            "extra": {"dfm_path": "/tmp/a.dfm", "no_cuda": True},
            "dfm_path": "/tmp/b.dfm",  # top-level wins
        }
    )
    assert cfg.extra["dfm_path"] == "/tmp/b.dfm"
    assert cfg.extra["no_cuda"] is True
