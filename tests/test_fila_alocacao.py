from datetime import datetime, timedelta, timezone
from decimal import Decimal

from conftest import inserir_pendente
from sebo import fila, livros
from sebo.tempo import iso

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


def _status(ctx, lid, ordem):
    item = ctx.dynamodb.get_item(
        TableName=ctx.tabela_interesses,
        Key={"livroId": {"S": lid}, "ordem": {"S": ordem}},
        ConsistentRead=True,
    )["Item"]
    return {k: v["S"] for k, v in item.items()}


def test_reservar_decrementa_e_marca_reservado(ctx):
    lid = _livro(ctx, 1)
    ordem = inserir_pendente(ctx, lid, "ana@x.com", AGORA)
    assert fila.reservar(ctx, lid, ordem, AGORA) is True
    assert livros.obter(ctx, lid)["disponivel"] == 0
    item = _status(ctx, lid, ordem)
    assert item["status"] == "RESERVADO"
    assert item["reservadoEm"] == iso(AGORA)
    assert item["expiraEm"] == iso(AGORA + timedelta(minutes=2))


def test_reservar_sem_disponivel_retorna_false_sem_efeito(ctx):
    lid = _livro(ctx, 0)
    ordem = inserir_pendente(ctx, lid, "ana@x.com", AGORA)
    assert fila.reservar(ctx, lid, ordem, AGORA) is False
    assert _status(ctx, lid, ordem)["status"] == "PENDENTE"
    assert livros.obter(ctx, lid)["disponivel"] == 0


def test_reservar_interesse_ja_reservado_retorna_false(ctx):
    lid = _livro(ctx, 3)
    ordem = inserir_pendente(ctx, lid, "ana@x.com", AGORA)
    assert fila.reservar(ctx, lid, ordem, AGORA) is True
    assert fila.reservar(ctx, lid, ordem, AGORA) is False
    assert livros.obter(ctx, lid)["disponivel"] == 2


def test_reservar_com_estado_obsoleto_falha_sem_efeito(ctx):
    lid = _livro(ctx, 1)
    ana = inserir_pendente(ctx, lid, "ana@x.com", AGORA)
    bruno = inserir_pendente(ctx, lid, "bruno@x.com", AGORA + timedelta(seconds=1))
    assert fila.reservar(ctx, lid, ana, AGORA) is True
    assert fila.reservar(ctx, lid, ana, AGORA) is False
    assert fila.reservar(ctx, lid, bruno, AGORA) is False
    assert livros.obter(ctx, lid)["disponivel"] == 0
    assert _status(ctx, lid, bruno)["status"] == "PENDENTE"


def test_alocar_respeita_ordem_de_chegada(ctx, emails):
    lid = _livro(ctx, 2)
    for i, nome in enumerate(["ana", "bruno", "caio"]):
        inserir_pendente(ctx, lid, f"{nome}@x.com", AGORA + timedelta(seconds=i))
    reservados = fila.alocar(ctx, lid, AGORA)
    assert [r["email"] for r in reservados] == ["ana@x.com", "bruno@x.com"]
    assert all(r["expiraEm"] == iso(AGORA + timedelta(minutes=2)) for r in reservados)
    assert [p["email"] for p in fila.pendentes(ctx, lid)] == ["caio@x.com"]
    enviados = emails()
    assert sorted(e["email"] for e in enviados) == ["ana@x.com", "bruno@x.com"]
    assert all("Reserva confirmada" in e["assunto"] for e in enviados)


def test_alocar_sem_pendentes_nao_altera_estoque(ctx):
    lid = _livro(ctx, 2)
    assert fila.alocar(ctx, lid, AGORA) == []
    assert livros.obter(ctx, lid)["disponivel"] == 2


def test_alocar_sem_estoque_nao_reserva(ctx, emails):
    lid = _livro(ctx, 0)
    ordem = inserir_pendente(ctx, lid, "ana@x.com", AGORA)
    assert fila.alocar(ctx, lid, AGORA) == []
    assert _status(ctx, lid, ordem)["status"] == "PENDENTE"
    assert emails() == []
