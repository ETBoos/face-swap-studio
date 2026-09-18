# FaceSwap Studio · 剧组换脸预览工作站

面向影视剧组的 **实时换脸预览工作站（产品壳）**。  
本仓库是 **商业化产品外壳 + 安装脚本 + 引擎适配接口**，默认使用占位引擎；  
**尚未接入 DeepFaceLive / InsightFace 真换脸**。在 GPU 工作站集成成熟开源实时管线之前，请勿对外宣称“已可换脸”。

> **仅限授权影视用途 · AUTHORIZED FILM USE ONLY**

---

## 对外话术（产品定稿）

**正确表述**：「桌面端：虚拟摄像头 / OBS 可用的通话与直播」——本地双模式像真度。

**禁止表述**：「支持全部社交媒体」「原生对接所有 App」。

说明：换脸输出本质是虚拟摄像头/OBS 推流，对方软件把它当普通摄像头。Zoom / Teams / Discord / OBS→Twitch·YouTube 等可选摄像头或推流的桌面场景可覆盖；多数手机端 App 不在本期。虚拟摄像头能力标为 **P2**，真机样片之后再做。

## 产品定位

| 项 | 说明 |
|----|------|
| 名称 | FaceSwap Studio（中文：剧组换脸预览工作站） |
| 用户 | 剧组 / 后期预览岗，使用**已授权**脸部素材 |
| 能力（目标） | 项目管理、授权素材导入、摄像头实时预览、参考帧导出 |
| 引擎策略 | 后期包装成熟开源实时管线（DeepFaceLive / InsightFace），本 MVP **不训练新模型** |
| 合规 | UI 内授权清单、水印开关、本地使用日志桩 |

## 当前实现 vs 桩（stub）

| 模块 | 状态 |
|------|------|
| 项目管理（本地目录 + project.json） | **可用** |
| 授权素材导入 / 授权勾选 / 水印选项 | **可用** |
| 使用日志（JSONL） | **可用（本地桩）** |
| PySide6 中文 GUI | **可用（壳）** |
| 摄像头预览 | **占位**：有摄像头则显示画面+横幅，否则合成 slate |
| DeepFaceLive 适配器 | **已接线**：启动子进程打开 DFL 窗口（见 `engines/deepfacelive.py`）；壳内 `read_frame()` 仍不拉流 |
| 真实人脸交换 | **未实现** |

---

## 硬件要求（目标销售机 / 集成机）

正式接入 DeepFaceLive 后，推荐：

- **GPU**：NVIDIA **RTX 4080 / 4090**（或同级），最新 Studio/Game Ready 驱动
- **系统**：Windows 10/11 x64
- **内存**：32 GB+ 建议
- **存储**：SSD，预留模型与素材空间（≥50 GB）
- **摄像头**：USB / HDMI 采集卡（OpenCV 可打开的设备索引）

本仓库可在无 GPU / Linux 上跑 **产品壳与冒烟测试**；真换脸必须在 Windows + NVIDIA GPU 上完成引擎接入。

---

## Windows 安装步骤

1. 安装 [Python 3.11+](https://www.python.org/downloads/)（勾选 Add to PATH）。
2. 将本项目解压到例如 `C:\FaceSwapStudio\face-swap-studio`。
3. 双击或在 cmd 中运行：

```bat
scripts\setup-win.bat
```

脚本会安装 `uv`（若缺失）并执行 `uv sync`。

4. 启动：

```bat
scripts\start-win.bat
```

或：

```bat
uv run python -m face_swap_studio
```

### 开发者（Linux / macOS 盒上调试壳）

```bash
cd face-swap-studio
uv sync
# 无显示冒烟：
FSS_SMOKE=1 FSS_OFFSCREEN=1 uv run python -m face_swap_studio --offscreen
```

---

## 项目结构（摘要）

```
face-swap-studio/
  pyproject.toml
  README.md
  src/face_swap_studio/
    app.py                 # 入口
    core/                  # 项目、授权清单、使用日志
    engines/
      base.py              # FaceSwapEngine 适配接口
      placeholder.py       # 占位预览引擎（真实可用的壳）
      deepfacelive.py      # DeepFaceLive Pro 适配器（启动官方 NVIDIA 包）
      facefusion_stub.py   # FaceFusion 简易模式（仍为 stub）
    ui/                    # PySide6 中文界面
  scripts/setup-win.bat
  scripts/start-win.bat
  docs/PRODUCT_SPEC.md
```

---

## 向剧组销售时的法律 / 合规提示

1. **仅限授权影视用途**：合同与 UI 均应写明，禁止用于未授权肖像、骚扰、欺诈等。
2. **书面授权**：导入的脸部素材须有演员/权利人授权或剧组合同约定；软件内清单为流程辅助，**不能替代**法律文件。
3. **未成年人**：未经监护人合法授权不得使用未成年人面部素材。
4. **水印与日志**：建议默认开启水印；保留使用记录便于审计。正式成片须另行审片与法务流程。
5. **开源引擎许可**：接入 DeepFaceLive / InsightFace 时，须单独评估其许可证与商业分发条款，必要时提供引擎“自备安装”方案，避免违规再分发。
6. **勿虚假宣传**：在 DeepFaceLive 未于客户 GPU 机集成并验收前，销售材料应写“预览工作站 / 待集成实时引擎”，不要承诺当前版本已具备 SOTA 换脸。

---

## DeepFaceLive 接入（概要）

详见 `src/face_swap_studio/engines/deepfacelive.py` 与 `docs/PRO_DEEPFACELIVE.md`。建议：

- 独立 venv/conda 安装 DFL + CUDA；
- 通过 **子进程 / 共享内存 / 本地 socket** 与 PySide6 进程隔离；
- 实现同一 `FaceSwapEngine` 接口后在设置中切换引擎。

**请勿在本阶段克隆体积庞大的 ML 仓库。**

---

## 版本

- `0.1.0` — 产品壳 MVP：GUI、项目、授权、占位预览、引擎接口与 DFL stub、Windows 脚本与规格说明。
