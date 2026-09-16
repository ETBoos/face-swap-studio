FaceSwap Studio — Windows preview build

安装版：运行 *-setup.exe。安装仅针对当前用户，不要求管理员权限。
便携版：完整解压 ZIP，然后双击 FaceSwapStudio.exe。不要单独移动 exe。
两种版本均包含 Python 和界面运行库，无需用户安装 Python。

这是用于验证安装、设备检测和操作流程的 alpha 版本。
Windows + NVIDIA 的真实换脸画质、帧率、延迟及通话兼容性需要真机验收。
没有 GPU 时仍应能启动界面并查看检测结果；这不表示 CPU 已能实时换脸。

本包不包含 FaceFusion、DeepFaceLive、换脸模型或 CUDA 工具包。
实际换脸需要另行配置已审查授权的引擎/模型；输出需要受支持的摄像头驱动。
components\FaceSwapStudio-Camera-Setup.exe 是独立可选的虚拟摄像头安装程序。
需要输出时主动运行它并允许管理员安装；主程序安装过程不会自动注册摄像头。
组件提供 DirectShow 设备，未承诺微信、WhatsApp 等所有接收应用兼容。
软件不能自动让手机端应用接受虚拟摄像头。

卸载安装版只移除安装的程序和快捷方式，保留用户项目、设置及日志。
已安装的摄像头组件可在 Windows“应用”中单独卸载，不随主程序卸载。
便携版的“便携”是免安装启动，用户数据仍保存到用户目录，不随 ZIP 搬移。
首次启动异常可查 %LOCALAPPDATA%\FaceSwapStudio\logs\startup.log。
第三方运行库版本和许可文件见 THIRD-PARTY-NOTICES\。

此测试包未使用代码签名证书。发布者签名、模型许可及真实设备验收完成前，
不要将其描述为已正式验收的商业成品。
