# 双模式方案（FaceSwap Studio）

用户目标：同一套 Win 软件同时支持——

| 模式 | 名称 | 何时用 | 后端 | 用户操作 |
|------|------|--------|------|----------|
| **即用** | Simple | 无 `.dfm`，导入一张脸图就要预览 | **Deep-Live-Cam** | 选源脸 → 首帧进预览窗，或打开 DLC Live 窗口 |
| **专模** | Pro | 已有专模 `.dfm` | **DeepFaceLive** | 导入 `.dfm` → 开摄像头 → DFL 窗口实时预览 |

## 分工
- **即用**：壳、模式切换、Deep-Live-Cam 适配（`engines/deeplivecam.py`）。不实现换脸算法
- **专模**：DeepFaceLive / `.dfm` 适配保持原样（另一条工作流）
- **技术调研**：采集/验收规格

## 壳侧统一契约
见 `engines/base.py` + `engines/modes.py`：
- `WorkMode.SIMPLE` → `deeplivecam`（Deep-Live-Cam，需要源脸图）
- `WorkMode.PRO` → `deepfacelive`（需要 `dfm_path`）

查找、启动命令和配置键：`docs/DEEPLIVECAM_INSTANT.md`。

## 装机顺序（现场）
1. NVIDIA 驱动（RTX 构建优先）
2. 即用：双击 `scripts/setup-all-win.bat`（检测或安装 `%USERPROFILE%/Deep-Live-Cam`，自动写入 `deeplivecam_root`，桌面「打开换脸」）。不必手填路径
3. 装 DeepFaceLive NVIDIA 包（与导出 `.dfm` 的 DFL 版本匹配）
4. 装本壳：`scripts/setup-win.bat`
