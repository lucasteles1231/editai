"""
O que o Editai baixa (editor/componentes.py) e a regra de quem usa: nada baixa sem o ok dela.

- o catálogo: os tamanhos, as licenças e o que é essencial;
- a trava: o Whisper, o auditor e o recorte param antes de baixar, sem chamar a rede;
- o ok: aprovado vale para os processos filhos, e o recusado (só o que tem reserva) não é
  perguntado de novo;
- o download com o andamento em bytes;
- o servidor: a edição sem o modelo responde 409 com o que falta, e o pedido refeito com o ok
  baixa antes, numa barra própria;
- as barras de cada parte da edição.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from editor import auditor, componentes, recorte, servidor, tarefas, transcricao
from tests.conftest import fazer_video
from tests.test_servidor import BASE, CABECA, PORTA, TOKEN, _enviar, _esperar


class TestOCatalogo:
    def test_os_ids_e_os_tamanhos(self):
        ids = [c.id for c in componentes.catalogo()]
        assert len(ids) == len(set(ids))
        for modelo in transcricao.MODELOS:
            c = componentes.pegar(f"whisper-{modelo}")
            assert c.essencial and c.bytes == componentes.BYTES_DO_WHISPER[modelo]
            assert c.licenca == "MIT" and c.link.endswith(f"faster-whisper-{modelo}")
        assert componentes.pegar("whisper-small").tamanho() == "486 MB"
        assert componentes.pegar("auditor").tamanho() == "412 MB"
        assert componentes.pegar("recorte").tamanho() == "26 MB"

    def test_os_sons_tem_reserva_e_os_motores_se_instalam_a_parte(self):
        sons = componentes.pegar("sons-noticia")
        assert not sons.essencial and 0 < sons.bytes < 1_000_000
        for id_ in ("ia-local", "voz-local", "motor-de-voz"):
            c = componentes.pegar(id_)
            assert c.a_parte and c.tamanho() == c.tamanho_escrito

    def test_o_dicionario_para_a_pagina(self):
        d = componentes.pegar("whisper-small").para_dict()
        assert set(d) == {"id", "nome", "para_que", "bytes", "tamanho", "licenca", "link",
                          "essencial", "a_parte", "instalado"}
        assert d["instalado"]                  # com o transcritor falso dos testes

    def test_desconhecido(self):
        with pytest.raises(KeyError):
            componentes.pegar("nada")


@pytest.fixture
def sem_whisper(monkeypatch):
    """O transcritor de verdade, com o modelo fora do computador (e a rede trocada)."""
    monkeypatch.delenv(transcricao.VARIAVEL_FALSA, raising=False)
    monkeypatch.setattr(transcricao, "modelo_baixado", lambda modelo="small": False)


class TestATrava:
    def test_exigir_sem_o_ok(self, sem_whisper):
        with pytest.raises(componentes.PrecisaDeOk) as erro:
            componentes.exigir("whisper-small")
        assert [c.id for c in erro.value.faltam] == ["whisper-small"]
        d = erro.value.para_dict()
        assert d["bytes"] == componentes.BYTES_DO_WHISPER["small"] and d["tamanho"] == "486 MB"
        assert "486 MB" in d["detail"]

    def test_aprovado_passa_e_vai_para_os_filhos(self, sem_whisper):
        componentes.aprovar(["whisper-small"])
        componentes.exigir("whisper-small")
        import os

        assert "whisper-small" in os.environ[componentes.VARIAVEL].split(",")
        assert not componentes.aprovado("auditor")
        componentes.aprovar([componentes.TUDO])
        assert componentes.aprovado("auditor")

    def test_a_transcricao_para_antes_de_baixar(self, sem_whisper, monkeypatch, tmp_path):
        criados = []

        class Modelo:
            def __init__(self, *args, **kwargs):
                criados.append(kwargs)

        import faster_whisper

        monkeypatch.setattr(faster_whisper, "WhisperModel", Modelo)
        audio = fazer_video(tmp_path / "x.mp4", segundos=1.0, falas=[(0.1, 0.8)])
        with pytest.raises(componentes.PrecisaDeOk):
            transcricao.transcrever(audio)
        assert criados == []                   # nem chegou a abrir (e baixar) o modelo

    def test_o_auditor_para_antes_de_baixar(self, monkeypatch):
        monkeypatch.delenv(auditor.VARIAVEL_FALSA, raising=False)
        chamadas = []

        def hf_hub_download(repo, nome, revision=None, local_files_only=False, **kwargs):
            chamadas.append(local_files_only)
            raise FileNotFoundError(nome)      # não está no cache

        import huggingface_hub

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", hf_hub_download)
        with pytest.raises(componentes.PrecisaDeOk):
            auditor.preparar(["um cachorro"])
        assert chamadas and all(chamadas)       # só olhou o cache: nada da rede

    def test_o_recorte_para_antes_de_baixar(self, monkeypatch):
        monkeypatch.delenv(recorte.VARIAVEL_FALSA, raising=False)
        monkeypatch.setattr(recorte, "_sessao", None)
        monkeypatch.setattr(recorte, "modelo_baixado", lambda: False)
        with pytest.raises(componentes.PrecisaDeOk):
            recorte.preparar_modelo()

    def test_recusar_vale_so_para_o_que_tem_reserva(self, monkeypatch):
        monkeypatch.setattr(componentes, "_recusados", set())
        monkeypatch.setattr(componentes, "instalado", lambda id_: False)
        assert [c.id for c in componentes.faltando(["whisper-small", "sons-noticia"])] == [
            "whisper-small", "sons-noticia"]
        componentes.recusar(["whisper-small", "sons-noticia"])
        assert [c.id for c in componentes.faltando(["whisper-small", "sons-noticia"])] == [
            "whisper-small"]
        componentes.aprovar(["sons-noticia"])     # mudou de ideia
        assert not componentes.recusado("sons-noticia")


class TestOQueAEdicaoUsa:
    def test_o_whisper_o_recorte_e_os_sons_do_tema(self):
        from editor.montagem import Montagem
        from editor.opcoes import OpcoesDeEdicao

        assert componentes.da_edicao(OpcoesDeEdicao()) == ["whisper-small"]
        noticia = OpcoesDeEdicao(modelo="base", tema_dos_sons="noticia")
        assert componentes.da_edicao(noticia) == ["whisper-base", "sons-noticia"]
        mudo = OpcoesDeEdicao(tema_dos_sons="noticia", sons=False)
        assert componentes.da_edicao(mudo) == ["whisper-small"]
        m = Montagem("fundo.mp4", pessoa="eu.mp4", recorte="modnet")
        assert "recorte" in componentes.da_edicao(OpcoesDeEdicao(), m)
        sem_fundo = Montagem("fundo.mp4", pessoa="eu.mp4", recorte="transparente")
        assert "recorte" not in componentes.da_edicao(OpcoesDeEdicao(), sem_fundo)


class TestBaixar:
    def test_o_andamento_em_bytes(self, sem_whisper, monkeypatch):
        import huggingface_hub

        baixados = []

        def hf_hub_download(repo, nome, revision=None, tqdm_class=None, **kwargs):
            baixados.append((repo, nome, revision))
            barra = tqdm_class(total=100, unit="B")
            barra.update(componentes.BYTES_DO_WHISPER["tiny"] // len(
                transcricao.ARQUIVOS_DO_MODELO))
            barra.close()
            return f"/cache/{nome}"

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", hf_hub_download)
        andou: list[float] = []
        with pytest.raises(componentes.PrecisaDeOk):
            componentes.baixar("whisper-tiny", lambda f, texto: andou.append(f))
        assert baixados == [] and andou == []
        componentes.aprovar(["whisper-tiny"])
        componentes.baixar("whisper-tiny", lambda f, texto: andou.append(f))
        assert [b[1] for b in baixados] == list(transcricao.ARQUIVOS_DO_MODELO)
        assert {b[2] for b in baixados} == {transcricao.REVISOES["tiny"]}
        assert andou[0] == 0.0 and andou[-1] == 1.0 and andou == sorted(andou)

    def test_cancelar_no_meio(self, sem_whisper, monkeypatch):
        import huggingface_hub

        def hf_hub_download(repo, nome, revision=None, tqdm_class=None, **kwargs):
            tqdm_class(total=10).update(5)

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", hf_hub_download)
        componentes.aprovar(["whisper-tiny"])
        with pytest.raises(InterruptedError):
            componentes.baixar("whisper-tiny", cancelar=lambda: True)

    def test_os_motores_a_parte_tem_o_botao_deles(self, monkeypatch):
        monkeypatch.setattr(componentes, "instalado", lambda id_: False)
        componentes.aprovar(["ia-local"])
        with pytest.raises(ValueError, match="botão"):
            componentes.baixar("ia-local")


@pytest.fixture
def cliente(tmp_path):
    app = servidor.criar_app(TOKEN, porta=PORTA, pasta_saida=tmp_path / "saida")
    with TestClient(app, base_url=BASE) as c:
        yield c


class TestNoServidor:
    def test_sem_o_modelo_pede_o_ok_e_nada_baixa(self, cliente, tmp_path, monkeypatch):
        baixados = []
        monkeypatch.setattr(componentes, "instalado",
                            lambda id_: id_ != "whisper-small")
        monkeypatch.setattr(componentes, "baixar",
                            lambda id_, andamento=None, cancelar=None: baixados.append(id_))
        v = _enviar(cliente, fazer_video(tmp_path / "x.mp4", segundos=2.0))
        r = cliente.post("/api/tarefas", headers=CABECA, json={"video_id": v["id"]})
        assert r.status_code == 409, r.text
        d = r.json()
        assert [c["id"] for c in d["precisa_de_ok"]] == ["whisper-small"]
        assert d["tamanho"] == "486 MB" and d["precisa_de_ok"][0]["licenca"] == "MIT"
        assert baixados == [] and not cliente.get("/api/estado", headers=CABECA).json()["ocupado"]

    def test_com_o_ok_baixa_antes_numa_barra_propria(self, cliente, tmp_path, monkeypatch):
        baixados = []
        instalados = {"whisper-small": False}
        monkeypatch.setattr(componentes, "instalado", lambda id_: instalados.get(id_, True))

        def baixar(id_, andamento=None, cancelar=None):
            for f in (0.0, 0.5, 1.0):
                andamento(f, f"{int(f * 100)}%")
            baixados.append(id_)
            instalados[id_] = True

        monkeypatch.setattr(componentes, "baixar", baixar)
        v = _enviar(cliente, fazer_video(tmp_path / "x.mp4", segundos=2.0))
        r = cliente.post("/api/tarefas", headers={**CABECA, "X-Editai-Aprovados": "whisper-small"},
                         json={"video_id": v["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["partes"][0]["id"] == "baixar:whisper-small"
        t = _esperar(cliente, r.json()["id"])
        assert t["estado"] == "pronto", t
        assert baixados == ["whisper-small"]
        estados = {p["id"]: p["estado"] for p in t["partes"]}
        assert estados["baixar:whisper-small"] == "pronto" and estados["desenhando"] == "pronto"

    def test_o_som_com_reserva_pode_ser_recusado(self, cliente, tmp_path, monkeypatch):
        monkeypatch.setattr(componentes, "_recusados", set())
        monkeypatch.setattr(componentes, "instalado", lambda id_: id_ != "sons-noticia")
        v = _enviar(cliente, fazer_video(tmp_path / "x.mp4", segundos=2.0))
        pedido = {"video_id": v["id"], "edicao": {"tema_dos_sons": "noticia"}}
        r = cliente.post("/api/tarefas", headers=CABECA, json=pedido)
        assert r.status_code == 409
        falta = r.json()["precisa_de_ok"][0]
        assert falta["id"] == "sons-noticia" and falta["essencial"] is False
        r = cliente.post("/api/tarefas", headers={**CABECA, "X-Editai-Recusados": "sons-noticia"},
                         json=pedido)
        assert r.status_code == 200, r.text
        assert _esperar(cliente, r.json()["id"])["estado"] == "pronto"

    def test_o_cabecalho_sem_token_nao_aprova(self, cliente):
        r = cliente.get("/api/estado", headers={"X-Editai-Aprovados": "*"})
        assert r.status_code == 401 and not componentes.aprovado("auditor")

    def test_id_desconhecido_e_ignorado(self, cliente):
        cliente.get("/api/estado", headers={**CABECA, "X-Editai-Aprovados": "nada,auditor"})
        assert componentes.aprovados() == {"auditor"}

    def test_o_estado_lista_o_catalogo(self, cliente):
        d = cliente.get("/api/estado", headers=CABECA).json()
        assert {c["id"] for c in d["componentes"]} == {c.id for c in componentes.catalogo()}


class TestAsBarras:
    def _tarefa(self, tmp_path, baixar=()):
        from editor import saida as saida_mod
        from editor.opcoes import OpcoesDeEdicao

        return tarefas.Tarefa(tmp_path / "x.mp4", tmp_path / "y.mp4", OpcoesDeEdicao(),
                              saida_mod.OpcoesDeSaida(), baixar=list(baixar))

    def test_uma_parte_para_cada_etapa(self, tmp_path):
        t = self._tarefa(tmp_path)
        assert [p.id for p in t.partes] == list(tarefas.ETAPAS)
        t.andar("transcrevendo", 0.5)
        assert t.total() == pytest.approx(0.175)
        t.andar("desenhando", 0.0)               # a escolha das frases não rodou
        estados = {p.id: p.estado for p in t.partes}
        assert estados == {"transcrevendo": "pronto", "cortando": "pulada",
                           "escolhendo": "pulada", "desenhando": "rodando",
                           "finalizando": "esperando"}

    def test_a_etapa_que_volta(self, tmp_path):
        t = self._tarefa(tmp_path)
        t.andar("cortando", 1.0)
        t.andar("escolhendo", 0.2)
        t.andar("cortando", 0.0)
        assert t.parte("cortando").estado == "rodando"

    def test_os_downloads_pesam_pelos_bytes(self, tmp_path):
        t = self._tarefa(tmp_path, ["whisper-small", "recorte"])
        assert [p.id for p in t.partes[:2]] == ["baixar:whisper-small", "baixar:recorte"]
        assert t.partes[0].nome == "Baixando o Whisper small (486 MB)"
        t.andar("baixar:whisper-small", 1.0)
        pequeno = componentes.BYTES_DO_RECORTE
        grande = componentes.BYTES_DO_WHISPER["small"]
        assert t.total() == pytest.approx(tarefas.PESO_DOS_DOWNLOADS * grande / (grande + pequeno))
        t.andar("transcrevendo", 0.0)
        assert t.total() == pytest.approx(tarefas.PESO_DOS_DOWNLOADS)
        assert t.parte("baixar:recorte").estado == "pulada"

    def test_quanto_falta_em_cada_parte(self, tmp_path, monkeypatch):
        relogio = [100.0]
        monkeypatch.setattr(time, "monotonic", lambda: relogio[0])
        t = self._tarefa(tmp_path)
        t.andar("transcrevendo", 0.02)
        assert t.parte("transcrevendo").falta_s() is None        # cedo demais
        relogio[0] = 110.0
        t.andar("transcrevendo", 0.25)
        assert t.parte("transcrevendo").falta_s() == pytest.approx(30.0)
        assert t.para_dict()["partes"][0]["falta_s"] == pytest.approx(30.0)

    def test_o_erro_fica_na_parte(self, tmp_path, monkeypatch):
        from editor import render

        def quebrar(*args, progresso=None, **kwargs):
            progresso("transcrevendo", 0.3, "")
            raise RuntimeError("o disco encheu")

        monkeypatch.setattr(render, "editar", quebrar)
        t = self._tarefa(tmp_path)
        g = tarefas.Gerente()
        g._rodar(t)
        assert t.estado == "erro" and t.parte("transcrevendo").estado == "erro"
        assert "o disco encheu" in t.parte("transcrevendo").detalhe
        assert t.parte("desenhando").estado == "esperando"


class TestNoTerminal:
    @pytest.fixture
    def sem_o_modelo(self, monkeypatch):
        instalados = {"whisper-small": False}
        baixados: list[str] = []
        monkeypatch.setattr(componentes, "instalado", lambda id_: instalados.get(id_, True))

        def baixar(id_, andamento=None, cancelar=None):
            andamento(1.0, "486 MB")
            baixados.append(id_)
            instalados[id_] = True

        monkeypatch.setattr(componentes, "baixar", baixar)
        return baixados

    def test_com_sim_aprova_baixa_e_edita(self, tmp_path, sem_o_modelo, capsys):
        from editor import cli

        video = fazer_video(tmp_path / "x.mp4", segundos=2.0)
        assert cli.main([str(video), "--sim"]) == 0
        saida = capsys.readouterr().out
        assert "o Whisper small, 486 MB" in saida and "(--sim: aprovado)" in saida
        assert sem_o_modelo == ["whisper-small"] and (tmp_path / "x-editado.mp4").is_file()

    def test_sem_ninguem_para_responder_nao_baixa(self, tmp_path, sem_o_modelo, capsys,
                                                 monkeypatch):
        from editor import cli

        monkeypatch.setattr("sys.stdin", None)
        video = fazer_video(tmp_path / "x.mp4", segundos=2.0)
        assert cli.main([str(video)]) == 1
        saida = capsys.readouterr().out
        assert "rode de novo com --sim" in saida and "Nada foi baixado" in saida
        assert sem_o_modelo == [] and not (tmp_path / "x-editado.mp4").exists()

    def test_a_pergunta(self, monkeypatch, capsys):
        from editor import cli

        monkeypatch.setattr(componentes, "_recusados", set())

        class Terminal:
            @staticmethod
            def isatty():
                return True

        monkeypatch.setattr("sys.stdin", Terminal)
        faltam = [componentes.pegar("whisper-small"), componentes.pegar("sons-noticia")]
        assert not cli._ok_para_baixar(faltam, sim=False, perguntar=lambda texto: "n")
        assert componentes.recusado("sons-noticia") and not componentes.aprovado("whisper-small")
        perguntas: list[str] = []
        assert cli._ok_para_baixar(faltam, sim=False,
                                   perguntar=lambda texto: perguntas.append(texto) or "s")
        assert perguntas == [f"Aprovar e baixar {componentes.legivel(sum(c.bytes for c in faltam))}"
                             "? [s/N] "]
        assert componentes.aprovado("whisper-small") and componentes.aprovado("sons-noticia")
        assert "— opcional" in capsys.readouterr().out

    def test_o_pedido_do_meio_do_caminho_recomeca(self, monkeypatch):
        from editor import cli

        rodadas: list[int] = []

        def executar(a):
            rodadas.append(1)
            componentes.exigir("auditor")
            return 0

        monkeypatch.setattr(componentes, "instalado", lambda id_: False)
        monkeypatch.setattr(cli, "_executar", executar)
        assert cli.main(["--sim"]) == 0
        assert len(rodadas) == 2 and componentes.aprovado("auditor")


class TestTirar:
    def test_sai_so_a_pasta_do_modelo(self, cliente, tmp_path, monkeypatch):
        from editor import desinstalar

        cache = tmp_path / "hf"
        monkeypatch.setattr(desinstalar, "cache_do_hugging_face", lambda: cache)
        blobs = cache / "models--Xenova--modnet" / "blobs"
        blobs.mkdir(parents=True)
        (blobs / "modelo").write_bytes(b"1" * 100)
        de_outro = cache / "models--outro--programa"
        de_outro.mkdir()
        componentes.aprovar(["recorte", "auditor"])
        r = cliente.delete("/api/componentes/recorte", headers=CABECA)
        assert r.status_code == 200, r.text
        assert r.json()["saiu"] == 100 and {c["id"] for c in r.json()["componentes"]} >= {"recorte"}
        assert not (cache / "models--Xenova--modnet").exists() and de_outro.exists()
        assert not componentes.aprovado("recorte") and componentes.aprovado("auditor")

    def test_os_sons_do_tema(self, cliente):
        from editor import sons

        for nome in sons.catalogo()["baixados"]:
            (sons.pasta_dos_baixados() / f"{nome}.wav").write_bytes(b"RIFF")
        (sons.pasta_dos_baixados() / "outro.wav").write_bytes(b"RIFF")
        r = cliente.delete("/api/componentes/sons-noticia", headers=CABECA)
        assert r.status_code == 200 and r.json()["saiu"] == 4 * len(sons.catalogo()["baixados"])
        assert [p.name for p in sons.pasta_dos_baixados().iterdir()] == ["outro.wav"]

    def test_o_motor_a_parte_e_o_desconhecido(self, cliente):
        assert cliente.delete("/api/componentes/ia-local", headers=CABECA).status_code == 400
        assert cliente.delete("/api/componentes/nada", headers=CABECA).status_code == 404
        assert cliente.get("/api/componentes", headers=CABECA).json()["componentes"]
