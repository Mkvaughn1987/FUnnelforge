; ============================================================
; Funnel Forge - Inno Setup Script (FULL)
; - Copies ENTIRE PyInstaller onedir output (EXE + _internal + assets)
; - Creates Desktop shortcut AUTOMATICALLY
; - Uses embedded EXE icon for shortcuts
; - Uses your ICO for installer icon (optional but recommended)
; ============================================================

#define AppName "FNNL FORGE"
#define AppVersion "2.3"
#define AppPublisher "MVaughn"
#define AppExeName "FunnelForge.exe"

; <<< IMPORTANT: This must point to your PyInstaller output folder >>>
#define DistDir "dist\FunnelForge"

; <<< OPTIONAL: installer icon file (recommended). Update if needed. >>>
#define SetupIco "funnelforge_desktop.ico"

[Setup]
AppId={{A7D4E2B1-6A77-4E6F-9D2A-9A0B2E7B1C11}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}

; ✅ Per-user install (no admin) — best for coworkers
PrivilegesRequired=lowest
DefaultDirName={localappdata}\{#AppName}

DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

WizardStyle=modern
Compression=lzma2
SolidCompression=yes

OutputDir=installer
OutputBaseFilename=FunnelForge-Setup-{#AppVersion}

; Installer icon (if file exists)
SetupIconFile={#SetupIco}

; Uninstall icon in Apps & Features
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; ✅ CRITICAL: Copy EVERYTHING from dist\FunnelForge (including _internal + assets)
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Icon files for desktop and taskbar
Source: "funnelforge_desktop.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "funnelforge_taskbar.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu shortcut
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\funnelforge_desktop.ico"

; ✅ Desktop shortcut ALWAYS created + uses desktop icon file
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\funnelforge_desktop.ico"

[Run]
; Launch after install
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
