; RecordType 安装脚本 — 由 Jiayi Shen / Chia_i_Shen Studio 制作
; Inno Setup 6.3+

[Setup]
AppName=RecordType
AppVersion=2.1.0
AppPublisher=Jiayi Shen
AppPublisherURL=https://chiaishen.studio
AppSupportURL=https://chiaishen.studio/support
AppComments=Audio + Note Recorder by Chia_i_Shen Studio
DefaultDirName={autopf}\RecordType
DefaultGroupName=RecordType
OutputDir=installer
OutputBaseFilename=RecordType_Installer
SetupIconFile=..\src\recordtype\assets\icon.ico
Compression=lzma
SolidCompression=yes
WizardImageFile=wizard_logo.bmp
WizardSmallImageFile=wizard_banner.bmp
LicenseFile=license.txt
PrivilegesRequired=lowest
DisableProgramGroupPage=no
UninstallDisplayIcon={app}\RecordType.exe
UninstallDisplayName=RecordType 2.1.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked
Name: "startmenuicon"; Description: "创建开始菜单快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "..\dist\RecordType.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "wizard_logo.bmp"; DestDir: "{app}"; Flags: dontcopy
Source: "wizard_banner.bmp"; DestDir: "{app}"; Flags: dontcopy
Source: "license.txt"; DestDir: "{app}"; Flags: isreadme

[Icons]
Name: "{autoprograms}\RecordType"; Filename: "{app}\RecordType.exe"; Tasks: startmenuicon
Name: "{autodesktop}\RecordType"; Filename: "{app}\RecordType.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RecordType.exe"; Description: "启动 RecordType"; Flags: nowait postinstall skipifsilent
