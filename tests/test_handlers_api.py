import json
import logging

import pytest

from conftest import carregar_handler


def evento_http(route_key, body=None, path=None, query=None):
    evento = {
        "version": "2.0",
        "routeKey": route_key,
        "rawPath": "/",
        "headers": {},
        "isBase64Encoded": False,
    }
    if body is not None:
        evento["body"] = body if isinstance(body, str) else json.dumps(body)
    if path:
        evento["pathParameters"] = path
    if query:
        evento["queryStringParameters"] = query
    return evento


@pytest.fixture
def api(ctx, monkeypatch):
    monkeypatch.setenv("TABELA_LIVROS", "Livros")
    monkeypatch.setenv("TABELA_INTERESSES", "Interesses")
    monkeypatch.setenv("TABELA_VENDAS", "Vendas")
    monkeypatch.setenv("TOPICO_SNS", ctx.topico_sns)
    handlers = {
        nome: carregar_handler(nome)
        for nome in (
            "listar_livros",
            "gerenciar_estoque",
            "registrar_interesse",
            "registrar_venda",
        )
    }

    def chamar(nome, route_key, **kw):
        resp = handlers[nome].lambda_handler(evento_http(route_key, **kw), None)
        assert resp["headers"]["Content-Type"] == "application/json"
        return resp["statusCode"], json.loads(resp["body"])

    return chamar


def cadastrar(api, quantidade=1, preco=19.9):
    status, corpo = api(
        "gerenciar_estoque",
        "POST /livros",
        body={"titulo": "Dom Casmurro", "autor": "Machado", "preco": preco,
              "quantidade": quantidade},
    )
    assert status == 201
    return corpo["livroId"]


def test_fluxo_api_completo(api):
    livro_id = cadastrar(api)
    status, lista = api("listar_livros", "GET /livros")
    assert status == 200
    assert [l["livroId"] for l in lista] == [livro_id]
    assert lista[0]["disponivel"] == 1

    status, corpo = api(
        "registrar_interesse", "POST /interesses",
        body={"livroId": livro_id, "email": "a@b.com"},
    )
    assert status == 201
    assert corpo["status"] == "RESERVADO"

    status, reservas = api(
        "registrar_venda", "GET /reservas", query={"livroId": livro_id}
    )
    assert status == 200
    assert len(reservas) == 1

    status, corpo = api(
        "registrar_venda", "POST /vendas",
        body={"livroId": livro_id, "ordem": reservas[0]["ordem"]},
    )
    assert status == 201
    assert corpo["vendaId"]


def test_chegada_retorna_livro_atualizado(api):
    livro_id = cadastrar(api)
    status, corpo = api(
        "gerenciar_estoque", "POST /livros/{id}/chegada",
        body={"quantidade": 2}, path={"id": livro_id},
    )
    assert status == 200
    assert corpo["quantidade"] == 3


def test_listar_livros_serializa_decimal(api):
    cadastrar(api, quantidade=1, preco=19.9)
    _, lista = api("listar_livros", "GET /livros")
    assert lista[0]["preco"] == 19.9
    assert lista[0]["quantidade"] == 1
    assert isinstance(lista[0]["quantidade"], int)


LIVRO_OK = {"titulo": "T", "autor": "A", "preco": 10, "quantidade": 1}


@pytest.mark.parametrize(
    "body",
    [
        None,
        "{",
        "[]",
        {**LIVRO_OK, "quantidade": "2"},
        {**LIVRO_OK, "quantidade": 1.5},
        {**LIVRO_OK, "quantidade": True},
        {**LIVRO_OK, "preco": -1},
        {**LIVRO_OK, "preco": "10"},
        {"titulo": "T"},
    ],
)
def test_entradas_invalidas_retornam_400(api, body):
    status, corpo = api("gerenciar_estoque", "POST /livros", body=body)
    assert status == 400
    assert corpo["erro"]


def test_email_invalido_retorna_400(api):
    livro_id = cadastrar(api)
    status, _ = api(
        "registrar_interesse", "POST /interesses",
        body={"livroId": livro_id, "email": "invalido"},
    )
    assert status == 400


def test_reservas_sem_livro_id_retorna_400(api):
    assert api("registrar_venda", "GET /reservas")[0] == 400
    assert api("registrar_venda", "GET /reservas", query={"livroId": ""})[0] == 400


def test_rota_desconhecida_retorna_404(api):
    assert api("listar_livros", "GET /outra")[0] == 404


def test_codigos_de_erro(api):
    status, _ = api(
        "registrar_interesse", "POST /interesses",
        body={"livroId": "nao-existe", "email": "a@b.com"},
    )
    assert status == 404

    livro_id = cadastrar(api)
    corpo = {"livroId": livro_id, "email": "a@b.com"}
    assert api("registrar_interesse", "POST /interesses", body=corpo)[0] == 201
    assert api("registrar_interesse", "POST /interesses", body=corpo)[0] == 409

    _, reservas = api("registrar_venda", "GET /reservas", query={"livroId": livro_id})
    venda = {"livroId": livro_id, "ordem": reservas[0]["ordem"]}
    assert api("registrar_venda", "POST /vendas", body=venda)[0] == 201
    assert api("registrar_venda", "POST /vendas", body=venda)[0] == 409


def test_erro_inesperado_retorna_500(api, monkeypatch, caplog):
    def falha(ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr("sebo.livros.listar", falha)
    with caplog.at_level(logging.ERROR):
        status, corpo = api("listar_livros", "GET /livros")
    assert status == 500
    assert corpo == {"erro": "erro interno"}
    assert "boom" in caplog.text


@pytest.mark.parametrize("quantidade", [0, "2", 1.5, True])
def test_chegada_com_quantidade_invalida_retorna_400(api, quantidade):
    livro_id = cadastrar(api)
    status, _ = api(
        "gerenciar_estoque", "POST /livros/{id}/chegada",
        body={"quantidade": quantidade}, path={"id": livro_id},
    )
    assert status == 400
