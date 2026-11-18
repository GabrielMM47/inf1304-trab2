from datetime import datetime, timezone

from sebo import fila, http
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
    if event.get("routeKey") == "POST /interesses":
        dados = http.ler_json(event)
        resultado = fila.registrar_interesse(
            _contexto(),
            http.campo(dados, "livroId", str),
            http.campo(dados, "email", str),
            datetime.now(timezone.utc),
        )
        return resposta(201, resultado)
    return resposta(404, {"erro": "rota não encontrada"})
