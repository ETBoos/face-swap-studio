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
            "userdata_dir": r"D:\dfl-userdata",
        },
        source_face_paths=["a.png"],
        watermark_text=None,
    )
    assert cfg.extra["dfm_path"] == r"D:\models\actor.dfm"
    assert cfg.extra["deepfacelive_root"] == r"D:\DeepFaceLive"
    assert cfg.extra["userdata_dir"] == r"D:\dfl-userdata"
    assert cfg.source_face_paths == ["a.png"]


def test_deeplivecam_keys_survive_settings_to_config():
    cfg = build_engine_config(
        {
            "gpu_device": "cuda:0",
            "deeplivecam_root": r"D:\Deep-Live-Cam",
            "dlc_session": "preview",
            "preview_target": r"D:\stills\cam.png",
            "execution_provider": "",
        },
        source_face_paths=[r"D:\faces\a.png"],
    )
    assert cfg.extra["deeplivecam_root"] == r"D:\Deep-Live-Cam"
    assert cfg.extra["dlc_session"] == "preview"
    assert cfg.extra["preview_target"] == r"D:\stills\cam.png"
    assert "execution_provider" not in cfg.extra
    assert cfg.source_face_paths == [r"D:\faces\a.png"]


def test_pro_config_omits_instant_keys_even_when_dlc_path_is_filled():
    cfg = build_engine_config(
        {
            "work_mode": "pro",
            "engine": "deepfacelive",
            "dfm_path": r"D:\models\actor.dfm",
            "deepfacelive_root": r"D:\DeepFaceLive_NVIDIA",
            "deeplivecam_root": r"D:\Deep-Live-Cam",
            "dlc_session": "preview",
        }
    )
    assert cfg.extra["dfm_path"] == r"D:\models\actor.dfm"
    assert cfg.extra["deepfacelive_root"] == r"D:\DeepFaceLive_NVIDIA"
    assert "deeplivecam_root" not in cfg.extra
    assert "dlc_session" not in cfg.extra


def test_nested_extra_merged():
    cfg = build_engine_config(
        {
            "extra": {"dfm_path": "/tmp/a.dfm", "no_cuda": True},
            "dfm_path": "/tmp/b.dfm",  # top-level wins
        }
    )
    assert cfg.extra["dfm_path"] == "/tmp/b.dfm"
    assert cfg.extra["no_cuda"] is True
