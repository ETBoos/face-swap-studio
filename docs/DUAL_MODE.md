# 双模式方案（FaceSwap Studio）

用户目标：同一套 Win 软件同时支持——

| 模式 | 名称 | 何时用 | 后端 | 用户操作 |
|------|------|--------|------|----------|
| **简易** | Simple | 无 `.dfm`、要快验像真度 / 简单配置 | **FaceFusion**（或 Rope，默认 FF） | 选目标脸图 → 开摄像头/视频 → 预览 |
| **顶级** | Pro | 已有专模 `.dfm`，要特定真人上限 | **DeepFaceLive** | 导入 `.dfm` → 开摄像头 → 实时预览 |

## 分工
- **编程助手**：壳、模式切换 UI、简易模式（FaceFusion）适配与装机脚本
- **编程助手2号**：顶级模式（DeepFaceLive / `.dfm`）安装、版本匹配、联调
- **技术调研**：采集/验收规格

## 壳侧统一契约
见 `engines/base.py` + `engines/modes.py`：
- `WorkMode.SIMPLE` → FaceFusion 适配器
- `WorkMode.PRO` → DeepFaceLive 适配器（需 `dfm_path`）

## 装机顺序（现场）
1. NVIDIA 驱动（RTX 构建优先）
2. 装 FaceFusion（简易先通）
3. 装 DeepFaceLive NVIDIA 包（与导出 `.dfm` 的 DFL 版本匹配）
4. 装本壳：`scripts/setup-win.bat`
