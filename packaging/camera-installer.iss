#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef NativeDir
  #error NativeDir is required
#endif
#ifndef ArtifactsDir
  #error ArtifactsDir is required
#endif

[Setup]
AppId={{DCE5F63E-F877-49F4-AF12-BB23098A4752}
AppName=FaceSwap Studio Camera
AppVersion={#AppVersion}
AppPublisher=FaceSwap Studio
DefaultDirName={autopf64}\FaceSwap Studio Camera
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#ArtifactsDir}
OutputBaseFilename=FaceSwapStudio-Camera-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
RestartApplications=no
InfoBeforeFile=camera-readme.txt
SetupLogging=yes

[Files]
Source: "{#NativeDir}\x64\FaceSwapStudioCamera64.dll"; DestDir: "{app}"; Flags: regserver 64bit uninsrestartdelete
Source: "{#NativeDir}\Win32\FaceSwapStudioCamera32.dll"; DestDir: "{app}"; Flags: regserver 32bit uninsrestartdelete
Source: "..\native\virtual_camera\LICENSE.txt"; DestDir: "{app}"
Source: "..\native\virtual_camera\UPSTREAM.md"; DestDir: "{app}"
Source: "camera-readme.txt"; DestDir: "{app}"

; regserver unregisters only these two DLLs on uninstall. The native source
; further limits unregistration to the component's exact service/property CLSIDs.
