# L1 · Media Foundation 虚拟摄像头（微信/WhatsApp 出站）

## 安装（易错点）

必须安装 **两样**（缺一不可）：

1. **DroidCam Virtual Camera 驱动**（系统里出现 `DroidCam Video` 等摄像头设备）
2. **OBS 插件：DroidCam Virtual Output**（Tools → DroidCam Virtual Output → Activate）

**不要**只装「DroidCam 手机摄像头输入 / Source」类插件——那是把手机当输入，不是给微信出站用的输出虚拟摄像头。

参考：https://github.com/dev47apps/droidcam-obs-virtual-output

## 推荐接线

物理摄像头 → Deep-Live-Cam（即用）或 DeepFaceLive（专模）→ OBS 场景（窗口/游戏采集预览）→ **DroidCam Virtual Output 激活** → 微信/WhatsApp 选 `DroidCam Video`（以设备管理器实名为准）

OBS 画布分辨率/FPS 与通话软件所选档位一致（常见 1280×720 或 1920×1080 @30）。

## 禁止当作唯一方案

OBS 自带 **DirectShow VirtualCam** 对腾讯系经常枚举不到；L1 默认以 MF/DroidCam 为准，失败再 L2/L3。

## 验收记录模板

| 项 | 填写 |
|----|------|
| Windows | |
| OBS | |
| DroidCam 驱动版本 | |
| OBS 输出插件版本 | |
| 微信/WhatsApp 版本 | |
| 系统设备名 | |
| 通话软件内显示名 | |
| 测试画面出站 | 通过/失败 |
| 换脸出站 | 通过/失败 |
