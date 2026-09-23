# FaceSwap Studio 安装与配置教学

适用版本：FaceSwap Studio `0.2.0a1`，Windows 10/11 x64。

这份教学分成两条路线：

- **先看界面**：只安装 FaceSwap Studio，使用“设备测试（不换脸）”检查摄像头和操作流程。
- **完成真实换脸**：额外安装官方 FaceFusion `3.9.0`、运行环境和模型，再安装虚拟摄像头组件。

FaceSwap Studio 安装包已经包含桌面界面和 Python 运行库，但**不包含 FaceFusion、CUDA、换脸模型或专属人物模型**。只安装主程序不能产生真实换脸画面。

> 证据状态：除特别标注外，本页基于当前源码、Windows 构建产物和 FaceFusion 3.9.0 官方安装入口确认。真实 NVIDIA 性能和各通话软件兼容性仍待真机验收。

## 一、安装前准备

建议准备：

- Windows 10 1809 或更新版本，64 位系统。
- 一台可被 Windows 识别的摄像头。
- NVIDIA 显卡。CPU 可以用于排错，但通常不适合实时换脸。
- 稳定网络。FaceFusion 环境和模型需要另外下载。
- Windows 管理员权限，仅安装虚拟摄像头时需要。
- 已获得授权的形象照片和模型素材。

交付目录中应有这些文件：

| 文件 | 用途 |
| --- | --- |
| `FaceSwapStudio-0.2.0a1-windows-x64-setup.exe` | 主程序安装版，推荐普通用户使用 |
| `FaceSwapStudio-0.2.0a1-windows-x64-portable.zip` | 免安装便携版，必须完整解压 |
| `FaceSwapStudio-Camera-Setup.exe` | 独立虚拟摄像头组件，需要管理员权限 |
| `SHA256SUMS.txt` | 检查下载文件是否完整 |
| `build-info.json` | 构建版本与验证范围 |

### 可选：检查安装包是否完整

在交付目录空白处按住 `Shift` 并单击鼠标右键，选择“在终端中打开”，执行：

```powershell
Get-FileHash .\FaceSwapStudio-0.2.0a1-windows-x64-setup.exe -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

第一条命令显示的哈希值应与 `SHA256SUMS.txt` 中同名文件的值一致。当前测试包没有代码签名证书；Windows 可能显示发布者未知。只有在文件来自本项目交付目录并且哈希一致时才继续。

## 二、安装 FaceSwap Studio

### 推荐：安装版

1. 双击 `FaceSwapStudio-0.2.0a1-windows-x64-setup.exe`。
2. 按安装向导继续。主程序按当前 Windows 用户安装，不需要管理员权限。
3. 可选勾选“创建桌面快捷方式”。
4. 安装完成后启动 **FaceSwap Studio**。

默认程序目录为：

```text
%LOCALAPPDATA%\Programs\FaceSwap Studio
```

用户设置、项目和日志保存在：

```text
%USERPROFILE%\FaceSwapStudio
```

卸载或升级主程序会保留这个用户目录。

### 便携版

1. 将 `FaceSwapStudio-0.2.0a1-windows-x64-portable.zip` 完整解压到普通文件夹。
2. 打开解压后的 `FaceSwapStudio` 文件夹。
3. 双击 `FaceSwapStudio.exe`。

不要只把 `FaceSwapStudio.exe` 单独复制出来。它需要同目录中的运行库、授权配置和组件文件。

## 三、先用设备测试确认主程序

在安装 FaceFusion 之前，先确认主程序和摄像头可以工作：

1. 启动 FaceSwap Studio。
2. 在“1 选择摄像头”中点击 **查找设备（不会开启摄像头）**。
3. 选择真实摄像头。不要把 `FaceSwap Studio Camera` 选作输入。
4. 在“2 选择照片或专属模型”中选择 **设备测试（不换脸）**。
5. 点击 **开始预览**。

能看到真实摄像头画面，说明主程序和输入设备路径基本正常。设备测试不会换脸，也不能开始虚拟摄像头输出。

## 四、安装 FaceFusion 3.9.0

FaceSwap Studio 当前只接受官方 FaceFusion `3.9.0`。其他版本会被拒绝，避免内部接口变化造成错误输出。

以下命令来自 FaceFusion 官方安装方式，并按本项目固定版本调整。官方入口：

- [FaceFusion 3.9.0 发布页](https://github.com/facefusion/facefusion/releases/tag/3.9.0)
- [FaceFusion Windows 平台准备](https://docs.facefusion.io/installation/platform/windows)
- [FaceFusion Windows 加速器准备](https://docs.facefusion.io/installation/accelerator/windows)

### 1. 安装 Git、Miniconda 和 FFmpeg

用普通权限打开 **PowerShell**，逐条执行：

```powershell
winget install -e --id Git.Git
winget install -e --id Anaconda.Miniconda3 --version py312_25.1.1-2 --override "/AddToPath=1"
winget install -e --id Gyan.FFmpeg --version 7.0.2
```

安装结束后关闭 PowerShell，再打开一个新的 PowerShell。

如果 `winget` 提示指定版本不可用，请先查看 FaceFusion 官方 Windows 安装页中的当前命令，不要随意混用其他 Python 或 CUDA 教程。

### 2. 创建 FaceFusion 专用环境

```powershell
conda init --all
```

执行后关闭 PowerShell，再打开一个新的 PowerShell，然后执行：

```powershell
conda create --name facefusion python=3.12 pip=25.0 -y
conda activate facefusion
```

命令行左侧出现 `(facefusion)` 才表示环境已启用。

### 3. 下载固定版本源码

```powershell
git clone --branch 3.9.0 --single-branch https://github.com/facefusion/facefusion.git C:\facefusion
cd C:\facefusion
```

如果 `C:\facefusion` 已存在，不要直接覆盖。先确认其中是否是完整的官方 `3.9.0` 目录。

### 4. 配置 NVIDIA CUDA 环境

在仍显示 `(facefusion)` 的 PowerShell 中执行：

```powershell
conda install nvidia/label/cuda-12.9.1::cuda-runtime nvidia/label/cudnn-9.10.0::cudnn -y
python install.py cuda@12
```

FaceFusion `3.9.0` 的安装器使用位置参数 `cuda@12`。不要使用旧教程中的 `--onnxruntime cuda`。

如果没有 NVIDIA 显卡，只为排错时可以安装 CPU 版本：

```powershell
python install.py default
```

CPU 模式不代表能达到实时换脸速度。

### 5. 重新加载环境并确认版本

```powershell
conda deactivate
conda activate facefusion
cd C:\facefusion
python facefusion.py --version
```

输出必须包含：

```text
FaceFusion 3.9.0
```

### 6. 下载并准备模型

FaceSwap Studio 在运行换脸时禁止自动下载模型，因此先在官方 FaceFusion 环境中完成下载：

```powershell
python facefusion.py force-download
```

等待命令完整结束。当前适配器会检查所选换脸模型及人脸检测、关键点、识别、遮罩和内容检查所需的模型文件与 `.hash` 文件。

默认使用 `inswapper_128`。也可在 FaceSwap Studio 中选择 `inswapper_128_fp16`。其他换脸模型暂不在当前适配范围内。

### 7. 记录 FaceFusion Python 路径

保持 `(facefusion)` 环境启用，执行：

```powershell
where.exe python
```

记录属于 `facefusion` 环境的 `python.exe`，通常类似：

```text
C:\Users\你的用户名\miniconda3\envs\facefusion\python.exe
```

不要选择 FaceSwap Studio 安装目录里的 Python，也不要选择 Windows Store 的 Python。

### 8. 可选：确认 CUDA 执行器

```powershell
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

NVIDIA 配置成功时，结果中应包含：

```text
CUDAExecutionProvider
```

## 五、在 FaceSwap Studio 中填写引擎配置

启动 FaceSwap Studio，点击 **画面与引擎设置…**，建议先按下表填写：

| 界面字段 | 推荐值 | 说明 |
| --- | --- | --- |
| 预览尺寸 | `1280 × 720` | 首次测试先保证稳定，之后再试 `1920 × 1080` |
| 设备号 | 保持查找设备后的值 | 名称不匹配时再调整 |
| GPU 设备（高级） | `cuda:0` | 第一张 NVIDIA 显卡；多卡机器可尝试 `cuda:1` |
| FaceFusion 安装目录 | `C:\facefusion` | 目录中必须有 `facefusion.py` |
| FaceFusion Python | 第四部分记录的 `python.exe` | 必须属于 `facefusion` Conda 环境 |
| 已准备的照片模型 | `inswapper_128` | 也支持 `inswapper_128_fp16` |
| 照片模型计算设备 | NVIDIA GPU（CUDA） | CPU 仅用于排错 |
| 首帧等待上限 | `180 秒` | 首次加载模型可能较慢；稳定后可缩短 |

点击 **确定** 保存。再次开始预览后新设置才会生效。

## 六、激活产品密钥

1. 点击窗口右上角 **激活 / 授权**。
2. 在“产品密钥”中输入销售方提供的 `FSS-XXXX-XXXX-XXXX-XXXX`。
3. 点击 **联网激活**。
4. 状态显示套餐、密钥尾号和设备额度后关闭窗口。

授权规则：

- 未激活：可以查看带标记的本机预览，不能开始虚拟输出。
- Starter：可使用照片换脸和虚拟输出，保留品牌标记。
- Pro / Studio：可去除预览标记，并开放专业人物模型入口。
- 在线激活后默认可离线使用 7 天；长期离线前应点击 **刷新授权**。

“清除此电脑的授权”只删除本机凭证，不会释放服务器上的设备额度。换电脑前需要销售方在后台解绑旧设备。

## 七、开始真实换脸预览

1. 点击 **查找设备（不会开启摄像头）**，选择真实摄像头。
2. 模式选择 **照片模式**。
3. 点击 **选择照片…**，选择 1 至 8 张同一个人的清晰照片。
4. 勾选 **我拥有这些素材，或已获得使用许可**。
5. 点击 **开始预览**。

推荐照片条件：

- 每张图只有一张清晰人脸。
- 优先正脸和轻微侧脸，避免强美颜、重遮挡、低分辨率。
- 多张照片必须是同一个人。
- 使用者拥有照片和人物形象的使用许可。

正常状态依次为“正在准备引擎”“等待换脸首帧”“本机换脸预览已就绪”。只有收到真实换脸帧后，软件才允许开始输出。

实时摄像头中没有脸、出现多人、人脸被严重遮挡或引擎中断时，软件会显示安全占位并暂停输出，不会自动把原始摄像头画面送出去。

## 八、安装虚拟摄像头

完成本机真实换脸预览后再安装输出组件：

1. 关闭正在使用摄像头的 OBS、会议和直播软件。
2. 在 FaceSwap Studio 中点击 **准备虚拟摄像头…**；也可以直接运行 `FaceSwapStudio-Camera-Setup.exe`。
3. Windows 显示管理员权限提示时，确认安装的是 **FaceSwap Studio Camera**。
4. 完成安装后重新启动目标通话或直播软件，使它重新扫描摄像头设备。

虚拟摄像头组件与主程序分开安装。卸载主程序不会卸载摄像头组件；可在“Windows 设置 → 应用”中单独卸载 **FaceSwap Studio Camera**。

## 九、输出到 OBS、直播或通话软件

1. 在 FaceSwap Studio 中确认状态为 **本机换脸预览已就绪**。
2. 点击 **开始输出**。
3. 等到界面提示发送端已就绪。
4. 打开或重新启动目标软件。
5. 在目标软件的摄像头列表中选择 **FaceSwap Studio Camera**。
6. 检查接收画面是否持续更新，再进行正式通话或直播。

### OBS 示例

1. 在“来源”区域点击 `+`。
2. 选择“视频采集设备”。
3. 新建来源，例如命名为“FaceSwap Studio”。
4. 设备选择 **FaceSwap Studio Camera**。
5. 分辨率先保持设备默认值；确认稳定后再调整场景尺寸。

FaceSwap Studio Camera 只提供视频。麦克风仍需在 OBS 或通话软件中选择原来的真实麦克风。

当前虚拟摄像头基于 DirectShow。某个软件能看到设备不等于其视频通话链路已经通过兼容性验收；微信、WhatsApp、Zoom、Teams 等都应以具体版本和实际接收端画面为准。手机端应用不能直接选择这台 Windows 虚拟摄像头。

## 十、常见问题

### 主程序无法启动

打开日志目录：

```text
%USERPROFILE%\FaceSwapStudio\logs
```

优先查看 `startup.log`。也可以在主界面点击 **打开诊断日志文件夹**。

### 查找不到真实摄像头

1. 在 Windows“设置 → 隐私和安全性 → 相机”中允许桌面应用访问相机。
2. 关闭可能独占摄像头的浏览器、会议或直播软件。
3. 重新插拔 USB 摄像头，再点击“查找设备”。
4. 不要选择 `FaceSwap Studio Camera` 作为输入。

### 提示找不到 FaceFusion

“FaceFusion 安装目录”必须指向包含以下文件的根目录：

```text
C:\facefusion\facefusion.py
C:\facefusion\facefusion\metadata.py
```

不要选择 `facefusion` 子目录本身。

### 提示 FaceFusion 版本不受支持

在 FaceFusion PowerShell 中执行：

```powershell
cd C:\facefusion
git status
git describe --tags --always
python facefusion.py --version
```

本版必须显示 `3.9.0`。

### 提示找不到 FaceFusion Python

```powershell
conda activate facefusion
where.exe python
```

将属于 `envs\facefusion` 的完整 `python.exe` 路径填入设置。

### 提示缺少模型或 `.hash` 文件

```powershell
conda activate facefusion
cd C:\facefusion
python facefusion.py force-download
```

下载完成后停止并重新开始 FaceSwap Studio 预览。本程序不会代替 FaceFusion 下载模型，也不会忽略损坏的校验文件。

### 提示没有 CUDA 执行器

先检查：

```powershell
conda activate facefusion
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

如果没有 `CUDAExecutionProvider`，在 `C:\facefusion` 中重新执行：

```powershell
python install.py cuda@12 --force-reinstall
```

同时确认 NVIDIA 驱动正常，再重新打开 FaceSwap Studio。

### 一直停在等待首帧

- 画面中保持一张清晰人脸。
- 暂时移开其他人，减少遮挡和逆光。
- 确认源照片中每张图也只有一张脸。
- 将首帧等待上限调到 `180` 或 `300` 秒。
- 查看 `%USERPROFILE%\FaceSwapStudio\logs` 中的具体错误。

### “开始输出”不可用

同时检查：

- 产品授权仍然有效。
- 当前是照片模式的真实换脸预览，设备测试画面不能输出。
- 界面已经显示“本机换脸预览已就绪”。
- 虚拟摄像头组件已经安装。

### 目标软件看不到 FaceSwap Studio Camera

1. 关闭目标软件。
2. 重新运行 `FaceSwapStudio-Camera-Setup.exe`。
3. 安装成功后重新打开目标软件。
4. 检查目标软件是否支持 Windows DirectShow 摄像头。
5. 仍然看不到时重启 Windows，再检查设备列表。

组件同时注册 64 位和 32 位 DirectShow 设备，但具体应用是否接受仍需要实测。

### 画面卡顿或延迟高

1. 先用 `1280 × 720`。
2. 计算设备选择 NVIDIA GPU（CUDA）。
3. 关闭占用显卡的视频编辑、游戏或其他推理程序。
4. 先用 `inswapper_128`，确认稳定后再测试其他设置。
5. 记录显卡、驱动、实际 FPS 和延迟；当前版本没有承诺所有硬件都达到实时标准。

## 十一、卸载

### 卸载主程序

打开“Windows 设置 → 应用 → 已安装的应用”，卸载 **FaceSwap Studio**。

用户项目、设置和日志会保留在 `%USERPROFILE%\FaceSwapStudio`。

### 卸载虚拟摄像头

先关闭 OBS 和通话软件，再在“已安装的应用”中卸载 **FaceSwap Studio Camera**。

### 卸载 FaceFusion 环境

确认不再需要模型和环境后，可在 PowerShell 中执行：

```powershell
conda env remove --name facefusion
```

源码和模型仍在 `C:\facefusion`。是否保留或删除应由使用者根据模型许可、备份和后续升级需要自行决定。

## 十二、首次成功检查表

- [ ] 主程序能正常打开。
- [ ] 能找到并预览真实摄像头。
- [ ] FaceFusion 显示版本 `3.9.0`。
- [ ] `CUDAExecutionProvider` 可用。
- [ ] FaceFusion 模型和 `.hash` 文件准备完整。
- [ ] FaceSwap Studio 已填写正确的 FaceFusion 根目录与 Python。
- [ ] 使用授权照片并勾选素材许可确认。
- [ ] 本机显示真实换脸预览，而不是设备测试画面或安全占位。
- [ ] 产品密钥已激活。
- [ ] FaceSwap Studio Camera 已安装。
- [ ] 目标软件能选择虚拟摄像头并收到持续更新的画面。
- [ ] 麦克风在目标软件中单独工作。
- [ ] 完成至少一次真实接收端检查，再决定是否用于正式直播或通话。

