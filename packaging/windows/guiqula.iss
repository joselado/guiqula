; Inno Setup script of the Windows installer (PLAN.md section 6, phase 6).
; Wraps the PyInstaller folder dist\guiqula (packaging\pyinstaller\guiqula.spec):
;   iscc /DVersion=0.1.0 packaging\windows\guiqula.iss
; gives dist\guiqula-<version>-windows-x64-setup.exe. It installs for the current
; user by default (no administrator rights; the dialog offers all users), adds a Start
; menu entry, optionally a desktop icon, and opens .guiqula files with guiqula.
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{757E2985-3064-45D1-9098-D5733D4AF25A}
AppName=guiqula
AppVersion={#Version}
AppPublisher=Jose Lado
AppPublisherURL=https://github.com/joselado/pyqula
DefaultDirName={autopf}\guiqula
DefaultGroupName=guiqula
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=guiqula-{#Version}-windows-x64-setup
SetupIconFile=..\..\src\guiqula\resources\guiqula.ico
UninstallDisplayIcon={app}\guiqula.exe
LicenseFile=..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\guiqula\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\guiqula"; Filename: "{app}\guiqula.exe"
Name: "{autodesktop}\guiqula"; Filename: "{app}\guiqula.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.guiqula"; ValueType: string; ValueName: ""; ValueData: "guiqula.project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\guiqula.project"; ValueType: string; ValueName: ""; ValueData: "guiqula project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\guiqula.project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\guiqula.exe,0"
Root: HKA; Subkey: "Software\Classes\guiqula.project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\guiqula.exe"" ""%1"""

[Run]
Filename: "{app}\guiqula.exe"; Description: "{cm:LaunchProgram,guiqula}"; Flags: nowait postinstall skipifsilent
