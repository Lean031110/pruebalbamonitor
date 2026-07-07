; ===========================================================================
; LBAMonitor — Inno Setup installer script
; Genera LBAMonitor-Setup-1.0.0.exe
;
; Uso:
;   1. Compilar backend con PyInstaller:
;      cd backend && pyinstaller ../installer/pyinstaller/svc.spec
;      pyinstaller ../installer/pyinstaller/cli.spec
;   2. Compilar desktop:
;      cd desktop && pyinstaller ../installer/pyinstaller/desktop.spec
;   3. Copiar dist/ a installer/build/
;   4. Compilar con Inno Setup Compiler:
;      iscc installer\msi\lbamonitor.iss
; ===========================================================================

#define MyAppName "LBAMonitor"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "LBAMonitor"
#define MyAppURL "https://lbamonitor.example.com"
#define MyAppExeName "lbamonitor-desktop.exe"

[Setup]
AppId={{LBAMONITOR-{{1A2B3C4D-5E6F-7890-ABCD-EF1234567890}}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={pf}\LBAMonitor
DefaultGroupName=LBAMonitor
DisableProgramGroupPage=yes
OutputDir=..\build
OutputBaseFilename=LBAMonitor-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayIcon={app}\lbamonitor-desktop.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Additional shortcuts:"

[Files]
; Backend (servicio + API + CLI)
Source: "..\build\lbamonitor-svc\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\build\lbamonitor-cli\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Check: DirExists(ExpandConstant('{tmp}\..\build\lbamonitor-cli'))
; Desktop admin
Source: "..\build\lbamonitor-desktop\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Config
Source: "..\..\config.default.toml"; DestDir: "{app}"; Flags: ignoreversion
; Assets
Source: "..\assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Crear directorios de datos en ProgramData (persistentes)
Name: "{commonappdata}\LBAMonitor"; Flags: uninsneveruninstall
Name: "{commonappdata}\LBAMonitor\data"; Flags: uninsneveruninstall
Name: "{commonappdata}\LBAMonitor\logs"; Flags: uninsneveruninstall
Name: "{commonappdata}\LBAMonitor\backups"; Flags: uninsneveruninstall
Name: "{commonappdata}\LBAMonitor\exports"; Flags: uninsneveruninstall
Name: "{commonappdata}\LBAMonitor\config"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\LBAMonitor"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Detener servicio"; Filename: "{app}\nssm.exe"; Parameters: "stop LBAMonitorService"
Name: "{group}\Iniciar servicio"; Filename: "{app}\nssm.exe"; Parameters: "start LBAMonitorService"
Name: "{group}\Desinstalar LBAMonitor"; Filename: "{uninstallexe}"
Name: "{commondesktop}\LBAMonitor"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Copiar config default si no existe config.toml
Filename: "{cmd}"; Parameters: "/C copy ""{app}\config.default.toml"" ""{commonappdata}\LBAMonitor\config\config.toml"""; Flags: runhidden; Check: not FileExists(ExpandConstant('{commonappdata}\LBAMonitor\config\config.toml'))

; Instalar servicio Windows con NSSM
Filename: "{app}\nssm.exe"; Parameters: "install LBAMonitorService ""{app}\lbamonitor-svc.exe"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set LBAMonitorService Start SERVICE_AUTO_START"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set LBAMonitorService AppDirectory ""{app}"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set LBAMonitorService AppStdout ""{commonappdata}\LBAMonitor\logs\svc-stdout.log"""; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "set LBAMonitorService AppStderr ""{commonappdata}\LBAMonitor\logs\svc-stderr.log"""; Flags: runhidden

; Iniciar servicio
Filename: "{app}\nssm.exe"; Parameters: "start LBAMonitorService"; Flags: runhidden; Description: "Iniciar servicio LBAMonitor"

; Lanzar app desktop
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar LBAMonitor ahora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Detener y eliminar servicio
Filename: "{app}\nssm.exe"; Parameters: "stop LBAMonitorService"; Flags: runhidden
Filename: "{app}\nssm.exe"; Parameters: "remove LBAMonitorService confirm"; Flags: runhidden

[UninstallDelete]
; Limpiar logs y cache (NO borrar data ni backups)
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1';
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  // TODO: verificar que Windows 10+ 64-bit
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    if IsUpgrade() then
    begin
      // Detener servicio antes de upgrade
      ShellExec('open', ExpandConstant('{app}\nssm.exe'), 'stop LBAMonitorService', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
    end;
  end;
end;

var
  ErrorCode: Integer;
