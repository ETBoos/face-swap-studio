# FaceFusion 参数笔记（历史，不是当前即用引擎）

**产品即用模式已改为 Deep-Live-Cam**（导入脸图）。壳不会启动 FaceFusion。验收与配置见 `docs/DEEPLIVECAM_INSTANT.md` 与 `docs/SIMPLE_ENGINE_FOUR_STAGE.md`。下面的表格只保留作旧调研笔记，不要当成壳的配置键。

# FaceFusion 简易模式 · 最高像真度推荐参数（P0）

真机（Win+NVIDIA）一到即可按此开跑。目标：先出可用样片验像真度，不追求一键安装体验。

## 环境
- GPU：RTX 4080 / 4090（或同级），最新 NVIDIA 驱动
- 安装 FaceFusion（官方/社区当前稳定版），记录根目录到壳 `facefusion_root`
- 优先 CUDA 执行提供者；不要用 CPU 出 P0 样片

## 推荐默认（像真度优先）
| 项 | 建议 | 说明 |
|----|------|------|
| 处理器 / 模型 | `inswapper_128`（若版本支持加 **`pixel_boost` 512，冲极像用 1024**） | 通用身份；非 `.dfm` 专模；boost 更慢更像 |
| 增强 | 默认 **`codeformer`**；与 `gfpgan_1.4` 做 A/B | GFPGAN 易假白/塑料感；嘴/肤质看样片择优 |
| 检测器 | `retinaface` / 默认高精度检测 | 减少错脸；模型名可不硬改 |
| 输出 | **1080p** 先 | 再冲 1440p；4K 不做 P0 |
| 执行 | `cuda` | 失败再查驱动/CUDA |
| 参考脸 | 1–5 张清晰正脸 + 轻侧脸 | 授权素材；拒强美颜 |

## 出片流程（3 分钟简易样片）
1. 准备目标脸图（授权）+ 摄像头或 1080p 素材视频
2. 按上表参数跑 FaceFusion（CLI 或 UI）
3. 导出 ≥3 分钟片段（含说话），交技术调研按 P0 标准打分
4. 壳侧：模式选「简易」，填 `facefusion_root`；真接线前可并列运行 FF

## 明确限制
- 简易模式 **达不到** DeepFaceLive + 专模 `.dfm` 的特定真人上限
- 大侧脸、逆光、重遮挡按验收标准允许掉点，须在样片说明里写清

## 壳对接字段（已有）
- `work_mode=simple` → engine `facefusion`
- `extra.facefusion_root`
- `source_face_paths`

## 出站到微信 PC（L1→L2→L3）
换脸引擎出画后：L1 OBS+MF 虚拟摄像头 → L2 钉版本/驱动 → L3 采集卡环回。详见 PRODUCT_SPEC。微信未测通前为实验支持。
