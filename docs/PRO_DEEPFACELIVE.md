# 顶级模式：DeepFaceLive + `.dfm`

归属：**编程助手2号**

## 用户流程
1. 安装 DeepFaceLive **NVIDIA** 构建（RTX 优先；DX12 可跑但更慢）
2. 确认 `.dfm` 与导出它的 DeepFaceLab / DeepFaceLive **版本匹配**
3. 在壳中切到「顶级模式」，选择 `.dfm`，配置 `deepfacelive_root`
4. 壳会把模型复制到 `<root>/userdata/dfm_models/`，并启动 DeepFaceLive
5. 在 DeepFaceLive 界面打开摄像头，**Face swapper** 选刚导入的模型

## 壳契约（`EngineConfig.extra`）
| 键 | 必填 | 说明 |
|----|------|------|
| `dfm_path` | 是 | 本地 `.dfm` 绝对路径 |
| `deepfacelive_root` | 建议 | 安装目录（含 `DeepFaceLive.bat` 或 `main.py`）；也可用环境变量 `DEEPFACELIVE_ROOT` |
| `userdata_dir` | 否 | 覆盖默认 `<root>/userdata` |
| `no_cuda` | 否 | `true` 时禁用 CUDA（仅 `main.py` 启动路径） |

## CLI 事实
官方入口不接受「直接传 dfm 路径」：
```text
python main.py run DeepFaceLive --userdata-dir <PATH> [--no-cuda]
```
模型靠 `userdata/dfm_models` 目录被 UI 发现。

## 装机脚本
```powershell
.\scripts\setup-deepfacelive-win.ps1 -DeepFaceLiveRoot "C:\DeepFaceLive_NVIDIA" -DfmPath "D:\models\person.dfm"
```

## 限制
- 预览在 DeepFaceLive 窗口；壳 `read_frame()` 暂不拉帧
- 无 `.dfm` 时请用简易模式（FaceFusion），不要空跑顶级模式
