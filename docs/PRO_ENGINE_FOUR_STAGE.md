# 顶级模式（DeepFaceLive + `.dfm`）四阶段验收勾选表

归属：**编程助手2号**  
> **RUNNING ≠ 模型已加载 ≠ 首帧出画 ≠ 微信已通。** 每阶段单独取证。

| 阶段 | 勾选 | 通过标准 | 证据 | 依赖真机 |
| --- | --- | --- | --- | --- |
| 1. 外部程序启动 | ☐ | 适配器 `start()` 拉起 DeepFaceLive 子进程；任务管理器可见；非 0 退出码记 ERROR | 进程名 + 退出码日志；`detect_build_kind`=nvidia（含 `_internal/CUDA/bin`） | 否（有安装目录即可） |
| 2. 模型实际加载 | ☐ | `.dfm` 已在**实际使用的** `userdata/dfm_models/`（自定义 userdata 必须与启动 `--userdata-dir` 一致）；DFL UI **Face swapper** 能选到该模型并加载成功 | 目录截图 + DFL 模型列表截图 | 否（需本机 DFL） |
| 3. 首帧出画 | ☐ | DFL 预览/Stream 出现换脸首帧；物理摄像头进、指定人物出 | 预览截图 ≥1 | 是（摄像头） |
| 4. 微信接收端出画 | ☐ | 微信 PC 选虚拟摄像头/采集卡后，**手机端**看到换脸；记 L1/L2/L3 | 手机录屏；未测通不得写「已支持」 | 是 |

## 适配器行为边界（勿误验）

| 现象 | 含义 |
| --- | --- |
| `EngineStatus.RUNNING` | 仅外部进程已拉起 |
| `read_frame()` 返回 `None` | **预期**：帧在 DFL 窗口，壳不拉流 |
| 仅复制了 `.dfm` | 未完成阶段 2，还须在 UI 选模型 |

## 启动命令要点（Codex #5）

- 官方 bat 写死 `--userdata-dir="%~dp0userdata"`  
- **自定义 `userdata_dir` 时**适配器改走 `_internal/python/python.exe` + `main.py` + `--userdata-dir`  
- NVIDIA 识别优先扫 `_internal/CUDA/bin`，目录改名 `DeepFaceLive` 不应误判 unknown

## 相关文档

- 现场单：`docs/DEEPFACELIVE_PRO_RUNBOOK.md`
- 规格：`docs/PRO_DEEPFACELIVE.md`
- 实时验收：`docs/REALTIME_ACCEPTANCE.md`
