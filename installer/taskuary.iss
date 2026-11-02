; TaskuarySetup.exe - the Windows download (the owner, 2026-11-02: "the download button on the website should be full installer").
; Build: TASKUARY_ONEDIR=1 pyinstaller taskuary.spec --distpath dist\onedir, then
;        iscc /DAppVersion=X.Y.Z.W installer\taskuary.iss   ->  dist\TaskuarySetup.exe
;
; For this user by default, in %LOCALAPPDATA%\Programs - no admin rights, no IT ticket. The first page offers "for all users" as
; well, and only that asks Windows for the admin yes, like any installer. The data folder (~\.taskuary) is never the installer's:
; uninstalling leaves every connection, task and setting where it is. Updates run this same file quietly (taskuary/update.py).

#ifndef AppVersion
  #define AppVersion "0.0.0.0"
#endif

[Setup]
; never change AppId: it is how an update finds the install it replaces
AppId={{6306b40a-3228-4273-8f53-a5c04956d201}
AppName=Taskuary
AppVersion={#AppVersion}
AppVerName=Taskuary {#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher=Taskuary
AppPublisherURL=https://taskuary.com
AppSupportURL=https://github.com/ldbumble/taskuary/issues
DefaultDirName={autopf}\Taskuary
DefaultGroupName=Taskuary
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=TaskuarySetup
SetupIconFile=..\assets\taskuary.ico
UninstallDisplayIcon={app}\Taskuary.exe
UninstallDisplayName=Taskuary
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; the last version's bundle goes first, so no file a newer build dropped is left behind to be loaded
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\onedir\Taskuary\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Taskuary"; Filename: "{app}\Taskuary.exe"
Name: "{autodesktop}\Taskuary"; Filename: "{app}\Taskuary.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Taskuary.exe"; Description: "{cm:LaunchProgram,Taskuary}"; Flags: nowait postinstall skipifsilent
