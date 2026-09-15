# 顶级模式：DeepFaceLive + `.dfm`

归属：**编程助手2号**

## 用户流程
1. 安装 DeepFaceLive **NVIDIA** 构建（RTX 优先；DX12 默认拒绝）
2. 确认 `.dfm` 与导出它的 DeepFaceLab / DeepFaceLive **版本匹配**
3. 在壳中切到「顶级模式」，选择 `.dfm`，配置 `deepfacelive_root`
4. 壳会预检 `.dfm`（大小 + ONNX 指纹），复制到 `<root>/userdata/dfm_models/`，并启动 DeepFaceLive
5. 在 DeepFaceLive 界面打开摄像头，**Face swapper** 选刚导入的模型

## 壳契约（`EngineConfig.extra`）
| 键 | 必填 | 说明 |
|----|------|------|
| `dfm_path` | 是 | 本地 `.dfm` 绝对路径 |
| `deepfacelive_root` | 建议 | 安装目录；也可用 `DEEPFACELIVE_ROOT` |
| `userdata_dir` | 否 | 覆盖默认 `<root>/userdata` |
| `no_cuda` | 否 | `true` 时禁用 CUDA（仅 `main.py` 路径） |
| `require_nvidia` | 否 | 默认 `true`；DX12 构建会可读报错退出 |
| `allow_unknown_build` | 否 | 默认 `false`；无法判定构建时拒绝 |
| `dfm_version_hint` | 否 | 可选版本提示（需出现在文件名或 `.dfm.version` 旁路文件） |

## 装机脚本
```powershell
.\scripts\setup-deepfacelive-win.ps1 -DeepFaceLiveRoot "C:\DeepFaceLive_NVIDIA" -DfmPath "D:\models\person.dfm"
```
DX12 / 未知构建、过小或非 ONNX 指纹的 `.dfm` 会直接中文报错退出。

## 限制
- 预览在 DeepFaceLive 窗口；壳 `read_frame()` 暂不拉帧
- 无 `.dfm` 时请用简易模式（FaceFusion）
