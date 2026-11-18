from sebo import livros
from sebo.contexto import Contexto
from sebo.http import resposta, tratar_erros

_ctx = None


def _contexto():
    global _ctx
    if _ctx is None:
        _ctx = Contexto.de_ambiente()
    return _ctx


@tratar_erros
def lambda_handler(event, context):
    if event.get("routeKey") == "GET /livros":
        return resposta(200, livros.listar(_contexto()))
    return resposta(404, {"erro": "rota não encontrada"})
