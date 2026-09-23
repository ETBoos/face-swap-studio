; Compile with /DAppVersion /DBundleDir /DArtifactsDir from build-windows.ps1.
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef BundleDir
  #error BundleDir is required
#endif
#ifndef ArtifactsDir
  #error ArtifactsDir is required
#endif

[Setup]
AppId={{E79E9B04-BFC1-41CB-9609-D15B02BA68AE}
AppName=FaceSwap Studio
AppVersion={#AppVersion}
AppPublisher=FaceSwap Studio
AppVerName=FaceSwap Studio {#AppVersion}
DefaultDirName={localappdata}\Programs\FaceSwap Studio
DefaultGroupName=FaceSwap Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#ArtifactsDir}
OutputBaseFilename=FaceSwapStudio-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\FaceSwapStudio.exe
CloseApplications=yes
CloseApplicationsFilter=FaceSwapStudio.exe
RestartApplications=no
SetupLogging=yes
ShowLanguageDialog=no
LanguageDetectionMethod=none

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FaceSwap Studio"; Filename: "{app}\FaceSwapStudio.exe"; WorkingDir: "{app}"
Name: "{group}\安装配置教学"; Filename: "{sys}\notepad.exe"; Parameters: """{app}\安装配置教学.md"""
Name: "{group}\卸载 FaceSwap Studio"; Filename: "{uninstallexe}"
Name: "{group}\安装虚拟摄像头组件（需要管理员权限）"; Filename: "{app}\components\FaceSwapStudio-Camera-Setup.exe"
Name: "{autodesktop}\FaceSwap Studio"; Filename: "{app}\FaceSwapStudio.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\FaceSwapStudio.exe"; Description: "启动 FaceSwap Studio"; Flags: nowait postinstall skipifsilent

; Deliberately no [UninstallDelete]: user projects, settings, logs and models
; live outside the application directory and must survive uninstall/reinstall.
