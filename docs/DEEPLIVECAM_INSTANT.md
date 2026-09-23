# 即用模式 · Deep-Live-Cam（导入脸图 → 首帧 / 实时）

即用 = 选一张源脸图，由**上游 Deep-Live-Cam** 做换脸。本仓库不实现换脸算法，也不改 SAEHD / AMP / `.dfm` 训练。专模仍是 DeepFaceLive，见 `docs/PRO_DEEPFACELIVE.md`。

本文件描述的是适配器怎么找到并启动 DLC。**没有**在本开发环境的 NVIDIA Windows 或物理摄像头上跑通；下面的「Win 验收」是现场要做的事，不是已通过的记录。

## 安装目录怎么找到

`resolve_deeplivecam_root()` 顺序：

1. 设置 / `EngineConfig.extra` 里的 `deeplivecam_root`（或别名 `dlc_root`）。**填了但不像 DLC 目录就直接失败**，不会改去用别的盘上的副本。
2. 环境变量 `DEEP_LIVE_CAM_ROOT`，然后 `DLC_ROOT`。
3. 常见路径：`C:\Deep-Live-Cam`、`D:\Deep-Live-Cam`、`%USERPROFILE%\Deep-Live-Cam`，以及不带连字符的 `DeepLiveCam`。

像 DLC 目录的条件：存在 `run.py` **并且**存在 `modules/core.py`。

Windows 上可以双击或运行 `scripts\setup-deeplivecam-cpu-win.bat` 做 CPU 一键安装（清华 pip 源、下载模型，装到 `%USERPROFILE%\Deep-Live-Cam`）。装完后把 `deeplivecam_root` 设成该目录。

解释器（不要用本壳的 Python）：

1. `deeplivecam_python`（填了但文件不存在则失败）
2. `DEEP_LIVE_CAM_PYTHON` / `DLC_PYTHON`
3. `<root>\venv\Scripts\python.exe` 或 `<root>/venv/bin/python`（也认 `.venv`）

模型文件 `models/inswapper_128.onnx` 或 `inswapper_128_fp16.onnx` 缺失时不拦截；DLC 自己的 `pre_check` 会尝试下载。首次运行需要网络和 ffmpeg（DLC 的 `pre_check` 要求 PATH 里有 ffmpeg，静帧也一样）。

## 两种启动

| `dlc_session` | 谁换脸 | 画面在哪 | 命令形态 |
| --- | --- | --- | --- |
| `preview`（默认） | 上游 `run.py` 静帧管线 | 本壳预览窗的**首帧** | `python run.py -s 源脸 -t 目标静帧 -o 输出.png --frame-processor face_swapper --execution-provider cuda` |
| `live` | 上游 Live 窗口 | **DLC 自己的窗口**。本壳 `read_frame()` 为 `None` | 引导脚本打开 `run.py`，**不**把 `-s` 传给 `run.py` |

`-s/--source` 在当前 Deep-Live-Cam 里会把 `modules.globals.headless` 设为真并跳过 GUI，Live 按钮不会出现。所以实时模式用 `engines/dlc_live_bootstrap.py`：先让 `run.py` 做它自己的 CUDA DLL 准备，再在 `parse_args()` 之后把源脸写进 `modules.globals.source_path`，并强制 `headless = False`。引导脚本只有标准库，用 DLC 的 venv 执行。

目标静帧（仅 `preview`）：

- 有 `preview_target`（或 `target_image`）就用那张图，须能被 OpenCV 读入。
- 否则用本壳 OpenCV 从 `camera_index` **抓一帧**存成 jpg，再交给 DLC。抓帧不是换脸。
- 摄像头打不开时，初始化失败并提示改填 `preview_target`。

`gpu_device=cuda:0` 且未填 `execution_provider` 时传 `cuda`。允许值：`cpu` `cuda` `dml` `coreml` `rocm` `openvino` `tensorrt`。DLC 会按本机 onnxruntime 再过滤；机器上没有 cuda 提供者时进程会在 argparse 失败，日志在 `%TEMP%\face-swap-studio\dlc\`。

## 配置键

| 键 | 作用 |
| --- | --- |
| `work_mode=simple` | 即用。引擎 id 为 `deeplivecam`。旧值 `facefusion` 只是别名，不再走 FaceFusion stub |
| `source_face_paths` / 界面「选择脸图」 | 第一张图是 DLC 的 `-s` |
| `deeplivecam_root` / `dlc_root` | 安装目录 |
| `deeplivecam_python` | 可选，DLC venv 的 python |
| `dlc_session` | `preview` 或 `live` |
| `preview_target` / `target_image` | 首帧的目标静帧 |
| `execution_provider` | 空则按 `gpu_device` 推导 |
| `frame_processors` | 默认 `face_swapper`。可选再加 `face_enhancer`、`face_enhancer_gpen256`、`face_enhancer_gpen512` |
| `execution_threads` / `dlc_max_memory` | 传给 DLC 的同名参数；空则不传 |
| `dlc_many_faces` / `dlc_mouth_mask` / `live_mirror` | 对应 `--many-faces`、`--mouth-mask`、`--live-mirror` |
| `dlc_lang` | 默认 `en` |
| `preview_timeout_sec` | 默认 300。超时则杀掉首帧进程 |
| `camera_index` / `width` / `height` | 仅用于「没有 preview_target 时抓一帧」 |

专模键（`dfm_path`、`deepfacelive_root`、`userdata_dir` 等）原样保留，即用启动不会读它们。

## Win 上怎么验「选图 → 首帧」

需要：Windows、NVIDIA、已装好的 Deep-Live-Cam（官方仓库的 `run.py` + venv）、ffmpeg、一张**已授权**源脸、一张含人脸的目标静帧（或可用的摄像头索引）。

1. 设置 `DEEP_LIVE_CAM_ROOT` 指向含 `run.py` 的目录，或在壳的设置里填「Deep-Live-Cam 目录」。
2. 可选：`powershell -File scripts\check-deeplivecam.ps1`
3. 启动壳：`scripts\start-win.bat`
4. 工作模式保持 **即用（Deep-Live-Cam · 导入脸图）**。即用输出保持 **首帧进预览窗**。
5. 勾选授权清单 → **选择脸图…** → 在设置里把「首帧目标静帧」设成一张含人脸的图（没有摄像头时必须设）。
6. **开始预览**。状态栏会先写「正在生成首帧」。DLC 第一次会下模型，可能要几分钟。`RUNNING` 还不是出画。
7. 通过：本壳预览窗出现一张图，状态栏写「即用首帧已出画」。该图是 DLC 写出的 PNG（`%TEMP%\face-swap-studio\dlc\first_frame_*.png`），不是本程序画的假脸。
8. 失败：弹窗里带 DLC 日志尾部。先看 ffmpeg、`--execution-provider cuda` 是否在该 venv 的 onnxruntime 里、两张图是否都有脸。

实时摄像头（阶段 3 的另一条，**未在此环境验证**）：

1. 即用输出改为 **DLC 实时窗口**，源脸仍选好，开始预览。
2. 应出现 Deep-Live-Cam 自己的窗口，源脸已写入它的全局变量（缩略图可能仍是空的，这是上游 UI 不在启动时重画）。
3. 在 **DLC 窗口**里选摄像头，点 **Live**。换脸画面在那个窗口，不在本壳。
4. 本壳摄像头索引只用于首帧抓拍，不保证等于 DLC 下拉框的顺序。

出站到微信仍走 L1→L3，与引擎无关。未按 `COMPAT_MATRIX.md` 取证前不得写「已支持微信」。

## 不要误验

| 现象 | 含义 |
| --- | --- |
| `EngineStatus.RUNNING` | 只说明 DLC 进程已拉起 |
| 预览窗有图且 `meta.kind=first_frame` | 静帧管线写出了 PNG。不是摄像头循环，也不是本机已做 NVIDIA 验收 |
| `meta.hardware_verified` | 适配器固定为 false |
| 实时模式 `read_frame()` 为 `None` | 预期。帧在 DLC 窗口 |
| 占位引擎 | 设置里选手动「占位引擎」才会绕过 DLC，画面无换脸 |
