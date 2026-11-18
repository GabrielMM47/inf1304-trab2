from datetime import datetime, timezone

from sebo import http, reservas
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
    if rota == "GET /reservas":
        livro_id = (event.get("queryStringParameters") or {}).get("livroId")
        if not livro_id:
            raise DadosInvalidos("parâmetro 'livroId' obrigatório")
        return resposta(200, reservas.listar_ativas(_contexto(), livro_id))
    if rota == "POST /vendas":
        dados = http.ler_json(event)
        venda_id = reservas.vender(
            _contexto(),
            http.campo(dados, "livroId", str),
            http.campo(dados, "ordem", str),
            datetime.now(timezone.utc),
        )
        return resposta(201, {"vendaId": venda_id})
    return resposta(404, {"erro": "rota não encontrada"})
