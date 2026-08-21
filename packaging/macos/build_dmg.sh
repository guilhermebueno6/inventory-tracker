#!/usr/bin/env bash
# Gera o .dmg do macOS (ESCOPO.md §9.1).
# Sem notarização por decisão de escopo: o Mac é a máquina de desenvolvimento.
# Na primeira abertura: botão direito no app → Abrir.
set -euo pipefail

VERSAO="${APP_VERSION:-0.1.0}"
APP="dist/Estoque Facil.app"
DMG="dist/EstoqueFacil-${VERSAO}.dmg"

[ -d "$APP" ] || { echo "erro: $APP não existe — rode o PyInstaller antes"; exit 1; }

# assinatura ad-hoc: sem ela o app nem abre em Apple Silicon
codesign --force --deep --sign - "$APP"

rm -rf dist/dmg && mkdir -p dist/dmg
cp -R "$APP" dist/dmg/
ln -s /Applications dist/dmg/Applications

hdiutil create -volname "Estoque Facil" -srcfolder dist/dmg -ov -format UDZO "$DMG"
rm -rf dist/dmg
echo "gerado: $DMG"
