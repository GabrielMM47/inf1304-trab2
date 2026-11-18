from datetime import datetime, timezone

from sebo.notificacao import Notificador


def test_reserva_confirmada_publica_com_atributo_email(ctx, emails):
    Notificador(ctx).reserva_confirmada(
        "ana@x.com",
        "Dom Casmurro",
        datetime(2026, 11, 17, 12, 2, tzinfo=timezone.utc),
    )
    [m] = emails()
    assert m["email"] == "ana@x.com"
    assert m["assunto"] == "Reserva confirmada: Dom Casmurro"
    assert "Dom Casmurro" in m["texto"]
    assert "17/11/2026 12:02" in m["texto"]
    assert "livraria" in m["texto"]


def test_na_fila_informa_posicao(ctx, emails):
    Notificador(ctx).na_fila("bia@x.com", "Dom Casmurro", 3)
    [m] = emails()
    assert m["email"] == "bia@x.com"
    assert m["assunto"] == "Você está na fila: Dom Casmurro"
    assert "posição 3" in m["texto"]


def test_reserva_expirada(ctx, emails):
    Notificador(ctx).reserva_expirada("ana@x.com", "Dom Casmurro")
    [m] = emails()
    assert m["email"] == "ana@x.com"
    assert m["assunto"] == "Reserva expirada: Dom Casmurro"
    assert "próximo da fila" in m["texto"]
    assert "novo interesse" in m["texto"]


def test_assunto_longo_truncado(ctx, emails):
    Notificador(ctx).na_fila("ana@x.com", "L" * 200, 1)
    [m] = emails()
    assert len(m["assunto"]) <= 100
