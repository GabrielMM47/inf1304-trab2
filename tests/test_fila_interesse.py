from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from sebo import fila, livros
from sebo.tempo import iso
from sebo.erros import DadosInvalidos, InteresseDuplicado, LivroNaoEncontrado

AGORA = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _livro(ctx, disponivel):
    lid = livros.cadastrar(ctx, "Dom Casmurro", "Machado", Decimal("10"), 5)
    ctx.dynamodb.update_item(
        TableName=ctx.tabela_livros,
        Key={"livroId": {"S": lid}},
        UpdateExpression="SET disponivel = :d",
        ExpressionAttributeValues={":d": {"N": str(disponivel)}},
    )
    return lid


def _item(ctx, lid, ordem):
    item = ctx.dynamodb.get_item(
        TableName=ctx.tabela_interesses,
        Key={"livroId": {"S": lid}, "ordem": {"S": ordem}},
        ConsistentRead=True,
    )["Item"]
    return {k: v["S"] for k, v in item.items()}


def _marcar(ctx, lid, ordem, status):
    ctx.dynamodb.update_item(
        TableName=ctx.tabela_interesses,
        Key={"livroId": {"S": lid}, "ordem": {"S": ordem}},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": {"S": status}},
    )


def test_com_estoque_reserva_imediatamente(ctx, emails):
    lid = _livro(ctx, 1)
    r = fila.registrar_interesse(ctx, lid, "ana@x.com", AGORA)
    assert r["status"] == "RESERVADO"
    assert r["expiraEm"] == iso(AGORA + ctx.prazo_reserva)
    assert _item(ctx, lid, r["ordem"])["status"] == "RESERVADO"
    msgs = emails()
    assert len(msgs) == 1
    assert "Reserva confirmada" in msgs[0]["assunto"]


def test_sem_estoque_entra_na_fila_com_posicao(ctx, emails):
    lid = _livro(ctx, 0)
    r1 = fila.registrar_interesse(ctx, lid, "ana@x.com", AGORA)
    r2 = fila.registrar_interesse(ctx, lid, "bruno@x.com", AGORA + timedelta(seconds=1))
    assert (r1["status"], r1["posicaoFila"]) == ("PENDENTE", 1)
    assert (r2["status"], r2["posicaoFila"]) == ("PENDENTE", 2)
    msgs = emails()
    assert len(msgs) == 2
    assert all("Você está na fila" in m["assunto"] for m in msgs)
    assert "posição 2" in msgs[1]["texto"]


def test_quem_chega_depois_nao_fura_fila(ctx, emails):
    lid = _livro(ctx, 0)
    ana = fila.registrar_interesse(ctx, lid, "ana@x.com", AGORA)
    livros.registrar_chegada(ctx, lid, 1)
    bruno = fila.registrar_interesse(ctx, lid, "bruno@x.com", AGORA + timedelta(seconds=1))
    assert _item(ctx, lid, ana["ordem"])["status"] == "RESERVADO"
    assert bruno["status"] == "PENDENTE"
    assert bruno["posicaoFila"] == 1


def test_duplicado_pendente_ou_reservado_recusado(ctx):
    lid = _livro(ctx, 0)
    r = fila.registrar_interesse(ctx, lid, "ana@x.com", AGORA)
    with pytest.raises(InteresseDuplicado):
        fila.registrar_interesse(ctx, lid, "ana@x.com", AGORA)
    _marcar(ctx, lid, r["ordem"], "RESERVADO")
    with pytest.raises(InteresseDuplicado):
        fila.registrar_interesse(ctx, lid, "ana@x.com", AGORA)
    _marcar(ctx, lid, r["ordem"], "EXPIRADO")
    novo = fila.registrar_interesse(ctx, lid, "ana@x.com", AGORA + timedelta(seconds=1))
    assert novo["status"] == "PENDENTE"


def test_email_normalizado(ctx, emails):
    lid = _livro(ctx, 0)
    r = fila.registrar_interesse(ctx, lid, " Ana@X.com ", AGORA)
    assert _item(ctx, lid, r["ordem"])["email"] == "ana@x.com"
    assert emails()[0]["email"] == "ana@x.com"
    with pytest.raises(InteresseDuplicado):
        fila.registrar_interesse(ctx, lid, "ana@x.com", AGORA)


@pytest.mark.parametrize("email", ["", "sem-arroba", "a@b", "a b@c.com", "@x.com"])
def test_email_invalido(ctx, email):
    lid = _livro(ctx, 1)
    with pytest.raises(DadosInvalidos):
        fila.registrar_interesse(ctx, lid, email, AGORA)


def test_livro_inexistente(ctx):
    with pytest.raises(LivroNaoEncontrado):
        fila.registrar_interesse(ctx, "nao-existe", "ana@x.com", AGORA)
