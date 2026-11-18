from sebo import http, livros
from sebo.contexto import Contexto
from sebo.erros import DadosInvalidos
from sebo.http import resposta, tratar_erros

_ctx = None


def _contexto():
    global _ctx
    if _ctx is None:
        _ctx = Contexto.de_ambiente()
    return _ctx


@tratar_erros
def lambda_handler(event, context):
    rota = event.get("routeKey")
    if rota == "POST /livros":
        dados = http.ler_json(event)
        livro_id = livros.cadastrar(
            _contexto(),
            http.campo(dados, "titulo", str),
            http.campo(dados, "autor", str),
            http.numero(dados, "preco"),
            http.campo(dados, "quantidade", int),
        )
        return resposta(201, {"livroId": livro_id})
    if rota == "POST /livros/{id}/chegada":
        livro_id = (event.get("pathParameters") or {}).get("id")
        if not livro_id:
            raise DadosInvalidos("id do livro ausente")
        dados = http.ler_json(event)
        livro = livros.registrar_chegada(
            _contexto(), livro_id, http.campo(dados, "quantidade", int)
        )
        return resposta(200, livro)
    return resposta(404, {"erro": "rota não encontrada"})
