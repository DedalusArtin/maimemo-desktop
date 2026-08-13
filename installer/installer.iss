; 墨墨背单词 - Inno Setup 安装脚本
#define MyAppName "墨墨背单词"
#define MyAppVersion "1.1.1"
#define MyAppExe "墨墨背单词.exe"
#define MyWebBat "启动Web版.bat"

[Setup]
AppId={{8E3F2A1B-5C44-4D6E-9B2A-4C1F7D0E9A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=开源社区
DefaultDirName={code:GetDefaultDir}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\安装包
OutputBaseFilename=墨墨背单词-安装程序-v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExe}
PrivilegesRequired=lowest
AllowNoIcons=yes
; 保留卸载程序(设置→应用 可卸载,或安装目录 unins000.exe)

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Code]
function GetDefaultDir(Param: string): string;
begin
  if DirExists('D:\') then
    Result := 'D:\'
  else
    Result := ExpandConstant('{sd}');
end;

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(悬浮窗)"; GroupDescription: "附加图标:"; Flags: checkedonce
Name: "webicon"; Description: "创建桌面快捷方式(Web端)"; GroupDescription: "附加图标:"; Flags: unchecked

[Files]
; 注意:不打包 config.json(token 属于隐私,首次启动自动生成默认配置)
Source: "..\墨墨背单词.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\web\*"; DestDir: "{app}\web"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\web版\*"; DestDir: "{app}\web版"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\words.txt"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\说明.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{#MyAppName} Web端"; Filename: "{app}\web版\{#MyWebBat}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon
Name: "{autodesktop}\{#MyAppName} Web端"; Filename: "{app}\web版\{#MyWebBat}"; Tasks: webicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "立即启动 墨墨背单词"; Flags: nowait postinstall skipifsilent
