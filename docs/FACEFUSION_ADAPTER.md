# FaceFusion 照片引擎：接入与验证边界

状态：已实现实际调用路径和跨进程测试；**尚未完成真实权重、实体摄像头、Windows NVIDIA 或微信接收端验证**。合成测试不能证明换脸画质、帧率、延迟或平台兼容性。

## 当前支持范围

- 用户自行安装的官方 **FaceFusion 3.9.0**，目录中包含 `facefusion.py` 和 `facefusion/metadata.py`。旧版本和开发分支不在此适配范围。
- 用户为 FaceFusion 配置的专用 Python。应用不把 FaceFusion/ONNX Runtime/CUDA 装进自身 Qt 环境，也不回退到打包应用本身充当 Python。
- 模型：`inswapper_128`（默认）、`inswapper_128_fp16`。执行后端：`cuda`（默认）、`cpu`、`directml`、`coreml`；存在后端不代表已通过性能认证。
- 160×120 至 1920×1080，默认 1280×720。请求摄像头 30 FPS，不把这个请求值作为实际处理 FPS。摄像头输出按比例缩放并留黑边。
- 每张形象图恰好一人，最多 8 张同一人的形象图。运行时画面中也必须恰好一张可检测人脸；多人及无脸时输出安全占位。暂不支持多人匹配、任意模型、跨帧追踪或动态热换源脸。
- 保留上游内容检查，每张源图片和每个处理帧都运行检查。未通过即停止，不禁用检查、不自动下载模型、不删除校验失败的模型。
- 图片、模型及摄像头帧均在本机处理。控制消息走 stdin；结果帧走 stdout 二进制管道；本地错误走 stderr。适配器不上传、不落盘保存相机帧、不监听网络端口。

## 配置

`EngineConfig.extra` 使用以下键：

| 键 | 用途 |
|---|---|
| `facefusion_root` | FaceFusion 根目录；也支持环境变量 `FACEFUSION_ROOT` |
| `facefusion_python` | FaceFusion 环境的 `python.exe` / `python`；也支持 `FACEFUSION_PYTHON` |
| `facefusion_model` | 默认 `inswapper_128` |
| `facefusion_execution_provider` | 默认取 `gpu_device` 前缀，例如 `cuda:0` → `cuda` |
| `facefusion_startup_timeout` | 10–600 秒，默认 120 秒 |

Python 自动探测仅检查指定根目录中的 `.venv`、`venv`、常见便携路径，以及用户目录中 miniconda/anaconda/miniforge 的 `facefusion` 环境。找不到时要求明确填写路径。显式路径无效时不会改用其他安装。

`watermark_text=None` 关闭引擎水印，有值时绘制。OpenCV 默认字体不支持中文；含非 ASCII 字符时显示 `FaceSwap Studio Preview`。源脸更换会停止旧进程并重新验证，调用方随后重新启动。

## 需要用户事先准备的模型

适配器按官方选定流水线检查 `.assets/models` 中现有模型与对应 `.hash` 文件：

- 选定的 `inswapper_128` 或 `inswapper_128_fp16`。
- `yoloface_8n`、`2dfan4`、`fan_68_5`、`arcface_w600k_r50`、`fairface`。
- `xseg_1`、`bisenet_resnet_34`；遮罩默认使用 box + occlusion。parser 是上游 common pre-check/inference pool 的依赖，虽然当前不启用 region 遮罩。
- `nsfw_1`、`nsfw_2`、`nsfw_3`（上游内容检查）。

具体缺失项以错误信息和该官方版本的模型目录为准。校验使用官方 3.9.0 的 CRC32 `.hash` 格式，采用分块读取；这是完整性检查，不等同于来源的密码学认证。适配器只应指向用户信任的安装目录和模型。

## 实际调用路径

1. 主进程仅用 AST 读取版本并校验配置；`initialize()` 不导入第三方 FaceFusion 包、不打开摄像头。
2. `start()` 创建后台读取线程，在 FaceFusion 专用 Python 内执行本项目的 `facefusion_worker.py`。
3. worker 从指定 root 导入 FaceFusion；复核版本与 ONNX provider，初始化明确的 state defaults，不读取用户 `facefusion.ini` 或依赖 CLI 隐式状态。
4. 在导入模型模块之前，将下载入口改为只验证本地文件，禁止 curl 和远程 provider 探测；这不修改上游文件或内容检测功能。
5. `face_swapper.core.pre_check()` 验证依赖模型；创建推理会话并检查请求 provider 实际存在于会话，防止 CUDA 失败后静默退到 CPU。
6. 源图通过 `vision.read_static_images`、`face_creator.get_many_faces`、`average_face_identity` 建立身份信息。
7. 单独摄像头线程始终只保留最新输入帧。推理线程使用 `get_many_faces`，明确检查恰好一张目标脸后调用官方 `face_swapper.core.swap_face`，由其完成对齐、推理、遮罩与贴回。没有调用会在无脸时原样返回图像的上层 `process_frame`。
8. 结果与输入像素完全一致时也视为未确认换脸，显示占位，不把它作为已换脸输出。此检查仅能发现原样返回，**不能证明模型质量或身份效果正确**。
9. stdout 使用有长度上限的 JSON header + BGR24 bytes，主进程持续读取并覆盖一个结果槽。`read_frame()` 取走当前槽；没有无界帧队列。

官方 API 源码核对：

- [3.9.0 swapper core](https://github.com/facefusion/facefusion/blob/3.9.0/facefusion/processors/modules/face_swapper/core.py)
- [3.9.0 face_creator](https://github.com/facefusion/facefusion/blob/3.9.0/facefusion/face_creator.py)
- [3.9.0 streamer](https://github.com/facefusion/facefusion/blob/3.9.0/facefusion/streamer.py)
- [3.9.0 state_manager](https://github.com/facefusion/facefusion/blob/3.9.0/facefusion/state_manager.py)
- [3.9.0 download](https://github.com/facefusion/facefusion/blob/3.9.0/facefusion/download.py)

这些内部 API 没有跨版本稳定性保证。升级时应重新审查 API 和状态默认值，更新支持版本并执行契约及真机测试。

## 状态、停止与输出闸门

- `READY`：配置文件检查通过，模型尚未在 worker 中加载。
- `STARTING`：worker 正在启动，或已提供占位画面而尚未产生第一张真实处理结果。
- `RUNNING`：至少收到一张真实处理结果。此后仍需**逐帧**检查输出资格，RUNNING 不保证每一帧都可输出。
- `ERROR`：启动/模型/摄像头/协议异常。清空结果槽，终止 worker，并保存可读错误。
- worker ready 消息仅说明模型初始化完成，不代表摄像头或真实首帧已成功。ready 后连续 15 秒没有新画面会失败；摄像头读取无帧等待默认 5 秒。
- `stop()` 非阻塞，立即使当前会话编号失效并清空结果槽。后台回收进程；无法正常终止时 2 秒后强制结束。迟到的旧会话帧/错误不能污染新会话。

仅同时满足下列元信息的帧才交给 UI/输出端：

```python
{"stub": False, "face_swapped": True, "safe_to_output": True}
```

无脸/多人/未确认处理的占位帧具有 `placeholder=True`、`face_swapped=False`、`safe_to_output=False`，图像完全由纯色与提示文字生成。异常直接报错，不把原始摄像头送出去。输出端仍需自行做断流占位，不能持续发送缓存的旧帧。

适配器验证单调时钟次序，拒绝来自未来或时间倒置的帧；`read_frame()` 对距采集超过 2 秒的结果改为不可输出的纯色占位。这是防止挂起后旧帧复活的宽松截止线，不是承诺可接受 2 秒延迟。真正低延迟验收另行测量。

每帧提供递增 `frame_id`、`captured_at_ns`、`processed_at_ns`、`received_at_ns`（墙上时钟），以及 `captured_monotonic_ns`、`processed_monotonic_ns`、`processing_ms`、`capture_to_processed_ms`。这里的采集时间是在 OpenCV 返回帧时记录，**不是传感器曝光时刻**；端到端延迟还需外部测量。

## 打包与环境隔离

Windows 安装包必须保留 worker 和 protocol 为可读取的真实 `.py` 数据文件，不能只放在 PYZ 中。worker 不依赖安装包的 Qt/numpy。

PyInstaller 会改变 DLL 搜索环境。适配器清除 Python/Qt 注入环境变量和指向 `_MEIPASS` 的路径；Windows 启动命令使用外部 Python 的最小 bootstrap，在导入数值库前于**子进程**调用 `SetDllDirectoryW(None)`，再运行 worker；主 GUI 的 DLL 状态不变，从而避免 Qt 加载并发风险。worker 为 FaceFusion 环境保留 conda `Library/bin` / `DLLs` 搜索句柄。stdout fd 在导入原生库前与日志分离，原生库直接打印也不会污染帧协议。

依据：[PyInstaller — Launching External Programs](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application)。Windows 打包→外部 Python→真实 ONNX/CUDA 的完整路径仍列为必须真机验证的项目。

## 已验证与待验证

`tests/test_facefusion_adapter.py` 覆盖协议边界、错误数据、安装/版本检查、环境隔离、真实子进程通信、首帧状态、最新帧覆盖、水印、无脸/多人占位、缺模型/内容检查/推理错误/摄像头断开、启动超时、停机与强制回收、旧会话隔离。

跨进程测试安装的是**合成 FaceFusion API**与**合成摄像头**，仅证明本产品的桥接和生命周期。未使用真实权重、未验证算法输出、未获取实体摄像头。正式验收还需：官方 3.9.0 + 所需权重；干净 Windows + NVIDIA；真实源脸/摄像头；60 分钟稳定性；OBS/微信手机端实际画面；质量、延迟、帧率、多人/无脸、遮挡、失追与故障测试。

## 使用权边界

本项目不分发 FaceFusion 或任何模型权重。FaceFusion 代码和每个模型有各自许可；用户提供权重不自动获得商业使用权。集成时需要逐项核对检测、识别、分类、换脸及遮罩依赖，而不能只检查 swapper。[FaceFusion 官方许可清单](https://docs.facefusion.io/introduction/licenses)
