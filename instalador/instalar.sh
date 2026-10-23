#!/bin/sh
# O instalador do Editai para macOS e Linux.
#
#   curl -LsSf https://lucasteles1231.github.io/editai/instalar.sh | sh
#
# Faz os três passos da instalação manual: instala o uv (se faltar), que cuida do Python sem
# mexer no do sistema; instala o Editai na versão abaixo; e cria o atalho "Editai". Rodar de
# novo atualiza. Para testar com um pacote local: EDITAI_PACOTE=dist/editai-X.Y.Z.whl sh instalar.sh
set -eu

VERSAO="${EDITAI_VERSAO:-__VERSAO__}"
PACOTE="${EDITAI_PACOTE:-https://github.com/lucasteles1231/editai/releases/download/v$VERSAO/editai-$VERSAO-py3-none-any.whl}"

echo "Instalando o Editai $VERSAO"

UV="$(command -v uv 2>/dev/null || true)"
if [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ]; then
  UV="$HOME/.local/bin/uv"
fi
if [ -z "$UV" ]; then
  echo "→ instalando o uv (uns 45 MB)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  UV="$HOME/.local/bin/uv"
fi

echo "→ instalando o Editai (uns 220 MB na primeira vez)…"
"$UV" tool install --force --python 3.12 "$PACOTE"

BIN="$("$UV" tool dir --bin)/editai"
if ! "$BIN" --criar-atalho; then
  echo "(o atalho não foi criado; abra pelo terminal, com: editai)"
fi

echo ""
echo "Pronto! Para abrir, use o atalho Editai, ou digite editai num terminal novo."
