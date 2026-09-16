# DeepFaceLive + `.dfm` 现场启动检查单（P0）

归属：**编程助手2号**  
用途：Win+NVIDIA 一到，按本单拧顶级样片；@技术调研 按 P0 像真度打分。

## 0. 机器前提
- [ ] Windows + **NVIDIA** 驱动正常（建议 RTX 4090；其他 RTX 也可，注明型号）
- [ ] DeepFaceLive 为 **NVIDIA 构建**（非 DX12）；路径写入 `DEEPFACELIVE_ROOT`
- [ ] 专模 `.dfm` 已用**同代** DeepFaceLab 导出，与本机 DFL 版本匹配
- [ ] 壳已切 **顶级 / Pro**，授权允许 dfm

## 1. 一键预检（装机脚本）
```powershell
.\scripts\setup-deepfacelive-win.ps1 `
  -DeepFaceLiveRoot "$env:DEEPFACELIVE_ROOT" `
  -DfmPath "D:\models\target.dfm"
```
期望：
- 构建检测 = `nvidia`
- `.dfm` 预检通过（不过小、有 ONNX 指纹）
- 模型已复制到 `<root>\userdata\dfm_models\`

失败即停：把**完整中文报错**贴群，不要强行开 DX12。

## 2. 壳启动（或 bat）
- [ ] 壳：`dfm_path` + `deepfacelive_root` → 引擎 READY → Start
- [ ] 或：`cd $env:DEEPFACELIVE_ROOT; .\DeepFaceLive.bat`
- [ ] DFL 内打开摄像头；**Face swapper (DFM)** 选刚 staged 的模型名
- [ ] Face detector / merger 设备选 **GPU**

## 3. 样片采集（交给验收）
| 项 | 要求 | 记录 |
|----|------|------|
| 时长 | ≥ **60s** 连续说话特写 + 另存一段 ≥ **3–5 min** 连拍 | 文件名/路径 |
| 分辨率 | 优先 **1080p** 预览 | 实际分辨率 |
| 正脸 | 静帧可认本人 | 主观 /10 |
| ±30° | 左右转头 | 主观 /10 |
| 嘴型 | 60s 无明显糊牙、唇错位、齿乱闪 | 通过/不通过 |
| 遮挡 | 手挡脸 / 麦挡脸 → 冻结或降级，**不乱成路人脸** | 通过/不通过 |
| 身份 | 5 min 不「漂成路人」 | 通过/不通过 |

样片命名建议：`pro_dfm_<subject>_<gpu>_<YYYYMMDD>.mp4`

## 4. P1 稳定观察（同场可记）
- [ ] 1080p 是否跟得上嘴型（主观卡顿：无/偶发/严重）
- [ ] 连续 **30 min** 是否崩溃、黑屏、进程退出
- [ ] 任务管理器：GPU 显存是否持续爬升不回落（泄漏嫌疑）
- [ ] 进程退出码非 0 → 记下 code + 最后操作

## 5. 交付清单（丢群）
1. 样片视频（至少 60s 说话 + 一段 5 min）
2. 本单勾选结果（可截图或填表）
3. 机器：GPU 型号、驱动、DFL 构建路径、`.dfm` 文件名与来源版本说明
4. 若失败：预检/运行中文报错原文

## 6. 明确不做（本单范围外）
- 虚拟摄像头、一键安装包打磨（P2）
- 无 `.dfm` 的空跑「顶级」演示（请走简易 FaceFusion）

## 出站到微信 PC（L1→L2→L3）
换脸引擎出画后：L1 OBS+MF 虚拟摄像头 → L2 钉版本/驱动 → L3 采集卡环回。详见 PRODUCT_SPEC。微信未测通前为实验支持。
