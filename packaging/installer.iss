#define AppName "STZ GF UI"
; Nome anterior: os atalhos antigos são removidos ao atualizar.
#define OldAppName "GF UI Editor"
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
; Avisa o Explorer da entrada nova em "Abrir com" (seção [Registry]).
ChangesAssociations=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "..\dist\GF-UI-Editor\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; A GPL exige que a licença acompanhe o programa distribuído.
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{group}\{#OldAppName}.lnk"
Type: files; Name: "{autodesktop}\{#OldAppName}.lnk"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"

[Registry]
; "Abrir com" dos .xml no Explorer, só para este usuário (sem admin). Não vira o programa
; padrão dos .xml: só entra na lista. Tudo sai ao desinstalar.
Root: HKCU; Subkey: "Software\Classes\STZGFUI.xml"; ValueType: string; ValueName: ""; ValueData: "XML de UI do Grand Fantasia"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\STZGFUI.xml\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\STZGFUI.xml\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.xml\OpenWithProgids"; ValueType: string; ValueName: "STZGFUI.xml"; ValueData: ""; Flags: uninsdeletevalue
; Nome mostrado na lista "Abrir com".
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExeName}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExeName}\SupportedTypes"; ValueType: string; ValueName: ".xml"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExeName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""

[Run]
; Sem "skipifsilent": na atualização automática (instalação /SILENT) o editor
; é reaberto ao terminar; na instalação normal vira a caixa "Executar".
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall

[Code]
// Interface nova (beta): usa o Edge WebView2 Runtime, que já vem no Windows 10/11.
// Em Windows "lite" (Tiny11, AtlasOS…) ele pode faltar: baixa o instalador oficial da
// Microsoft (~2 MB) e instala para este usuário. Se falhar (sem internet), segue: a
// interface clássica não precisa dele e o editor avisa ao escolher a nova.
const
  WebView2Client = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2Bootstrapper = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';

function WebView2Installed: Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WebView2Client, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WebView2Client, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + WebView2Client, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

procedure InstallWebView2;
var
  ResultCode: Integer;
begin
  if WebView2Installed then
    Exit;
  try
    DownloadTemporaryFile(WebView2Bootstrapper, 'MicrosoftEdgeWebview2Setup.exe', '', nil);
    Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  except
    Log('WebView2 não instalado: ' + GetExceptionMessage);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    InstallWebView2;
end;
