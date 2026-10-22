; Instalador do Baixou (Inno Setup 6)
; Compile com:  ISCC.exe installer\baixou.iss

#define AppName "Baixou"
#define AppVersion "1.0.0"
#define AppExe "Baixou.exe"
#define Dist "..\build\dist\Baixou"

[Setup]
AppId={{DD34AE2B-A151-42E8-8118-905FE54270F3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Baixou
VersionInfoVersion={#AppVersion}
; Instala só para o usuário atual: não pede senha de administrador.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\build\installer
OutputBaseFilename=Baixou-Setup
SetupIconFile=..\assets\baixou.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
LicenseFile=..\build\licenses\TERCEIROS.txt

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "{#Dist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar o {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Apaga o login salvo e os dados da janela. Os vídeos baixados ficam intactos.
Type: filesandordirs; Name: "{userappdata}\Baixou"
