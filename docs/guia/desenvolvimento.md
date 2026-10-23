# Desenvolvimento

Você vai precisar do [uv](https://docs.astral.sh/uv/) e, só para mexer na página, do
[Node](https://nodejs.org/) 20.19 ou mais novo.

```bash
git clone https://github.com/lucasteles1231/editai
cd editai
uv sync                                   # o ambiente, com as dependências de teste

uv run pytest -m "not navegador"          # o núcleo e o servidor (a transcrição é falsa)
uv run playwright install chromium firefox webkit
uv run pytest -m navegador                # a página nos três motores de navegador
uv run ruff check .
```

A página fica em `web/` (React, TypeScript e Vite). Ela é montada para
`editor/interface/estatico/`, que vai versionada, para que quem instala não precise de
Node.

```bash
cd web
npm ci
uv run editai --porta 8765 --sem-navegador   # noutro terminal: a API
npm run dev        # abra localhost:5173/?t=<token>, com o token que o editai mostrou
npm run build      # monta a página de volta no pacote
```

As imagens da documentação são geradas pelo próprio editor:
`uv run python docs/gerar_imagens.py exemplo.mp4`.

## O site e a documentação

Este site sai de `docs/` (o [VitePress](https://vitepress.dev/)) e é publicado no GitHub
Pages pelo workflow `site.yml`, a cada mudança em `docs/` ou no `CHANGELOG.md` que chega ao
`main`, e a cada versão publicada.

```bash
cd docs
npm ci
npm run dev        # localhost:5173/editai/
npm run build      # o VitePress reprova link quebrado entre as páginas
```

**O README é o resumo, e o site é o detalhe.** Os dois mudam juntos, e o
`tests/test_documentacao.py` confere que:

- todo link do README para o site cai numa página e numa âncora que existem;
- todo link e toda imagem entre as páginas do site existem;
- toda opção do `editai` está documentada em [No terminal](./no-terminal);
- os comandos de instalação são os mesmos no README, no site e no `editor/versao.py`.

## Publicar uma versão

1. **O que mudou:** escreva a seção `## [X.Y.Z] — ainda não publicada` no `CHANGELOG.md`.
2. **O número:** `uv run python instalador/nova_versao.py X.Y.Z` põe a versão no
   `pyproject.toml` e no `editor/__init__.py`, e a data no `CHANGELOG.md`.
3. **A tag:**

   ```bash
   uv lock
   git commit -am "Versão X.Y.Z"
   git tag vX.Y.Z
   git push --follow-tags
   ```

A tag dispara o workflow `versao.yml`:

1. ele roda os testes inteiros de novo e confere que a tag é a versão do projeto;
2. monta o pacote (`editai-X.Y.Z-py3-none-any.whl`) e os instaladores
   (`instalador/montar.py`), com os hashes SHA-256;
3. publica a página da versão no GitHub, com as notas tiradas do `CHANGELOG.md`.

Em seguida, o site é refeito com a versão nova nos botões de download, e o aviso de versão
nova chega a quem usa no dia seguinte, no máximo.

Os instaladores ficam em `instalador/`. O teste de verdade deles roda no CI, nos três
sistemas (o trabalho `instalador`, em `testes.yml`): ele instala o pacote montado ali e
confere o atalho. No seu computador, para não mexer no Editai instalado, dá para testar
numa pasta à parte:

```bash
uv build --wheel --out-dir /tmp/pacote
python instalador/montar.py /tmp/inst --so-scripts --versao teste
HOME=/tmp/casa UV_TOOL_DIR=/tmp/tools UV_TOOL_BIN_DIR=/tmp/bin \
  UV_CACHE_DIR="$(uv cache dir)" UV_PYTHON_INSTALL_DIR="$(uv python dir)" \
  EDITAI_PACOTE="$(ls /tmp/pacote/*.whl)" sh /tmp/inst/instalar.sh
```

> [!TIP]
> **Pasta sincronizada com o iCloud (macOS).** O iCloud marca como oculto o `.pth` da
> instalação em modo de desenvolvimento, e o Python 3.12 ignora `.pth` oculto. O
> resultado é um `ModuleNotFoundError: No module named 'editor'`. O `pytest` já contorna
> isso sozinho. Para os outros comandos, use `PYTHONPATH=.` ou clone o projeto fora do
> iCloud.
