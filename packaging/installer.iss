#define AppName "GF UI Editor"
#define AppExeName "GF-UI-Editor.exe"

[Setup]
AppId={{F546E00E-969D-4C17-9D92-D9368C655B18}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=GF-UI-Editor-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=app-icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
; Atualização automática: fecha o editor se ainda estiver aberto; quem o
; reabre é a entrada de [Run], também em modo silencioso.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "..\dist\GF-UI-Editor\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"

[Run]
; Sem "skipifsilent": na atualização automática (instalação /SILENT) o editor
; é reaberto ao terminar; na instalação normal vira a caixa "Executar".
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall
