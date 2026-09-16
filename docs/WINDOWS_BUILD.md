# Windows 可安装测试版的构建与验证

此流程生成 FaceSwap Studio `0.2.0a1` 的 Windows x64 预览安装包与免安装压缩包。
安装包包含 Python、Qt 和应用运行库，最终用户无需预先安装 Python。
它不包含 FaceFusion、DeepFaceLive、换脸模型或 CUDA 工具包。

## 产物

`dist/artifacts/`：

- `FaceSwapStudio-<版本>-windows-x64-setup.exe`：当前用户安装，无需管理员；提供开始菜单、可选桌面快捷方式和卸载入口。
- `FaceSwapStudio-<版本>-windows-x64-portable.zip`：完整解压后运行 `FaceSwapStudio.exe`；不能只拷贝 exe。
- `FaceSwapStudio-Camera-Setup.exe`：独立可选摄像头组件，需要管理员；提供 x64 和 x86 的 FaceSwap Studio Camera DirectShow 设备。
- `build-info.json`：源代码提交、构建时间、Python/PyInstaller 和运行库版本。
- `SHA256SUMS.txt`：以上文件的 SHA256 校验值。

主程序安装过程不会自动注册摄像头。需要输出时，从开始菜单选择“Install FaceSwap Studio Camera (administrator)”，或运行程序目录 `components/` 中的组件安装程序。
主程序卸载保留用户项目、设置、日志，也保留独立摄像头组件。后者可在 Windows“应用”中单独卸载。
便携版使用相同的用户数据目录，“便携”仅指免安装启动。

## 自动构建

`.github/workflows/windows-package.yml` 在推送到 `main`、`master`、`codex/**`，以及拉取请求和手动运行时触发。纯 Markdown 更新不触发 push/PR 构建。
流程仅上传 Actions artifacts，不创建 Release、不推送代码、不发布网站。

流水线使用 Windows Server 2022 runner、64 位 Python 3.11、锁定依赖的 `uv sync --frozen`。
PyInstaller 固定为 6.22.3；Inno Setup 固定为 7.1.0，并验证官方发布的 SHA256。
Actions 固定到已核验的提交。升级工具时应同时更新对应版本、摘要和文档。

执行顺序：

1. 安装应用、测试和构建依赖。
2. 无 GPU/offscreen 运行测试，输出 JUnit 报告。
3. 用 Visual Studio C++ v143 编译独立摄像头组件的 x64/x86 DLL。
4. 打包摄像头安装器与应用；收集运行库许可文件和构建信息。
5. 在无 GPU 的 runner 上从另一个工作目录启动冻结后的 GUI，验证正常退出；记录启动日志。
6. 安装主程序，验证已安装 GUI、快捷方式、卸载，以及外部用户数据保留。
7. 安装/卸载摄像头组件，回读两种注册表视图中的独立 CLSID；在 45 秒超时保护下，将自生成色场送入摄像头并用接收端检查实际像素。
8. 仅在测试成功后上传可下载安装包；失败时上传诊断报告。

在 Actions 对应运行页面下载 `FaceSwapStudio-windows-x64-<运行号>`；诊断附件包含测试、打包警告、安装和卸载日志。
默认保留 14 天，因此 Actions artifact 不是永久下载站。

## 本地 Windows 开发机

开发机需要 Git、64 位 Python 3.11、uv、Visual Studio 2022 Build Tools 的 C++ 桌面组件和 Windows SDK，以及 Inno Setup。
这些是构建机依赖，最终用户不需要安装。

```powershell
uv sync --frozen --python 3.11 --extra dev --extra build
.\scripts\build-windows.ps1 -InnoSetupCompiler "C:\Program Files\Inno Setup 7\ISCC.exe"
```

构建脚本可以自动发现 PATH 或常用位置中的 ISCC；如路径不同，显式传入。
修改依赖后先运行 `uv lock` 并提交 `uv.lock`，不要让流水线临时升级依赖。
构建脚本使用一目录模式，便于独立 DLL、问题排查和卸载；关闭 UPX。

安装/卸载测试应在干净 Windows 虚拟机运行：测试会安装真实程序和摄像头组件。脚本在发现已安装的本产品时拒绝覆盖。
摄像头测试需要管理员权限。它不会修改 OBS、UnityCapture 的设备注册项。

```powershell
.\scripts\test-windows-installer.ps1 -Installer ".\dist\artifacts\FaceSwapStudio-0.2.0a1-windows-x64-setup.exe"
.\scripts\test-windows-camera-installer.ps1 -Installer ".\dist\artifacts\FaceSwapStudio-Camera-Setup.exe" -FrameTestScript "scripts/smoke_virtual_camera.py"
```

## 验证范围与交付口径

Windows CI 成功可以证明依赖可以安装、源码测试通过、应用能够打包和启动、安装卸载完成，以及已执行的摄像头检查。
不能据此宣布 NVIDIA 推理已通过、画质达标、低延迟、微信/WhatsApp 已兼容。
这些需要 Windows + NVIDIA + 真实接收应用的单独验收。

摄像头组件属于 DirectShow 用户态组件，不是内核驱动。接收软件仍可能不支持该设备。
此预览版没有发布者代码签名证书，安装时 Windows 可能显示未知发布者。
发布前需要处理代码签名、第三方运行库分发义务、引擎/模型商业授权和真实硬件验收。

运行库许可文件位于 `THIRD-PARTY-NOTICES/`。自动收集清单用于检查，不等同于完整法律审查。
摄像头 MIT 许可与修改说明随独立组件安装；源码在 `native/virtual_camera/`。

官方参考：

- [PyInstaller spec 文件与一目录打包](https://pyinstaller.org/en/stable/spec-files.html)
- [PyInstaller 平台与运行时要求](https://pyinstaller.org/en/stable/requirements.html)
- [Inno Setup 当前用户安装权限](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
- [Inno Setup 文件注册与卸载](https://jrsoftware.org/ishelp/topic_filessection.htm)
- [GitHub Actions 构建产物](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- [UnityCapture 上游](https://github.com/schellingb/UnityCapture)
