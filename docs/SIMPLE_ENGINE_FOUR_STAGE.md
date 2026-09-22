# 即用模式（Deep-Live-Cam · 导入脸图）四阶段验收勾选表

即用后端是 **Deep-Live-Cam**，不是 FaceFusion stub。专模仍是 DeepFaceLive + `.dfm`（`docs/PRO_ENGINE_FOUR_STAGE.md`）。

> RUNNING ≠ 出画。换脸只发生在上游 DLC 进程里。每阶段必须有证据。微信接收仍依赖真机 + `COMPAT_MATRIX`。
> 本仓库开发环境**没有** NVIDIA Windows / 物理摄像头验收记录。

| 阶段 | 勾选 | 通过标准 | 证据 | 依赖真机 |
| --- | --- | --- | --- | --- |
| 1. 外部启动 | ☐ | `dlc_session=preview` 时拉起 `<DLC>\venv\...\python run.py -s -t -o`；或 `live` 时拉起 `dlc_live_bootstrap.py`（子进程里的 `run.py` **不带** `-s`）。非 0 退出或超时记 ERROR | 任务管理器 + `%TEMP%\face-swap-studio\dlc\dlc_*_stderr.log` | 否（有 DLC 目录即可看到命令；真正跑起来要 DLC venv） |
| 2. 源脸被接受 | ☐ | 界面「选择脸图」或项目素材路径进入 `source_face_paths`；DLC 日志没有 “select a source image” / 找不到 `-s` 文件 | 素材名 + 启动命令里的 `-s` 路径 | 否 |
| 3. 首帧出画 | ☐ | **静帧路径**：本壳预览窗出现 DLC 写出的 PNG（状态栏「即用首帧已出画」）。**或** 实时路径：DLC 窗口里点 Live 后出现换脸画面（本壳不拉流） | 预览截图 ≥1，并注明是静帧首帧还是 Live 窗口 | 静帧可无摄像头（用 `preview_target`）；Live 要 Win+NVIDIA+摄像头 |
| 4. 微信接收 | ☐ | 微信 PC 选中虚拟摄像头/采集卡后，手机端看到换脸画面（L1→L3） | 手机端录屏；未测通不得写「已支持」 | 是 |

## 选图 → 首帧（阶段 3 的静帧路径）

逐步操作见 `docs/DEEPLIVECAM_INSTANT.md`。摘要：即用 + 「首帧进预览窗」+ 源脸 + （`preview_target` 或摄像头抓的一帧）→ 开始预览 → 预览窗显示 DLC 的输出 PNG。

## 相关文档

- 启动与配置键：`docs/DEEPLIVECAM_INSTANT.md`
- 实时验收指标：`docs/REALTIME_ACCEPTANCE.md`
- L1：`docs/L1_VIRTUAL_CAM.md`
- L3：`docs/L3_CAPTURE_CARD_BEGINNER.md`
- 旧 FaceFusion 预设笔记（**不是**当前即用引擎）：`docs/FACEFUSION_SIMPLE_PRESETS.md`
