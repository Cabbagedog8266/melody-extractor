; 主旋律提取器 — Inno Setup script (build with: iscc installer.iss)
; Expects dist\MelodyExtractor\ produced by PyInstaller (melody_extractor.spec).

#define AppName "主旋律提取器"
#define AppNameEn "MelodyExtractor"
#define AppVersion "1.0.0"
#define AppExe "MelodyExtractor.exe"
#define AppPublisher "MelodyExtractor"

[Setup]
AppId={{7C4E1A2B-9D38-4F6E-B0A7-3E5C8D2F9A61}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppNameEn}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename={#AppNameEn}_Setup_v{#AppVersion}
SetupIconFile=appicon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
MinVersion=10.0

[Languages]
Name: "chinese"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#AppNameEn}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2Key = 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2Key64 = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Missing(): Boolean;
var
  pv: String;
begin
  Result := not (
    RegQueryStringValue(HKLM, WebView2Key64, 'pv', pv) or
    RegQueryStringValue(HKLM, WebView2Key, 'pv', pv) or
    RegQueryStringValue(HKCU, WebView2Key, 'pv', pv));
end;

function InitializeSetup(): Boolean;
var
  ErrCode: Integer;
begin
  Result := True;
  if WebView2Missing() then
  begin
    if MsgBox('未检测到 Microsoft Edge WebView2 运行时。' + #13#10 +
              '本程序需要它来显示界面。是否现在打开微软官方下载页面？' + #13#10#13#10 +
              '（Windows 11 与已安装新版 Edge 的 Windows 10 通常已自带，可先跳过重试）',
              mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/consumer/',
                '', '', SW_SHOWNORMAL, ewNoWait, ErrCode);
  end;
end;
