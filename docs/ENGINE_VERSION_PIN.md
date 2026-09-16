# 引擎版本锁定与 A/B（像真度宣称前必填）

> DeepFaceLive 官方仓库已于 2024-11 归档。生产不得「随便下一个最新镜像」；必须固定构建 + sha256 + 可回滚。

## 1. 锁定表（发布前填实）

| 组件 | 选定版本/构建 | sha256 | 获取来源 | 回滚包路径 |
|------|---------------|--------|----------|------------|
| DeepFaceLive Win **NVIDIA** 构建 | _TBD 真机选定_ | _TBD_ | 官方 Releases / 镜像备份 | `vendor/dfl/<tag>/` |
| FaceFusion | _TBD 锁定 tag_ | _TBD_ | 官方 release | `vendor/ff/<tag>/` |
| inswapper 模型 | 文件名 | _TBD_ | 随 FF | |
| codeformer / gfpgan | 文件名 | _TBD_ | 随 FF | |
| `.dfm` 样例（自有授权） | 文件名 | _TBD_ | 训练导出 | |

适配器检测：除根目录外须覆盖便携包 `_internal/CUDA/bin` 等布局；安装目录改名不得误判 `unknown`（工程项归编程助手2号）。

## 2. A/B 档（同素材、同摄像头、同出站）

| 档 | FaceFusion | 用途 |
|----|------------|------|
| **实时档** | `inswapper_128` + `codeformer` + `pixel_boost=512`（或关 boost） | 微信通话优先低延迟 |
| **画质档** | `inswapper_128` + `codeformer` + `pixel_boost=1024` | 样片比嘴型/身份；可接受更慢 |

**禁止**在未做同素材实测前写死「boost 一定更像」或「已是最高像真度」。对外「最强」仅限：「在 Win 本地实时 + 双模式约束下的最强可落地方案」；绝对画质需附 A/B 表。

## 3. A/B 比较项（技术调研打分）

同 60s 说话片段：嘴型、正脸身份、±30°、遮挡、端到端延迟、主观塑料感。胜出档写入 `COMPAT_MATRIX.md` 后，壳默认参数才许改。
