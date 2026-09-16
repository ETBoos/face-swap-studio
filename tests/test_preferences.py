from face_swap_studio.core.preferences import PreferencesStore


def test_corrupt_preferences_recover_without_losing_the_file(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text("broken")
    store = PreferencesStore(path)
    data = store.load()
    assert store.last_error
    assert data["engine"] == "facefusion"
    assert path.read_text() == "broken"


def test_preferences_validate_and_force_engine_from_mode(tmp_path):
    store = PreferencesStore(tmp_path / "preferences.json")
    store.save(
        {
            "work_mode": "pro",
            "engine": "placeholder",
            "width": "bad",
            "camera_index": -100,
            "source_face_paths": ["face.png", 1],
            "consent_acked": True,
        }
    )
    data = store.load()
    assert data["engine"] == "deepfacelive"
    assert data["width"] == 1280
    assert data["camera_index"] == 0
    assert data["source_face_paths"] == ["face.png"]
    assert data["consent_acked"] is True
    assert not store.path.with_suffix(".tmp").exists()
