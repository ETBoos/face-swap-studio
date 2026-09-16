# 简易模式（FaceFusion）四阶段验收勾选表

> RUNNING ≠ 出画。每阶段必须有证据（截图/日志/录屏）。微信接收仍依赖真机 + `COMPAT_MATRIX`。

| 阶段 | 勾选 | 通过标准 | 证据 |
| --- | --- | --- | --- |
| 1. 外部启动 | ☐ | FaceFusion / Studio 简易引擎进程拉起，无崩溃；CUDA 设备可见（若声明 GPU） | 启动日志 / 任务管理器 |
| 2. 模型或源脸加载 | ☐ | 源脸图片已导入；检测器/换脸模型加载完成；UI 显示就绪而非仅 RUNNING | 素材列表 + 引擎状态文案 |
| 3. 首帧出画 | ☐ | 预览窗出现换脸后首帧；口型/角度可接受（对照 `FACEFUSION_SIMPLE_PRESETS.md`） | 预览截图 ≥1 |
| 4. 微信接收 | ☐ | 微信 PC 选中虚拟摄像头/采集卡后，手机端看到换脸画面（L1→L3） | 手机端录屏；未测通不得写「已支持」 |

## 相关文档

- 预设：`docs/FACEFUSION_SIMPLE_PRESETS.md`
- 实时验收指标：`docs/REALTIME_ACCEPTANCE.md`
- L1：`docs/L1_VIRTUAL_CAM.md`
- L3：`docs/L3_CAPTURE_CARD_BEGINNER.md`
