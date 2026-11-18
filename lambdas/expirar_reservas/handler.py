from datetime import datetime, timezone

from sebo import reservas
from sebo.contexto import Contexto

_ctx = None


def _contexto():
    global _ctx
    if _ctx is None:
        _ctx = Contexto.de_ambiente()
    return _ctx


def lambda_handler(event, context):
    expirados = reservas.expirar_vencidas(_contexto(), datetime.now(timezone.utc))
    return {"expirados": len(expirados)}
