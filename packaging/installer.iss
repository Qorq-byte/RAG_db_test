[Setup]
AppId={{E857EDEA-88B7-42C7-B326-C808257216B1}
AppName=RAGDB
AppVersion=0.2.0
DefaultDirName={localappdata}\Programs\RAGDB
DefaultGroupName=RAGDB
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=RAGDB-0.2.0-windows-x64-setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\RAGDB.exe
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\RAGDB\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RAGDB"; Filename: "{app}\RAGDB.exe"
Name: "{autodesktop}\RAGDB"; Filename: "{app}\RAGDB.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\RAGDB.exe"; Description: "Launch RAGDB"; Flags: nowait postinstall skipifsilent
