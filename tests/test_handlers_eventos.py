import dataclasses
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from conftest import carregar_handler, inserir_pendente
from sebo import fila, livros


@pytest.fixture(autouse=True)
def ambiente(ctx, monkeypatch):
    monkeypatch.setenv("TABELA_LIVROS", "Livros")
    monkeypatch.setenv("TABELA_INTERESSES", "Interesses")
    monkeypatch.setenv("TABELA_VENDAS", "Vendas")
    monkeypatch.setenv("TOPICO_SNS", ctx.topico_sns)
    monkeypatch.setenv("PRAZO_RESERVA_MINUTOS", "0")


def registro(nome, livro_id, novo=None, antigo=None):
    dyn = {"Keys": {"livroId": {"S": livro_id}}}
    if novo is not None:
        dyn["NewImage"] = {"livroId": {"S": livro_id},
                           "disponivel": {"N": str(novo)}}
    if antigo is not None:
        dyn["OldImage"] = {"livroId": {"S": livro_id},
                           "disponivel": {"N": str(antigo)}}
    return {"eventName": nome, "dynamodb": dyn}


def status_de(ctx, livro_id):
    itens = ctx.dynamodb.query(
        TableName=ctx.tabela_interesses,
        KeyConditionExpression="livroId = :l",
        ExpressionAttributeValues={":l": {"S": livro_id}},
    )["Items"]
    return [i["status"]["S"] for i in itens]


def livro_com_pendentes(ctx, n):
    livro_id = livros.cadastrar(ctx, "T", "A", Decimal("10"), 0)
    agora = datetime.now(timezone.utc)
    for i in range(n):
        inserir_pendente(ctx, livro_id, f"u{i}@b.com", agora)
    return livro_id


def test_stream_aumento_de_disponivel_aloca(ctx):
    livro_id = livro_com_pendentes(ctx, 2)
    ctx.dynamodb.update_item(
        TableName="Livros", Key={"livroId": {"S": livro_id}},
        UpdateExpression="SET disponivel = :d, quantidade = :d",
        ExpressionAttributeValues={":d": {"N": "2"}},
    )
    h = carregar_handler("alocar_reservas")
    evento = {"Records": [
        registro("MODIFY", livro_id, novo=2, antigo=0),
        registro("MODIFY", livro_id, novo=2, antigo=0),
    ]}
    assert h.lambda_handler(evento, None) == {"alocados": 2}
    assert status_de(ctx, livro_id) == ["RESERVADO", "RESERVADO"]


def test_stream_diminuicao_ignorada(ctx):
    livro_id = livro_com_pendentes(ctx, 1)
    h = carregar_handler("alocar_reservas")
    evento = {"Records": [registro("MODIFY", livro_id, novo=0, antigo=1)]}
    assert h.lambda_handler(evento, None) == {"alocados": 0}
    assert status_de(ctx, livro_id) == ["PENDENTE"]


def test_stream_remove_ignorado(ctx):
    livro_id = livro_com_pendentes(ctx, 1)
    h = carregar_handler("alocar_reservas")
    evento = {"Records": [registro("REMOVE", livro_id, antigo=3)]}
    assert h.lambda_handler(evento, None) == {"alocados": 0}
    assert status_de(ctx, livro_id) == ["PENDENTE"]


def test_agendamento_expira_vencidas(ctx):
    livro_id = livros.cadastrar(ctx, "T", "A", Decimal("10"), 1)
    ctx0 = dataclasses.replace(ctx, prazo_reserva=ctx.prazo_reserva * 0)
    r = fila.registrar_interesse(ctx0, livro_id, "a@b.com",
                                 datetime.now(timezone.utc))
    assert r["status"] == "RESERVADO"
    h = carregar_handler("expirar_reservas")
    assert h.lambda_handler({}, None) == {"expirados": 1}
    assert status_de(ctx, livro_id) == ["EXPIRADO"]
