"""Numerical regression checks for face-only rendering and tracking behavior."""
import cv2
import numpy as np
import pytest

from face_swap_studio.engines.deepfacelive_worker import (
    AdaptiveLandmarks,
    match_face_color,
    warp_face_region,
)


def test_tracker_damps_small_jitter_but_follows_large_motion_and_resets():
    tracker = AdaptiveLandmarks()
    points = np.tile([100., 100.], (106, 1)).astype(np.float32)
    tracker.update(points, 100, 1., np)
    smoothed = tracker.update(points + 0.5, 100, 1 + 1 / 30, np)
    assert np.all(smoothed > points) and np.all(smoothed < points + 0.5)
    moved = points + 40
    np.testing.assert_allclose(tracker.update(moved, 100, 1.07, np), moved)
    np.testing.assert_allclose(tracker.update(points, 100, 2., np), points)
    tracker.reset()
    np.testing.assert_allclose(tracker.update(moved, 100, 2.01, np), moved)


def test_low_fps_does_not_accumulate_long_tracking_lag():
    points = np.ones((106, 2), np.float32) * 100
    tracker = AdaptiveLandmarks()
    tracker.update(points, 100, 1, np)
    result = tracker.update(points + 0.5, 100, 1.125, np)
    assert np.max(np.abs(result - (points + 0.5))) < 0.08


@pytest.mark.parametrize('translation', [(80, 50), (-15, 20), (250, 150), (-300, -300)])
def test_roi_warp_matches_full_frame_even_at_image_edges(translation):
    rng = np.random.default_rng(41)
    face = rng.random((64, 64, 3)).astype(np.float32)
    mask = np.zeros((64, 64), np.float32)
    cv2.circle(mask, (32, 32), 26, 1, -1)
    mask = cv2.GaussianBlur(mask, (9, 9), 2)
    affine = cv2.getRotationMatrix2D((32, 32), 17, 1.3).astype(np.float32)
    affine[:, 2] += translation
    expected_mask = cv2.warpAffine(mask, affine, (320, 240))
    expected_face = cv2.warpAffine(face, affine, (320, 240))
    result = warp_face_region(face, mask, affine, (240, 320, 3), cv2, np)
    if result is None:
        assert not np.any(expected_mask)
        return
    x0, y0, x1, y1, actual_face, actual_mask = result
    reconstructed = np.zeros((240, 320), np.float32)
    reconstructed[y0:y1, x0:x1] = actual_mask
    np.testing.assert_allclose(reconstructed, expected_mask, atol=1e-5)
    # Different OpenCV warp origins may round interpolation coordinates differently.
    error = np.abs(actual_face - expected_face[y0:y1, x0:x1])
    assert error.max() < 1 / 255 and error.mean() < 1e-4
    assert actual_mask.size < expected_mask.size / 2


def test_color_match_reduces_cast_without_changing_shape_or_erasing_texture():
    lab = np.full((64, 64, 3), (55, 6, 12), np.float32)
    lab[:, :, 0] += np.linspace(-4, 4, 64, dtype=np.float32)[None, :]
    face = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    target_lab = lab + np.float32([6, -4, -3])
    original = np.round(cv2.cvtColor(target_lab, cv2.COLOR_LAB2BGR) * 255).astype(np.uint8)
    corrected = match_face_color(face, original, np.ones((64, 64), np.float32), cv2, np)
    result_lab = cv2.cvtColor(corrected, cv2.COLOR_BGR2LAB)
    assert corrected.shape == face.shape and corrected.dtype == np.float32
    assert np.isfinite(corrected).all() and corrected.min() >= 0 and corrected.max() <= 1
    assert np.abs(result_lab - target_lab).mean() < np.abs(lab - target_lab).mean()
    assert result_lab[:, :, 0].std() > lab[:, :, 0].std() * 0.9
    np.testing.assert_array_equal(
        match_face_color(face, original, np.zeros((64, 64), np.float32), cv2, np), face)
