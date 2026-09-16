# 顶级模式：DeepFaceLive + `.dfm`

归属：**编程助手2号** · 适配器版本 **0.4.0**（Codex #5）

## 官方 NVIDIA 便携包布局
- `_internal/CUDA/bin`（识别依据，目录改名 `DeepFaceLive` 仍应判 nvidia）
- `_internal/python/python.exe`
- `_internal/DeepFaceLive/main.py`
- `DeepFaceLive.bat`（**写死** `%~dp0userdata`）
- `userdata/dfm_models/`

## 壳契约（`EngineConfig.extra`）
| 键 | 必填 | 说明 |
|----|------|------|
| `dfm_path` | 是 | `.dfm` 路径 |
| `deepfacelive_root` | 建议 | 安装根目录 / `DEEPFACELIVE_ROOT` |
| `userdata_dir` | 否 | 自定义时适配器**不会**裸开 bat，改为 python + `--userdata-dir` |
| `require_nvidia` | 否 | 默认 true |
| `allow_unknown_build` | 否 | 默认 false |
| `dfm_version_hint` | 否 | 可选 |
| `no_cuda` | 否 | 强制 `--no-cuda` |

## 四阶段验收
见 `docs/PRO_ENGINE_FOUR_STAGE.md`。RUNNING ≠ 出画。
