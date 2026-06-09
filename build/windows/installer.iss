; Inno Setup script — compile on Windows with Inno Setup 6+
; Output: build/windows/installer-output/DSCAPI-PFX-Setup.exe

#define AppName "DSCAPI-PFX"
#define AppVersion "1.0.0"
#define AppPublisher "DSCAPI"
#define AppExeName "DSCAPI-PFX.exe"

[Setup]
AppId={{A8F3C2E1-9B4D-4F6A-8C1E-2D5E7F9A0B3C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer-output
OutputBaseFilename=DSCAPI-PFX-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\..\dist\DSCAPI-PFX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\certs\.gitkeep"; DestDir: "{app}\certs"; Flags: ignoreversion

[Dirs]
Name: "{app}\certs"; Permissions: users-modify

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent
