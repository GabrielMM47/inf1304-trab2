from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from sebo import fila, livros, reservas
from sebo.erros import ReservaInativa
from tests.conftest import inserir_pendente

AGORA = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


def _item(ctx, livro_id, ordem):
    resp = ctx.dynamodb.get_item(
        TableName=ctx.tabela_interesses,
        Key={"livroId": {"S": livro_id}, "ordem": {"S": ordem}},
        ConsistentRead=True,
    )
    return fila._para_dict(resp["Item"])


def _vendas(ctx):
    return ctx.dynamodb.scan(TableName=ctx.tabela_vendas)["Items"]


def _reservar(ctx, quantidade=1, email="ana@x.com"):
    livro_id = livros.cadastrar(ctx, "Dom Casmurro", "Machado", Decimal("25.50"), quantidade)
    r = fila.registrar_interesse(ctx, livro_id, email, AGORA)
    assert r["status"] == "RESERVADO"
    return livro_id, r["ordem"]


def test_expirar_libera_exemplar_e_avisa(ctx, emails):
    livro_id, ordem = _reservar(ctx)
    emails()
    expirados = reservas.expirar_vencidas(ctx, AGORA + timedelta(minutes=3))
    assert [e["ordem"] for e in expirados] == [ordem]
    assert _item(ctx, livro_id, ordem)["status"] == "EXPIRADO"
    assert livros.obter(ctx, livro_id)["disponivel"] == 1
    msgs = emails()
    assert len(msgs) == 1
    assert msgs[0]["email"] == "ana@x.com"
    assert "Reserva expirada" in msgs[0]["assunto"]


def test_expirar_nao_toca_reservas_no_prazo(ctx, emails):
    livro_id, ordem = _reservar(ctx)
    emails()
    assert reservas.expirar_vencidas(ctx, AGORA + timedelta(minutes=1)) == []
    assert _item(ctx, livro_id, ordem)["status"] == "RESERVADO"
    assert livros.obter(ctx, livro_id)["disponivel"] == 0
    assert emails() == []


def test_expirar_e_alocar_passa_para_o_proximo(ctx):
    livro_id, ordem_ana = _reservar(ctx)
    ordem_bruno = inserir_pendente(ctx, livro_id, "bruno@x.com", AGORA + timedelta(seconds=1))
    depois = AGORA + timedelta(minutes=3)
    reservas.expirar_vencidas(ctx, depois)
    assert _item(ctx, livro_id, ordem_bruno)["status"] == "PENDENTE"
    fila.alocar(ctx, livro_id, depois)
    assert _item(ctx, livro_id, ordem_bruno)["status"] == "RESERVADO"
    assert _item(ctx, livro_id, ordem_ana)["status"] == "EXPIRADO"


def test_vender_reserva_ativa(ctx):
    livro_id, ordem = _reservar(ctx)
    venda_id = reservas.vender(ctx, livro_id, ordem, AGORA + timedelta(minutes=1))
    assert _item(ctx, livro_id, ordem)["status"] == "VENDIDO"
    livro = livros.obter(ctx, livro_id)
    assert livro["quantidade"] == 0
    assert livro["disponivel"] == 0
    vendas = _vendas(ctx)
    assert len(vendas) == 1
    v = vendas[0]
    assert v["vendaId"]["S"] == venda_id
    assert v["livroId"]["S"] == livro_id
    assert v["email"]["S"] == "ana@x.com"
    assert Decimal(v["preco"]["N"]) == Decimal("25.50")
    assert v["ordemInteresse"]["S"] == ordem
    assert "data" in v


def test_vender_reserva_vencida_nao_varrida_recusa(ctx):
    livro_id, ordem = _reservar(ctx)
    with pytest.raises(ReservaInativa):
        reservas.vender(ctx, livro_id, ordem, AGORA + timedelta(minutes=3))
    assert _item(ctx, livro_id, ordem)["status"] == "RESERVADO"
    assert _vendas(ctx) == []


def test_vender_duas_vezes_recusa_a_segunda(ctx):
    livro_id, ordem = _reservar(ctx, quantidade=2)
    reservas.vender(ctx, livro_id, ordem, AGORA + timedelta(minutes=1))
    with pytest.raises(ReservaInativa):
        reservas.vender(ctx, livro_id, ordem, AGORA + timedelta(minutes=1))
    assert livros.obter(ctx, livro_id)["quantidade"] == 1
    assert len(_vendas(ctx)) == 1


def test_vender_interesse_inexistente(ctx):
    livro_id = livros.cadastrar(ctx, "Livro", "Autor", Decimal("10"), 1)
    with pytest.raises(ReservaInativa):
        reservas.vender(ctx, livro_id, "nao-existe", AGORA)


def test_listar_ativas_somente_reservados(ctx):
    livro_id, ordem_ana = _reservar(ctx, quantidade=2)
    r2 = fila.registrar_interesse(ctx, livro_id, "bia@x.com", AGORA + timedelta(seconds=1))
    inserir_pendente(ctx, livro_id, "caio@x.com", AGORA + timedelta(seconds=2))
    ativas = reservas.listar_ativas(ctx, livro_id)
    assert [a["ordem"] for a in ativas] == [ordem_ana, r2["ordem"]]
    assert [a["email"] for a in ativas] == ["ana@x.com", "bia@x.com"]
    assert set(ativas[0]) == {"ordem", "email", "reservadoEm", "expiraEm"}
