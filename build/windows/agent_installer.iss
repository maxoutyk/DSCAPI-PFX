; Inno Setup — IG E-Sign USB Agent
; Build: build\windows\build-agent.ps1 (Windows only)

#ifndef AgentVersion
#define AgentVersion "0.1.0"
#endif

#define AppName "IG E-Sign Agent"
#define AppPublisher "Incite Gravity"
#define AppExeName "IG-E-Sign-Agent.exe"

[Setup]
AppId={{C4E8A1F2-6D3B-4A9E-9F1C-8B2D5E7A0C4F}
AppName={#AppName}
AppVersion={#AgentVersion}
AppPublisher={#AppPublisher}
AppSupportURL=https://sign.incitegravity.com/
AppUpdatesURL=https://sign.incitegravity.com/
DefaultDirName={autopf}\IG E-Sign Agent
DefaultGroupName={#AppName}
OutputDir=installer-output
OutputBaseFilename=IG-E-Sign-Agent-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut to start the agent"; GroupDescription: "Additional shortcuts:"
Name: "startup"; Description: "Start the agent when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\..\dist\IG-E-Sign-Agent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "agent-scripts\Start Agent.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "agent-scripts\Pair Agent.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "agent-scripts\README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Start {#AppName}"; Filename: "{app}\Start Agent.bat"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Pair {#AppName}"; Filename: "{app}\Pair Agent.bat"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Start Agent.bat"; Tasks: desktopicon; IconFilename: "{app}\{#AppExeName}"

[Run]
Filename: "{app}\Pair Agent.bat"; Description: "Pair with your IG E-Sign account now"; Flags: postinstall skipifsilent nowait unchecked

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "IGEsignAgent"; ValueData: """{app}\{#AppExeName}"" run"; Tasks: startup; Flags: uninsdeletevalue
