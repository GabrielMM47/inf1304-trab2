from decimal import Decimal

import pytest

from sebo import livros
from sebo.erros import DadosInvalidos, LivroNaoEncontrado


def test_cadastrar_e_obter(ctx):
    lid = livros.cadastrar(ctx, "Dom Casmurro", "Machado", Decimal("25.50"), 3)
    livro = livros.obter(ctx, lid)
    assert livro == {
        "livroId": lid,
        "titulo": "Dom Casmurro",
        "autor": "Machado",
        "preco": Decimal("25.50"),
        "quantidade": 3,
        "disponivel": 3,
    }
    assert isinstance(livro["quantidade"], int)
    assert isinstance(livro["disponivel"], int)


def test_obter_inexistente(ctx):
    with pytest.raises(LivroNaoEncontrado):
        livros.obter(ctx, "nao-existe")


def test_listar_ordenado_por_titulo(ctx):
    for t in ["C", "A", "B"]:
        livros.cadastrar(ctx, t, "x", Decimal("1"), 1)
    assert [l["titulo"] for l in livros.listar(ctx)] == ["A", "B", "C"]


def test_listar_paginado(ctx):
    for i in range(30):
        livros.cadastrar(ctx, f"L{i:02d}", "x", Decimal("1"), 1)
    ctx.dynamodb.scan = _scan_pequeno(ctx.dynamodb.scan)
    assert len(livros.listar(ctx)) == 30


def _scan_pequeno(original):
    def scan(**kw):
        return original(Limit=7, **kw)

    return scan


def test_chegada_incrementa_quantidade_e_disponivel(ctx):
    lid = livros.cadastrar(ctx, "A", "x", Decimal("1"), 2)
    livro = livros.registrar_chegada(ctx, lid, 3)
    assert livro["quantidade"] == 5
    assert livro["disponivel"] == 5
    assert livros.obter(ctx, lid)["disponivel"] == 5


def test_chegada_livro_inexistente(ctx):
    with pytest.raises(LivroNaoEncontrado):
        livros.registrar_chegada(ctx, "nao-existe", 1)
    assert ctx.dynamodb.scan(TableName="Livros")["Count"] == 0


@pytest.mark.parametrize(
    "titulo,autor,preco,qtd",
    [
        ("", "a", Decimal("1"), 1),
        ("t", "", Decimal("1"), 1),
        ("t", "a", Decimal("-1"), 1),
        ("t", "a", Decimal("1"), -1),
        ("t", "a", Decimal("1"), True),
        ("t", "a", Decimal("1"), 1.5),
    ],
)
def test_cadastro_invalido(ctx, titulo, autor, preco, qtd):
    with pytest.raises(DadosInvalidos):
        livros.cadastrar(ctx, titulo, autor, preco, qtd)


@pytest.mark.parametrize("qtd", [0, -1, True, 1.5])
def test_chegada_quantidade_nao_positiva(ctx, qtd):
    lid = livros.cadastrar(ctx, "A", "x", Decimal("1"), 1)
    with pytest.raises(DadosInvalidos):
        livros.registrar_chegada(ctx, lid, qtd)
