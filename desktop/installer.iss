; Inno Setup script for AuditPack.
; Requires Inno Setup 6.3 or later: https://jrsoftware.org/isdl.php
; Compile with:  ISCC.exe desktop\installer.iss
; (desktop\build_windows.ps1 does this for you.)

#define AppName        "AuditPack"
#define AppVersion     "1.0.0"
#define AppPublisher   "AuditPack"
#define AppExeName     "AuditPack.exe"
#define SourceDir      "..\dist\AuditPack"

[Setup]
AppId={{A9D56E7E-265F-4493-AAE7-19DB8209B881}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=..\dist\installer
OutputBaseFilename=AuditPack-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Per-user install by default: no admin prompt, which is one less scary
; dialog for a non-technical user. They can still choose all-users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=
SetupIconFile=icon.ico
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Install the Edge WebView2 runtime if it is missing, so the app opens in
; its own window rather than the default browser. Non-fatal either way.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
    StatusMsg: "Installing Microsoft Edge WebView2 runtime..."; \
    Check: NeedsWebView2 and WebView2DownloadSucceeded; Flags: waituntilterminated
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  WEBVIEW2_CLIENT = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WEBVIEW2_BOOTSTRAPPER_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';

var
  DownloadPage: TDownloadWizardPage;
  BootstrapperReady: Boolean;

function WebView2Version(RootKey: Integer; const SubKey: string): Boolean;
var
  Version: string;
begin
  Result := RegQueryStringValue(RootKey, SubKey, 'pv', Version) and
            (Version <> '') and (Version <> '0.0.0.0');
end;

function NeedsWebView2: Boolean;
begin
  Result := not (
    WebView2Version(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WEBVIEW2_CLIENT) or
    WebView2Version(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WEBVIEW2_CLIENT) or
    WebView2Version(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WEBVIEW2_CLIENT));
end;

function WebView2DownloadSucceeded: Boolean;
begin
  Result := BootstrapperReady;
end;

procedure InitializeWizard;
begin
  BootstrapperReady := False;
  DownloadPage := CreateDownloadPage(
    SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and NeedsWebView2 then
  begin
    DownloadPage.Clear;
    DownloadPage.Add(WEBVIEW2_BOOTSTRAPPER_URL, 'MicrosoftEdgeWebview2Setup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        BootstrapperReady := True;
      except
        // Offline or blocked: install anyway, the app falls back to the browser.
        BootstrapperReady := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

// Offer to remove the saved API key and logs, which live outside the install
// folder in %APPDATA%\AuditPack and would otherwise be left behind.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\AuditPack');
    if DirExists(DataDir) and (not UninstallSilent) then
      if MsgBox('Also delete your saved API key and logs?' + #13#10 + DataDir,
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
