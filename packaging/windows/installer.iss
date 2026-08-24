; Inno Setup — Windows é a plataforma principal (ESCOPO.md §9)
#define Nome "Estoque Facil"
#define Versao GetEnv("APP_VERSION")
#if Versao == ""
  #define Versao "0.1.0"
#endif

[Setup]
AppName={#Nome}
AppVersion={#Versao}
AppPublisher=Guilherme Bueno
DefaultDirName={autopf}\EstoqueFacil
DefaultGroupName={#Nome}
OutputBaseFilename=EstoqueFacil-{#Versao}-setup
; caminho relativo a ESTE arquivo (packaging/windows) -> raiz do repositório
OutputDir={#SourcePath}\..\..\artefatos
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
; A pasta de dados fica em %LOCALAPPDATA%\EstoqueFacil, NUNCA em {app}.
; Por isso o desinstalador não encosta no estoque — não acrescente nada aqui
; que apague {localappdata}\EstoqueFacil.
UninstallDisplayIcon={app}\EstoqueFacil.exe
; o assistente de instalação também leva a marca (manual §05)
SetupIconFile={#SourcePath}\..\..\src\estoque_facil\resources\icone.ico

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\..\dist\EstoqueFacil\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#Nome}"; Filename: "{app}\EstoqueFacil.exe"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\EstoqueFacil.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos:"

[Run]
Filename: "{app}\EstoqueFacil.exe"; Description: "Abrir o {#Nome}"; Flags: nowait postinstall skipifsilent
