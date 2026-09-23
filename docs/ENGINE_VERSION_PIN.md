# 引擎版本锁定与 A/B（像真度宣称前必填）

> DeepFaceLive 官方仓库已于 2024-11 归档。生产不得「随便下一个最新镜像」；必须固定构建 + sha256 + 可回滚。

## 1. 锁定表（发布前填实）

| 组件 | 选定版本/构建 | sha256 | 获取来源 | 回滚包路径 |
|------|---------------|--------|----------|------------|
| DeepFaceLive Win **NVIDIA** 构建 | _TBD 真机选定_ | _TBD_ | 官方 Releases / 镜像备份 | `vendor/dfl/<tag>/` |
| Deep-Live-Cam（即用） | _TBD 锁定 commit_ | _TBD_ | https://github.com/hacksider/Deep-Live-Cam `run.py` | 客户机目录，不随壳克隆 |
| FaceFusion | 不再接入即用 | — | 历史笔记 `FACEFUSION_SIMPLE_PRESETS.md` | — |
| inswapper_128 / fp16（DLC 即用） | 文件名 | _TBD_ | DLC `models/`，首次可由上游下载 | |
| codeformer / gfpgan | 文件名 | _TBD_ | 历史 FF 笔记；DLC 增强器是 `face_enhancer*` | |
| `.dfm` 样例（自有授权） | 文件名 | _TBD_ | 训练导出 | |

适配器检测：除根目录外须覆盖便携包 `_internal/CUDA/bin` 等布局；安装目录改名不得误判 `unknown`（工程项归编程助手2号）。

## 2. A/B 档（同素材、同摄像头、同出站）

| 档 | 说明 | 用途 |
|----|------------|------|
| **实时档** | 历史 FF 笔记：`inswapper_128` + `codeformer` + `pixel_boost=512`。壳的即用默认只传 DLC `--frame-processor face_swapper`，不传 pixel_boost | 微信通话优先低延迟 |
| **画质档** | 历史 FF 笔记：`pixel_boost=1024`。即用要增强时才把 `face_enhancer` 加进 `frame_processors` | 样片比嘴型/身份；可接受更慢 |

**禁止**在未做同素材实测前写死「boost 一定更像」或「已是最高像真度」。对外「最强」仅限：「在 Win 本地实时 + 双模式约束下的最强可落地方案」；绝对画质需附 A/B 表。

## 3. A/B 比较项（技术调研打分）

同 60s 说话片段：嘴型、正脸身份、±30°、遮挡、端到端延迟、主观塑料感。胜出档写入 `COMPAT_MATRIX.md` 后，壳默认参数才许改。
