"""
A página num navegador de verdade (Playwright): o tour, uma edição inteira e a
thumbnail gerada no navegador — no Chromium (Chrome e Edge), no Firefox e no WebKit
(o motor do Safari, que o macOS abre por padrão).

Cada motor que não estiver instalado é pulado:
    uv run playwright install chromium firefox webkit
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from tests.conftest import fazer_video

pytestmark = pytest.mark.navegador

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

PORTA, TOKEN = 8911, "token-do-navegador"


def _instalado(motor: str) -> bool:
    try:
        with playwright.sync_playwright() as p:
            getattr(p, motor).launch().close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module", params=["chromium", "firefox", "webkit"])
def navegador(request):
    if not _instalado(request.param):
        pytest.skip(f"{request.param} do Playwright não instalado")
    with playwright.sync_playwright() as p:
        nav = getattr(p, request.param).launch()
        yield nav
        nav.close()


#: Anota cada recurso barrado pela CSP do editor (o Firefox nem sempre põe no console).
VIGIAR_A_CSP = ("window.__barrados = [];"
                "document.addEventListener('securitypolicyviolation',"
                " (e) => window.__barrados.push(e.violatedDirective + ' ' + e.blockedURI));")


def _barrados(pagina) -> list[str]:
    return pagina.evaluate("window.__barrados || []")


@pytest.fixture
def endereco(tmp_path):
    import uvicorn

    from editor import servidor

    app = servidor.criar_app(TOKEN, porta=PORTA, pasta_saida=tmp_path / "saida")
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORTA, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{PORTA}/?t={TOKEN}"
    srv.should_exit = True
    thread.join(5)


def test_tour_edicao_e_thumbnail(navegador, endereco, tmp_path):
    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.add_init_script(VIGIAR_A_CSP)
    pagina.goto(endereco)

    # O tour abre sozinho na primeira visita: os dois jeitos de usar e um passo por área
    # (nove ao todo). Cada passo é esperado antes do clique seguinte: o balão anima entre
    # um e outro, e no CI (mais lento) o texto ainda dizia "6 de 7" logo depois do sexto
    # clique.
    progresso = pagina.locator(".driver-popover-progress-text")
    expect(progresso).to_have_text("1 de 9", timeout=10_000)
    expect(pagina.locator(".driver-popover-title")).to_have_text("Dois jeitos de usar")
    expect(pagina.locator(".driver-popover-description")).to_contain_text(
        "Notícia com cenas")
    for passo in range(2, 10):
        pagina.locator(".driver-popover-next-btn").click()
        expect(progresso).to_have_text(f"{passo} de 9")
    pagina.locator(".driver-popover-next-btn").click()      # "Começar a editar"
    pagina.locator(".driver-popover").wait_for(state="detached")

    # Envia, edita e espera a thumbnail desenhada no navegador. A IA e o recorte são os
    # falsos (conftest): três ideias fixas e uma silhueta de busto, sem rede nem modelo.
    video = fazer_video(tmp_path / "meu video.mp4", segundos=4.0)
    pagina.set_input_files("#passo-envio input[type=file]", str(video))
    pagina.locator(".ficha").wait_for(timeout=20_000)
    # No vídeo único, mover a pessoa não aparece: só a montagem tem para onde levá-la.
    expect(pagina.locator("label.interruptor", has_text="Mover a pessoa")).to_have_count(0)
    with pagina.expect_request(lambda r: r.url.split("?")[0].endswith("/api/tarefas")
                               and r.method == "POST") as pedido:
        pagina.get_by_role("button", name="Editar vídeo").click()
    assert "video_id" in pedido.value.post_data_json
    pagina.locator(".miniaturas img").first.wait_for(timeout=120_000)

    # as três ideias viram cartões, e a primeira já é a thumbnail
    ideias = pagina.locator(".ideia")
    expect(ideias).to_have_count(3)
    expect(ideias.nth(0)).to_have_attribute("aria-pressed", "true")
    chamada = pagina.get_by_label("chamada", exact=False).first
    expect(chamada).to_have_value("Corta as pausas sozinho")

    # O vídeo do teste é em pé: a thumbnail sai no formato de Shorts, TikTok e Reels.
    saida = tmp_path / "saida"
    pngs = list(saida.glob("*-thumb-1080x1920.png"))
    assert len(pngs) == 1 and list(saida.glob("*-editado.mp4"))
    with Image.open(pngs[0]) as im:
        assert im.size == (1080, 1920)
        # não é um retângulo vazio: tem o recorte, o contorno branco e a cor de destaque
        cores = im.convert("RGB").getcolors(1_000_000)
        assert len(cores) > 500
        assert any(r > 250 and g > 250 and b > 250 for _, (r, g, b) in cores)
    primeira = pngs[0].read_bytes()

    # Escolher outra ideia e baixar: sai a capa como está na tela, e a da pasta é trocada.
    ideias.nth(2).click()
    expect(ideias.nth(2)).to_have_attribute("aria-pressed", "true")
    with pagina.expect_download(timeout=60_000) as baixada:
        pagina.get_by_role("button", name=re.compile("^Baixar para Shorts, TikTok e Reels")).click()
    jpg = tmp_path / "baixada.jpg"
    baixada.value.save_as(jpg)
    with Image.open(jpg) as im:
        assert im.format == "JPEG" and im.size == (1080, 1920)
    assert jpg.stat().st_size <= 2 * 1024 * 1024
    assert pngs[0].read_bytes() != primeira

    # A primeira ideia (falsa) traz a mão apontando: ela está na prévia.
    ideias.nth(0).click()
    previa = pagina.locator(".previa-thumb")
    expect(previa.locator('svg image[href*="/maos/"]').first).to_be_attached()

    # Arrastar a pessoa na prévia muda a posição dela (e "voltar ao automático" acende).
    # A prévia tem de estar na tela: fora dela, o Firefox não entrega o arrasto (e o
    # Chromium entrega, o que escondia o erro do teste).
    previa.scroll_into_view_if_needed()
    caixa = previa.bounding_box()
    # Em pé (o vídeo do teste), a pessoa fica no meio, embaixo da chamada.
    x0, y0 = caixa["x"] + caixa["width"] * 0.5, caixa["y"] + caixa["height"] * 0.75
    pagina.mouse.move(x0, y0)
    pagina.mouse.down()
    pagina.mouse.move(x0 - caixa["width"] * 0.2, y0, steps=6)
    pagina.mouse.up()
    pagina.get_by_role("tab", name="Pessoa").click()
    expect(pagina.get_by_role("button", name="Voltar ao automático")).to_be_enabled()

    # As fontes do fundo: a foto do Pexels (falso), a gerada (falsa) e a enviada.
    pagina.get_by_role("tab", name="Fundo").click()
    imagem_no_fundo = previa.locator('svg image[href*="/api/imagens/"]').first
    pagina.get_by_role("button", name="Pexels", exact=True).click()
    pagina.get_by_label("buscar no Pexels").fill("estúdio")
    pagina.get_by_role("button", name="Buscar", exact=True).click()
    pagina.locator(".fotos-pexels button").first.click()
    expect(imagem_no_fundo).to_be_attached()

    pagina.get_by_role("button", name="Gerar com IA").click()
    pagina.get_by_label("descrição do fundo").fill("um estúdio com luz neon")
    pagina.get_by_role("button", name="Gerar fundo (~US$ 0,04)").click()
    expect(pagina.locator(".credito")).to_contain_text("um estúdio com luz neon")

    fundo = tmp_path / "fundo.png"
    Image.new("RGB", (800, 450), (0, 90, 200)).save(fundo)
    pagina.get_by_role("button", name="Imagem", exact=True).click()
    pagina.set_input_files(".soltar-imagem input[type=file]", str(fundo))
    expect(pagina.locator(".soltar-imagem strong")).to_have_text("Arraste uma imagem aqui")
    expect(imagem_no_fundo).to_be_attached()

    pagina.get_by_role("button", name="Cor", exact=True).click()
    expect(imagem_no_fundo).not_to_be_attached()
    assert erros == [], erros


def test_montagem_com_personagem_e_narracao(navegador, endereco, tmp_path):
    """Um fundo sem pessoa, um personagem animado por cima e a narração à parte."""
    from tests.conftest import ler_info
    from tests.test_montagem import audio_wav, gif

    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.goto(endereco)

    pagina.get_by_role("button", name="Um fundo e, por cima").click()
    fundo = fazer_video(tmp_path / "tela.mp4", largura=320, altura=180, segundos=3.0,
                        com_audio=False)
    pagina.set_input_files('[data-envio="fundo"] input', str(fundo))
    expect(pagina.get_by_label("dados do fundo")).to_contain_text("320×180")
    pagina.get_by_role("button", name="Personagem animado").click()
    pagina.set_input_files('[data-envio="personagem"] input', str(gif(tmp_path / "b.gif", lado=80)))
    expect(pagina.get_by_label("dados do personagem")).to_contain_text("4 quadros")
    expect(pagina.locator(".tela-montada .por-cima")).to_be_attached()
    # De onde vem o áudio: com o personagem, o fundo, um áudio separado ou a "Minha voz";
    # e o fundo deste teste é mudo, então a pílula dele fica desligada.
    audio_vem_de = pagina.get_by_role("group", name="de onde vem o áudio")
    expect(audio_vem_de.get_by_role("button")).to_have_count(3)
    expect(audio_vem_de.get_by_role("button", name="O vídeo de fundo")).to_be_disabled()
    expect(pagina.locator('[data-envio="audio"]')).to_have_count(0)
    audio_vem_de.get_by_role("button", name="Áudio separado").click()
    pagina.set_input_files('[data-envio="audio"] input', str(audio_wav(tmp_path / "n.wav")))
    expect(pagina.get_by_label("os áudios separados")).to_contain_text("n.wav")
    # a montagem tem o "Mover o personagem"; o fundo é deitado, e o editor recomenda o
    # YouTube. Trocar para o TikTok põe o quadro em pé (o passo 4 acompanha).
    expect(pagina.locator("label.interruptor", has_text="Mover o personagem")).to_have_count(1)
    onde = pagina.get_by_role("group", name="onde você vai postar")
    expect(onde.locator('[aria-pressed="true"]')).to_have_text(re.compile("^YouTube recomendado"))
    onde.get_by_role("button", name=re.compile("^TikTok")).click()
    onde.get_by_role("button", name=re.compile("^YouTube( recomendado)?$")).click()
    em_pe = pagina.get_by_role("button", name="Em pé (9:16)")
    expect(em_pe).to_have_attribute("aria-pressed", "true")

    with pagina.expect_request(lambda r: r.url.split("?")[0].endswith("/api/tarefas")
                               and r.method == "POST") as pedido:
        pagina.get_by_role("button", name="Editar vídeo").click()
    montagem = pedido.value.post_data_json["montagem"]
    assert montagem["formato"] == "vertical" and montagem["fala"] == "audio"
    assert montagem["personagem_id"] and len(montagem["audio_ids"]) == 1
    assert "pessoa_id" not in montagem
    pagina.locator(".miniaturas img").first.wait_for(timeout=120_000)

    saida = tmp_path / "saida"
    editado = next(saida.glob("tela-editado.mp4"))
    assert (ler_info(editado)["largura"], ler_info(editado)["altura"]) == (180, 320)
    assert list(saida.glob("*-thumb-1080x1920.png"))
    assert not _barrados(pagina), _barrados(pagina)
    assert not erros, erros


def test_biblioteca_de_cenas(navegador, endereco, tmp_path):
    """A pasta de cenas com a matriz dentro, nada por cima, a narração em dois arquivos e
    o preset "Notícia com cenas": o pedido leva a biblioteca e os áudios em ordem, e o
    resultado diz quem escreveu o roteiro (a IA falsa, nos testes)."""
    import json

    from tests.test_montagem import audio_wav

    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.add_init_script(VIGIAR_A_CSP)
    pagina.goto(endereco)

    pasta = tmp_path / "cenas"
    (pasta / "clipes").mkdir(parents=True)
    for k, nome in enumerate(["t1-001", "t1-002", "t1-003", "t1-004"]):
        fazer_video(pasta / "clipes" / f"{nome}.mp4", largura=320, altura=180,
                    segundos=1.0 + k * 0.2, com_audio=False)
    matriz = [{"id": "t1-001", "arquivo": "cenas/clipes/t1-001.mp4", "descricao": "explosão",
               "energia": "alta"},
              {"id": "t1-002", "arquivo": "t1-002.mp4", "descricao": "praia"},
              {"id": "t1-003", "arquivo": "t1-003.mp4", "descricao": "boate",
               "monetizacao": "evitar"},
              {"id": "t1-004", "arquivo": "t1-004.mp4", "descricao": "cidade"}]
    (pasta / "cenas.json").write_text(json.dumps(matriz), encoding="utf-8")

    pagina.get_by_role("button", name="Um fundo e, por cima").click()
    pagina.get_by_role("button", name="Biblioteca de cenas").click()
    pagina.set_input_files('[data-envio="cenas"] input', str(pasta))
    ficha = pagina.get_by_label("dados da biblioteca de cenas")
    expect(ficha).to_contain_text("3 cenas", timeout=30_000)
    expect(ficha).to_contain_text("1 marcada “evitar” (fica de fora)")
    pagina.get_by_role("button", name="Nada", exact=True).click()
    # Sem som nos clipes, a fala vem dos áudios (ou das cenas, ou da "Minha voz"): dois, que
    # tocam na ordem do nome.
    audio_vem_de = pagina.get_by_role("group", name="de onde vem o áudio")
    expect(audio_vem_de.get_by_role("button")).to_have_count(3)
    pagina.set_input_files('[data-envio="audio"] input',
                           [str(audio_wav(tmp_path / "parte 2.wav")),
                            str(audio_wav(tmp_path / "parte 1.wav"))])
    expect(pagina.get_by_label("os áudios separados")).to_contain_text("1. parte 1.wav")
    expect(pagina.get_by_label("os áudios separados")).to_contain_text("2. parte 2.wav")

    pagina.get_by_role("button", name=re.compile("^Notícia com cenas")).click()
    expect(pagina.locator("label.interruptor", has_text="Janela e câmera")
           .locator("input")).to_be_checked()
    expect(pagina.get_by_role("group", name="Voz").get_by_role("button", name="Estúdio")
           ).to_have_attribute("aria-pressed", "true")
    expect(pagina.get_by_role("group", name="Estilo").get_by_role("button", name="Destaques")
           ).to_have_attribute("aria-pressed", "true")
    expect(pagina.get_by_placeholder("cocaína, sexo, decapitação")).to_have_value(
        re.compile("^cocaína, sexo"))
    # leve, para o teste não demorar (a biblioteca não limita a resolução)
    pagina.get_by_role("button", name="Em pé (9:16)").click()
    resolucao = pagina.locator("label.campo", has_text="Resolução").locator("select")
    expect(resolucao.locator('option[value="2160p"]')).to_be_enabled()
    resolucao.select_option("480p")

    with pagina.expect_request(lambda r: r.url.split("?")[0].endswith("/api/tarefas")
                               and r.method == "POST") as pedido:
        pagina.get_by_role("button", name="Editar vídeo").click()
    dados = pedido.value.post_data_json
    montagem = dados["montagem"]
    assert montagem["biblioteca_id"] and "fundo_id" not in montagem
    assert len(montagem["audio_ids"]) == 2 and montagem["fala"] == "audio"
    assert "pessoa_id" not in montagem and "personagem_id" not in montagem
    assert dados["edicao"]["estilo_da_legenda"] == "destaques"
    expect(pagina.locator(".painel .roteiro")).to_contain_text("Roteiro da IA de teste",
                                                               timeout=180_000)
    assert list((tmp_path / "saida").glob("cenas-editado.mp4"))
    assert not _barrados(pagina), _barrados(pagina)
    assert not erros, erros


def test_minha_voz(navegador, endereco, tmp_path):
    """A "Minha voz" do começo ao fim, com um arquivo no lugar do microfone: o nome, a
    leitura enviada e conferida, a voz salva, o roteiro narrado (pelo motor falso) e o
    pedido de edição com a narração como áudio separado."""
    from tests.test_voz_clonada import _leitura

    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.add_init_script(VIGIAR_A_CSP)
    pagina.goto(endereco)

    pagina.get_by_role("button", name="Um fundo e, por cima").click()
    fundo = fazer_video(tmp_path / "tela.mp4", largura=320, altura=180, segundos=2.0,
                        com_audio=False)
    pagina.set_input_files('[data-envio="fundo"] input', str(fundo))
    expect(pagina.get_by_label("dados do fundo")).to_contain_text("320×180")
    pagina.get_by_role("button", name="Nada", exact=True).click()
    pagina.get_by_role("group", name="de onde vem o áudio").get_by_role(
        "button", name="Minha voz (de um roteiro)").click()
    editar = pagina.get_by_role("button", name="Editar vídeo")
    expect(editar).to_be_disabled()                 # sem a narração, ainda não

    # sem nenhuma voz salva, a gravação abre direto
    gravar = pagina.get_by_label("gravar a sua voz")
    gravar.get_by_label("Seu nome (vai na autorização)").fill("Ana")
    gravar.get_by_role("button", name="Começar a leitura").click()
    expect(gravar.get_by_label("o parágrafo 1")).to_contain_text("Eu, Ana, autorizo")
    paragrafos = gravar.get_by_label("os parágrafos da leitura").get_by_role("button")
    total = paragrafos.count()
    assert total >= 8
    gravar.get_by_role("button", name="Enviar a gravação").click()
    expect(gravar.get_by_label("o texto inteiro")).to_contain_text("Que notícia incrível!")
    gravar.get_by_label("a gravação da leitura inteira").set_input_files(
        str(_leitura(tmp_path / "leitura.wav", total)))
    expect(gravar).to_contain_text(f"{total} de {total} parágrafos aprovados", timeout=30_000)
    expect(gravar.get_by_role("status")).to_contain_text("Parágrafo 1 aprovado")
    salvar = gravar.get_by_role("button", name="Salvar a minha voz")
    expect(salvar).to_be_enabled()
    salvar.click()

    voz = pagina.get_by_label("minha voz")
    expect(voz.get_by_role("group", name="as vozes salvas").get_by_role("button", name="Ana")
           ).to_have_attribute("aria-pressed", "true", timeout=15_000)
    voz.get_by_label("o roteiro a narrar").fill(
        "A Rockstar confirmou: o PEGI deu 18 anos.\n\nE aí, passou do ponto? Comenta aí.")
    voz.locator("summary", has_text="Pronúncia").click()
    voz.get_by_label("a lista de pronúncia").fill("PEGI = pégui")
    voz.get_by_role("button", name="Narrar o roteiro").click()
    expect(voz).to_contain_text("pronta para editar", timeout=30_000)
    expect(voz.locator("summary")).to_have_text("Pronúncia (1)")

    pagina.get_by_role("button", name="Em pé (9:16)").click()
    expect(editar).to_be_enabled()
    with pagina.expect_request(lambda r: r.url.split("?")[0].endswith("/api/tarefas")
                               and r.method == "POST") as pedido:
        editar.click()
    montagem = pedido.value.post_data_json["montagem"]
    assert montagem["fala"] == "audio" and len(montagem["audio_ids"]) == 1
    pagina.locator(".miniaturas img").first.wait_for(timeout=120_000)
    assert list((tmp_path / "saida").glob("tela-editado.mp4"))
    assert not _barrados(pagina), _barrados(pagina)
    assert not erros, erros


def test_minha_voz_pelo_microfone(navegador, endereco):
    """O teleprompter grava pelo microfone de verdade da página (o MediaRecorder): no
    Chromium, um microfone falso que toca bipes. A gravação chega ao servidor, é lida
    pelo PyAV (WebM com Opus) e recebe a nota."""
    if navegador.browser_type.name != "chromium":
        pytest.skip("só o Chromium tem o microfone falso")
    nav = navegador.browser_type.launch(args=["--use-fake-ui-for-media-stream",
                                              "--use-fake-device-for-media-stream"])
    try:
        pagina = nav.new_page()
        pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
        pagina.goto(endereco)
        pagina.get_by_role("button", name="Um fundo e, por cima").click()
        pagina.get_by_role("group", name="de onde vem o áudio").get_by_role(
            "button", name="Minha voz (de um roteiro)").click()
        gravar = pagina.get_by_label("gravar a sua voz")
        gravar.get_by_label("Seu nome (vai na autorização)").fill("Ana")
        gravar.get_by_role("button", name="Começar a leitura").click()
        gravar.get_by_role("button", name="Gravar o parágrafo 1").click()
        parar = gravar.get_by_role("button", name="Parar")
        expect(parar).to_be_visible()
        pagina.wait_for_timeout(3500)
        parar.click()
        # o bipe do microfone falso vem no volume máximo: a nota é "estourou", e as
        # medidas mostram que a gravação foi lida inteira
        resultado = gravar.get_by_role("status")
        expect(resultado).to_contain_text("Regrave o parágrafo 1", timeout=30_000)
        expect(resultado).to_contain_text("O som estourou")
        expect(resultado).to_contain_text("100% das palavras")
        expect(gravar.get_by_role("button", name="Regravar o parágrafo 1")).to_be_visible()
        expect(gravar.get_by_label("parágrafo 1: regravar")).to_be_visible()
    finally:
        nav.close()


def test_os_meus_presets(navegador, endereco, tmp_path):
    """Um preset seu: sai do "Personalizado", fica depois de recarregar a página, volta os
    valores quando escolhido, substitui pelo mesmo nome, entra por um arquivo importado e
    sai pelo ×."""
    import json

    from editor import presets

    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    pagina.add_init_script(VIGIAR_A_CSP)
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.on("dialog", lambda d: d.accept())
    pagina.goto(endereco)

    grupo = pagina.get_by_role("group", name="presets de edição")
    grupo.get_by_role("button", name=re.compile("^Short de gameplay")).click()
    zoom = pagina.locator("label.interruptor", has_text="Zoom de ênfase")
    zoom.click()                                         # muda um valor: vira "Personalizado"
    expect(zoom.locator("input")).not_to_be_checked()
    pagina.get_by_role("button", name="Salvar como preset").click()
    formulario = pagina.get_by_role("form", name="salvar como preset")
    formulario.get_by_label("Nome do preset").fill("Meu gameplay")
    formulario.get_by_label("Frase (opcional)").fill("Sem zoom, o resto do gameplay")
    formulario.get_by_role("button", name="Salvar").click()
    meu = grupo.get_by_role("button", name=re.compile("^Meu gameplay seu"))
    expect(meu).to_have_attribute("aria-pressed", "true")
    expect(formulario).to_have_count(0)

    # fica depois de recarregar, e volta os valores dele
    pagina.reload()
    grupo.get_by_role("button", name=re.compile("^Padrão")).click()
    expect(zoom.locator("input")).to_be_checked()
    meu.click()
    expect(zoom.locator("input")).not_to_be_checked()
    expect(meu).to_have_attribute("aria-pressed", "true")

    # o mesmo nome pede para substituir
    pagina.locator("label.interruptor", has_text="Cortar silêncios").click()
    pagina.get_by_role("button", name="Salvar como preset").click()
    formulario.get_by_label("Nome do preset").fill("Meu gameplay")
    formulario.get_by_role("button", name="Salvar").click()
    expect(formulario).to_contain_text("Já existe um preset seu com esse nome")
    formulario.get_by_role("button", name="Substituir").click()
    expect(meu).to_have_attribute("aria-pressed", "true")
    assert presets.todos()["meu-gameplay"].edicao["cortes"] is False

    # o nome de um preset pronto é recusado na hora, sem ir ao servidor
    pagina.locator("label.interruptor", has_text="Cortar silêncios").click()
    pagina.get_by_role("button", name="Salvar como preset").click()
    formulario.get_by_label("Nome do preset").fill("Humor")
    formulario.get_by_role("button", name="Salvar").click()
    expect(formulario).to_contain_text("é o nome de um preset pronto")
    formulario.get_by_role("button", name="Cancelar").click()

    # um arquivo exportado de outro computador entra pelo "Importar"
    expect(pagina.get_by_role("link", name="Exportar os seus")).to_have_attribute(
        "href", re.compile("/api/presets/exportar"))
    outro = {**presets.exportar(), "presets": [{
        "titulo": "Aula calma", "frase": "",
        "edicao": {**presets.PRESETS["aula"].edicao, "ritmo": 0.6},
        "saida": presets.PRESETS["aula"].saida, "thumb": presets.PRESETS["aula"].thumb}]}
    arquivo = tmp_path / "presets-do-outro.json"
    arquivo.write_text(json.dumps(outro), encoding="utf-8")
    pagina.get_by_label("importar presets").set_input_files(str(arquivo))
    expect(pagina.get_by_role("status")).to_contain_text("Entraram: Aula calma")
    expect(grupo.get_by_role("button", name=re.compile("^Aula calma seu"))).to_be_visible()

    # e sai pelo ×
    pagina.get_by_role("button", name="apagar o preset Meu gameplay").click()
    expect(meu).to_have_count(0)
    assert "meu-gameplay" not in presets.todos()
    assert not _barrados(pagina), _barrados(pagina)
    assert not erros, erros


def test_fotos_e_o_som_das_cenas(navegador, endereco, tmp_path):
    """Uma pasta com fotos e vídeos com som: as fotos entram como cenas, e o som vem dos
    vídeos marcados, na ordem dos números (clicar de novo tira, e os outros andam)."""
    import json

    from tests.test_cenas import _foto

    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    pagina.add_init_script(VIGIAR_A_CSP)
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.goto(endereco)

    pasta = tmp_path / "imovel"
    pasta.mkdir()
    for nome in ("sala.jpg", "cozinha.jpg"):
        _foto(pasta / nome)
    for nome in ("tour-1.mp4", "tour-2.mp4"):
        fazer_video(pasta / nome, largura=180, altura=320, segundos=2.0)
    (pasta / "cenas.json").write_text(json.dumps(
        [{"arquivo": n, "descricao": n.split(".")[0]} for n in
         ("sala.jpg", "cozinha.jpg", "tour-1.mp4", "tour-2.mp4")]), encoding="utf-8")

    pagina.get_by_role("button", name="Um fundo e, por cima").click()
    pagina.get_by_role("button", name="Biblioteca de cenas").click()
    pagina.set_input_files('[data-envio="cenas"] input', str(pasta))
    ficha = pagina.get_by_label("dados da biblioteca de cenas")
    expect(ficha).to_contain_text("4 cenas (2 fotos)", timeout=30_000)
    pagina.get_by_role("button", name="Nada", exact=True).click()
    pagina.get_by_role("group", name="de onde vem o áudio").get_by_role(
        "button", name="Das cenas").click()
    editar = pagina.get_by_role("button", name="Editar vídeo")
    expect(editar).to_be_disabled()                      # nenhuma marcada ainda
    grupo = pagina.get_by_role("group", name="as cenas de onde vem o som")
    expect(grupo.get_by_role("button")).to_have_count(2)  # só os vídeos com som
    grupo.get_by_role("button", name=re.compile("^tour-2.mp4")).click()
    grupo.get_by_role("button", name=re.compile("^tour-1.mp4")).click()
    expect(grupo.get_by_role("button", name="tour-1.mp4, 2ª")).to_be_visible()
    # tirar a primeira: a outra vira a 1ª
    grupo.get_by_role("button", name="tour-2.mp4, 1ª").click()
    expect(grupo.get_by_role("button", name="tour-1.mp4, 1ª")).to_be_visible()
    grupo.get_by_role("button", name=re.compile("^tour-2.mp4")).click()

    pagina.get_by_role("button", name="Em pé (9:16)").click()
    resolucao = pagina.locator("label.campo", has_text="Resolução").locator("select")
    resolucao.select_option("480p")
    with pagina.expect_request(lambda r: r.url.split("?")[0].endswith("/api/tarefas")
                               and r.method == "POST") as pedido:
        editar.click()
    montagem = pedido.value.post_data_json["montagem"]
    assert montagem["audio_das_cenas"] == ["tour-1.mp4", "tour-2.mp4"]
    assert montagem["fala"] == "audio" and "audio_ids" not in montagem
    pagina.locator(".miniaturas img").first.wait_for(timeout=180_000)
    assert not _barrados(pagina), _barrados(pagina)
    assert not erros, erros


def test_gerar_e_revisar_a_matriz(navegador, endereco, tmp_path):
    """Uma pasta sem matriz: o Gemini (aqui, a IA de teste) descreve as cenas, a tabela
    mostra cada uma com a miniatura, a pessoa corrige uma descrição e usa a matriz."""
    pagina = navegador.new_page(viewport={"width": 1366, "height": 1100})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.goto(endereco)

    pasta = tmp_path / "minhas cenas"
    pasta.mkdir()
    for nome in ("c01-praia.mp4", "c02-carro.mp4", "c03-festa.mp4"):
        fazer_video(pasta / nome, largura=320, altura=180, segundos=1.0, com_audio=False)
    pagina.get_by_role("button", name="Um fundo e, por cima").click()
    pagina.get_by_role("button", name="Biblioteca de cenas").click()
    pagina.set_input_files('[data-envio="cenas"] input', str(pasta))
    gerar = pagina.get_by_role("button", name="Gerar a matriz")
    expect(gerar).to_be_visible(timeout=30_000)
    pagina.get_by_placeholder("do que são as cenas").fill("um jogo de corrida")
    gerar.click()
    revisao = pagina.get_by_role("region", name="revisão da matriz")
    expect(revisao).to_contain_text("3 cenas", timeout=30_000)
    expect(revisao).to_contain_text("IA de teste")
    expect(revisao.locator("img")).to_have_count(3)
    descricao = revisao.get_by_label("descrição de c02-carro.mp4")
    descricao.fill("Carro vermelho correndo na pista")
    revisao.get_by_label("monetização de c03-festa.mp4").select_option("evitar")
    with pagina.expect_download() as baixado:
        revisao.get_by_role("button", name="Baixar o cenas.json").click()
    import json as _json
    salvo = _json.loads(Path(baixado.value.path()).read_text(encoding="utf-8"))
    assert salvo[1]["descricao"] == "Carro vermelho correndo na pista"
    revisao.get_by_role("button", name="Usar esta matriz").click()
    ficha = pagina.get_by_label("dados da biblioteca de cenas")
    expect(ficha).to_contain_text("2 cenas", timeout=30_000)           # a festa ficou de fora
    expect(ficha).to_contain_text("1 marcada “evitar”")
    expect(revisao).to_have_count(0)
    # e dá para voltar à tabela com a matriz em uso
    pagina.get_by_role("button", name="Revisar a matriz").click()
    expect(pagina.get_by_label("descrição de c02-carro.mp4")).to_have_value(
        "Carro vermelho correndo na pista")
    assert not erros, erros


def test_presets_e_sons(navegador, endereco, tmp_path):
    """Escolher um preset muda os controles e o pedido; mexer num controle marca
    "Personalizado"; o "Ouvir" toca os sons do tema."""
    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.goto(endereco)

    presets = pagina.get_by_role("group", name="presets de edição")
    marcado = presets.locator('[aria-pressed="true"]')
    expect(marcado).to_have_text(re.compile("^Padrão"))
    presets.get_by_role("button", name=re.compile("^Short de gameplay")).click()
    expect(marcado).to_have_text(re.compile("^Short de gameplay"))
    tema = pagina.get_by_label("Tema dos sons")
    expect(tema).to_have_value("gameplay")
    expect(pagina.get_by_label("Letras por linha")).to_have_value("14")
    expect(pagina.get_by_label("Quadros por segundo")).to_have_value("60")
    expect(pagina.locator("label.interruptor", has_text="Som em cada corte")
           .locator("input")).to_be_checked()

    # mexer num controle: vira "Personalizado"; escolher de novo volta a marca
    pagina.get_by_label("Letras por linha").select_option("16")
    expect(marcado).to_have_count(0)
    expect(pagina.locator(".preset.personalizado")).to_have_attribute("aria-current", "true")
    presets.get_by_role("button", name=re.compile("^Short de gameplay")).click()
    expect(marcado).to_have_text(re.compile("^Short de gameplay"))

    with pagina.expect_request(lambda r: "/api/sons/gameplay.wav" in r.url) as pedido:
        pagina.get_by_role("button", name="Ouvir", exact=True).click()   # o dos sons
    assert "volume=1.20" in pedido.value.url                 # o volume do preset vai junto
    # O WebKit do Linux entrega o som ao GStreamer, e o Playwright não vê a resposta
    # (status 0): o arquivo é conferido à parte.
    resposta = pagina.request.get(pedido.value.url)
    assert resposta.status == 200 and resposta.headers["content-type"] == "audio/wav"

    video = fazer_video(tmp_path / "jogo.mp4", segundos=3.0)
    pagina.set_input_files("#passo-envio input[type=file]", str(video))
    pagina.locator(".ficha").wait_for(timeout=20_000)
    with pagina.expect_request(lambda r: r.url.split("?")[0].endswith("/api/tarefas")
                               and r.method == "POST") as pedido:
        pagina.get_by_role("button", name="Editar vídeo").click()
    corpo = pedido.value.post_data_json
    assert corpo["edicao"]["tema_dos_sons"] == "gameplay" and corpo["edicao"]["ritmo"] == 1.5
    assert corpo["edicao"]["som_nos_cortes"] is True and corpo["saida"]["fps"] == "60"
    pagina.locator(".miniaturas img").first.wait_for(timeout=120_000)
    # o preset de gameplay faz a thumbnail em pé
    assert list((tmp_path / "saida").glob("*-thumb-1080x1920.png"))
    assert not erros, erros


def test_plataformas_e_baixar(navegador, endereco, tmp_path):
    """A plataforma vem recomendada pelo formato do vídeo, decide o formato da thumbnail e
    mostra onde a capa é cortada; o "Baixar" entrega a capa antes mesmo de editar."""
    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.goto(endereco)

    pagina.set_input_files("#passo-envio input[type=file]", str(fazer_video(tmp_path / "jogo.mp4")))
    pagina.locator(".ficha").wait_for(timeout=20_000)
    onde = pagina.get_by_role("group", name="onde você vai postar")
    marcadas = onde.locator('[aria-pressed="true"]')
    expect(marcadas).to_have_count(3)
    for nome in ("YouTube Shorts", "TikTok", "Instagram Reels"):
        botao = onde.get_by_role("button", name=re.compile(f"^{nome}"))
        expect(botao).to_contain_text("recomendado")
    # a prévia é em pé e mostra os recortes: a busca do YouTube, o perfil e o feed
    expect(pagina.locator(".recorte")).to_have_count(3)
    expect(pagina.locator(".recortes")).to_contain_text(
        "o perfil do TikTok e o perfil do Instagram (3:4)")

    # Marcar o YouTube num vídeo em pé: um aviso, e um segundo formato para baixar.
    onde.get_by_role("button", name=re.compile("^YouTube recomendado|^YouTube$")).click()
    expect(pagina.locator(".plataformas .aviso")).to_contain_text("publica este vídeo como Short")
    expect(pagina.get_by_role("button", name=re.compile("^Baixar para"))).to_have_count(2)

    pagina.get_by_label("Chamada").fill("Teste das plataformas")
    with pagina.expect_download(timeout=60_000) as baixada:
        pagina.get_by_role("button", name="Baixar para Shorts, TikTok e Reels (1080×1920)").click()
    jpg = tmp_path / "capa.jpg"
    baixada.value.save_as(jpg)
    with Image.open(jpg) as im:
        assert im.format == "JPEG" and im.size == (1080, 1920)
    # antes de editar, leva o nome do vídeo enviado
    assert (tmp_path / "saida" / "jogo-thumb-1080x1920.png").is_file()
    expect(pagina.locator(".baixar-um small")).to_contain_text("jogo-thumb-1080x1920.jpg")

    # A última plataforma marcada não desmarca.
    for nome in ("YouTube", "YouTube Shorts", "TikTok", "Instagram Reels"):
        onde.get_by_role("button", name=re.compile(f"^{nome}( recomendado)?$")).click()
    expect(marcadas).to_have_count(1)
    expect(marcadas).to_have_text(re.compile("^Instagram Reels"))
    assert not erros, erros


def _pagina_vigiada(navegador, endereco):
    """Uma página sem o tour, que anota os erros do console e as violações da CSP."""
    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    pagina.add_init_script(VIGIAR_A_CSP)
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.goto(endereco)
    return pagina, erros


def _conferir_o_wav(pagina, pedido) -> None:
    """O WebKit do Linux entrega o som ao GStreamer e o Playwright não vê a resposta: o WAV
    é conferido à parte, pelo mesmo endereço."""
    wav = pagina.request.get(pedido.url)
    assert wav.status == 200 and wav.headers["content-type"] == "audio/wav"


def test_efeito_na_voz(navegador, endereco, tmp_path):
    """O efeito na voz no passo 2: um pronto marcado, o "ouvir antes" com 8 s da fala com o
    efeito, e a edição levando o efeito como texto e saindo inteira."""
    import sys

    pagina, erros = _pagina_vigiada(navegador, endereco)
    efeito = pagina.get_by_label("efeito na voz", exact=True)
    ouvir = efeito.get_by_role("button", name=re.compile("^Ouvir 8 s"))
    expect(ouvir).to_be_disabled()                       # sem fala, nada para ouvir
    expect(efeito).to_contain_text("Envie o vídeo para ouvir o efeito")
    pagina.set_input_files("#passo-envio input[type=file]",
                           str(fazer_video(tmp_path / "fala.mp4", segundos=4.0)))
    pagina.locator(".ficha").wait_for(timeout=20_000)
    expect(ouvir).to_be_enabled()

    esquilo = efeito.get_by_role("button", name="Esquilo", exact=True)
    esquilo.click()
    expect(esquilo).to_have_attribute("aria-pressed", "true")
    with pagina.expect_request(lambda r: "/api/efeitos/ouvir" in r.url) as pedido:
        efeito.get_by_role("button", name="Ouvir 8 s com o efeito").click()
    assert "efeito=tom%3D9%2Cagudos%3D2" in pedido.value.url
    assert "fonte=video%3A" in pedido.value.url
    _conferir_o_wav(pagina, pedido.value)
    if not (navegador.browser_type.name == "webkit" and sys.platform == "linux"):
        tocador = efeito.get_by_label("ouvir o efeito na voz")
        fim = time.monotonic() + 30
        # (o wait_for_function avalia texto na página, e a CSP do editor barra; o evaluate não)
        while (tocador.evaluate("a => a.duration") or 0) <= 3:
            assert time.monotonic() < fim, "o áudio do efeito não carregou"
            pagina.wait_for_timeout(200)

    with pagina.expect_request(lambda r: r.url.split("?")[0].endswith("/api/tarefas")
                               and r.method == "POST") as pedido:
        pagina.get_by_role("button", name="Editar vídeo").click()
    assert pedido.value.post_data_json["edicao"]["efeito_da_voz"] == "tom=9,agudos=2"
    pagina.locator(".miniaturas img").first.wait_for(timeout=120_000)
    assert list((tmp_path / "saida").glob("fala-editado.mp4"))
    assert not _barrados(pagina), _barrados(pagina)
    assert not erros, erros


def _deslizar(controle, ate: int) -> None:
    """Leva um controle deslizante até o valor pelas setas do teclado: cada tecla é um
    passo, e o React recebe os eventos como numa pessoa mexendo."""
    controle.focus()
    atual = int(controle.input_value())
    for _ in range(abs(ate - atual)):
        controle.press("ArrowRight" if ate > atual else "ArrowLeft")


def _esperar_o_b(pagina, efeito_esperado: str, acao):
    """Faz a ``acao`` e espera o pedido do B (com o efeito) que ela provoca."""
    alvo = "efeito=" + efeito_esperado.replace("=", "%3D").replace(",", "%2C") + "&"
    with pagina.expect_request(lambda r: "/api/efeitos/ouvir" in r.url and alvo in r.url,
                               timeout=15_000) as pedido:
        acao()
    return pedido.value


def test_estudio_de_voz(navegador, endereco, tmp_path):
    """O estúdio: a amostra do vídeo vira o A e o B; começar de um pronto e mexer num
    controle pede o B de novo; o A/B; salvar, renomear, duplicar, apagar, exportar e
    importar os seus; uma amostra por arquivo; e "Usar no vídeo" leva o efeito ao passo 2."""
    import json
    import sys

    from editor import efeitos_da_voz

    pagina, erros = _pagina_vigiada(navegador, endereco)
    pagina.on("dialog", lambda d: d.accept())                # o "apagar?" do navegador
    pagina.set_input_files("#passo-envio input[type=file]",
                           str(fazer_video(tmp_path / "fala.mp4", segundos=4.0)))
    pagina.locator(".ficha").wait_for(timeout=20_000)
    efeito = pagina.get_by_label("efeito na voz", exact=True)

    # abrir: o A (sem efeito) e o B saem da fala do vídeo
    with pagina.expect_request(lambda r: "/api/efeitos/ouvir" in r.url and "efeito=&" in r.url
                               ) as pedido_a:
        efeito.get_by_role("button", name="Abrir o estúdio").click()
    estudio = pagina.get_by_role("dialog", name="Estúdio de voz")
    expect(estudio).to_be_visible()
    assert "fonte=video%3A" in pedido_a.value.url and "segundos=8" in pedido_a.value.url
    _conferir_o_wav(pagina, pedido_a.value)
    expect(estudio.get_by_role("button", name="A fala do vídeo")).to_have_attribute(
        "aria-pressed", "true")

    # começar de um pronto e mexer na sala: o B é pedido de novo, com o efeito novo
    _esperar_o_b(pagina, "radio=85,distorcao=20",
                 lambda: estudio.get_by_label("começar de").select_option(label="Rádio antigo"))
    expect(estudio.get_by_label("o efeito como texto")).to_have_text("radio=85,distorcao=20")
    pedido_b = _esperar_o_b(pagina, "radio=85,distorcao=20,sala=30",
                            lambda: _deslizar(estudio.get_by_label("Sala", exact=True), 30))
    _conferir_o_wav(pagina, pedido_b)
    expect(estudio).to_contain_text("O B já é o efeito de agora", timeout=15_000)
    # a forma de onda desenhada (o WebKit do Linux pode não decodificar o som)
    if not (navegador.browser_type.name == "webkit" and sys.platform == "linux"):
        assert estudio.get_by_label("a forma de onda da amostra").evaluate(
            "c => c.getContext('2d').getImageData(0, 0, c.width, c.height).data.some(v => v)")
    comparar = estudio.get_by_role("group", name="comparar")
    sem = comparar.get_by_role("button", name="A · sem efeito")
    com = comparar.get_by_role("button", name="B · com efeito")
    sem.click()
    expect(sem).to_have_attribute("aria-pressed", "true")
    expect(com).to_have_attribute("aria-pressed", "false")

    # salvar, renomear pelo ✎, duplicar e apagar
    formulario = estudio.get_by_role("form", name="salvar o efeito")
    formulario.get_by_label("Nome do efeito").fill("Esquilo")
    formulario.get_by_role("button", name="Salvar").click()
    expect(estudio).to_contain_text("é o nome de um efeito pronto")
    formulario.get_by_label("Nome do efeito").fill("Meu locutor")
    formulario.get_by_role("button", name="Salvar").click()
    lista = estudio.get_by_label("os seus efeitos")
    expect(lista.get_by_role("listitem")).to_have_count(1)
    expect(lista).to_contain_text("radio=85,distorcao=20,sala=30")
    formulario.get_by_label("Nome do efeito").fill("Locutor 2")
    formulario.get_by_role("button", name="Salvar", exact=True).click()       # editando: renomeia
    expect(lista.get_by_role("listitem")).to_have_count(1)
    expect(lista).to_contain_text("Locutor 2")
    assert [e.titulo for e in efeitos_da_voz.meus()] == ["Locutor 2"]
    lista.get_by_role("button", name="duplicar o efeito Locutor 2").click()
    expect(formulario.get_by_label("Nome do efeito")).to_have_value("Locutor 2 (cópia)")
    formulario.get_by_role("button", name="Salvar", exact=True).click()
    expect(lista.get_by_role("listitem")).to_have_count(2)
    lista.get_by_role("button", name="apagar o efeito Locutor 2 (cópia)").click()
    expect(lista.get_by_role("listitem")).to_have_count(1)

    # exportar e importar
    with pagina.expect_download() as baixado:
        lista.get_by_role("link", name="Exportar os seus").click()
    exportado = json.loads(Path(baixado.value.path()).read_text(encoding="utf-8"))
    assert [e["titulo"] for e in exportado["efeitos"]] == ["Locutor 2"]
    outro = tmp_path / "de-um-amigo.json"
    amigo = {"efeitos": [{"titulo": "Do amigo", "efeito": "tom=-3,eco=40"}]}
    outro.write_text(json.dumps(amigo), encoding="utf-8")
    lista.get_by_label("importar efeitos").set_input_files(str(outro))
    expect(estudio.get_by_text("Entraram: Do amigo")).to_be_visible()
    expect(lista.get_by_role("listitem")).to_have_count(2)

    # uma amostra por arquivo: o A e o B passam a vir dela
    from tests.test_montagem import audio_wav

    with pagina.expect_request(lambda r: "/api/efeitos/ouvir" in r.url
                               and "fonte=audio%3A" in r.url):
        estudio.get_by_label("o arquivo da amostra").set_input_files(
            str(audio_wav(tmp_path / "amostra.wav", segundos=6.0, falas=((0.5, 5.5),))))
    expect(estudio.get_by_role("button", name="Um arquivo")).to_have_attribute(
        "aria-pressed", "true")

    # usar no vídeo: o diálogo fecha e o passo 2 marca o efeito (que é um seu)
    lista.get_by_role("button", name="editar o efeito Locutor 2").click()
    estudio.get_by_role("button", name="Usar no vídeo").click()
    expect(estudio).to_be_hidden()
    expect(efeito.get_by_role("button", name=re.compile("^Locutor 2"))).to_have_attribute(
        "aria-pressed", "true")
    # o ✎ da pílula abre o estúdio nele
    efeito.get_by_role("button", name="editar o efeito Locutor 2 no estúdio").click()
    expect(estudio.get_by_role("form", name="salvar o efeito").get_by_label("Nome do efeito")
           ).to_have_value("Locutor 2")
    pagina.keyboard.press("Escape")
    expect(estudio).to_be_hidden()
    assert not _barrados(pagina), _barrados(pagina)
    assert not erros, erros


def test_estudio_grava_a_amostra_no_microfone(navegador, endereco):
    """A amostra gravada no estúdio, pelo MediaRecorder: no Chromium, um microfone falso
    que toca bipes. A gravação sobe como um áudio e vira o A e o B."""
    if navegador.browser_type.name != "chromium":
        pytest.skip("só o Chromium tem o microfone falso")
    nav = navegador.browser_type.launch(args=["--use-fake-ui-for-media-stream",
                                              "--use-fake-device-for-media-stream"])
    try:
        pagina = nav.new_page()
        pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
        pagina.goto(endereco)
        pagina.get_by_label("efeito na voz", exact=True).get_by_role(
            "button", name="Abrir o estúdio").click()
        estudio = pagina.get_by_role("dialog", name="Estúdio de voz")
        # sem vídeo, a amostra começa pelo microfone
        expect(estudio.get_by_role("button", name="A fala do vídeo")).to_be_disabled()
        expect(estudio.get_by_role("button", name="Gravar agora")).to_have_attribute(
            "aria-pressed", "true")
        estudio.get_by_role("button", name="Gravar", exact=True).click()
        parar = estudio.get_by_role("button", name="Parar")
        expect(parar).to_be_visible()
        pagina.wait_for_timeout(2500)
        with pagina.expect_request(lambda r: "/api/efeitos/ouvir" in r.url
                                   and "fonte=audio%3A" in r.url, timeout=20_000):
            parar.click()
        expect(estudio).to_contain_text("Tocando a sua gravação")
        expect(estudio.get_by_role("button", name="Gravar de novo")).to_be_visible()
    finally:
        nav.close()


def test_a_chave_do_gemini_no_topo(navegador, endereco, monkeypatch):
    """Sem a chave, o campo dela aparece antes do passo 1 (três passos dependem dela), e o
    painel da thumbnail leva até ele."""
    from editor import ia

    monkeypatch.delenv(ia.VARIAVEL_FALSA)
    pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
    pagina.add_init_script("localStorage.setItem('editor-tour-visto', '1')")
    erros: list[str] = []
    pagina.on("pageerror", lambda e: erros.append(str(e)))
    pagina.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pagina.goto(endereco)

    secao = pagina.get_by_label("a chave do Gemini")
    campo = secao.get_by_label("chave do Gemini", exact=True)
    expect(campo).to_be_visible()
    expect(secao).to_contain_text("a matriz da biblioteca de cenas e os cartões animados")
    assert secao.bounding_box()["y"] < pagina.locator("#passo-envio").bounding_box()["y"]
    # o painel da IA, no passo 5, não tem mais o campo: ele leva até o do topo
    painel = pagina.locator("#painel-ia")
    expect(painel.get_by_label("chave do Gemini", exact=True)).to_have_count(0)
    painel.get_by_role("button", name="Colar a chave do Gemini no topo da página").click()
    expect(campo).to_be_focused()
    assert not erros, erros
