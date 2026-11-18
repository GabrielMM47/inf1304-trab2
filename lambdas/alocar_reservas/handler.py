from datetime import datetime, timezone

from sebo import fila
from sebo.contexto import Contexto

_ctx = None


def _contexto():
    global _ctx
    if _ctx is None:
        _ctx = Contexto.de_ambiente()
    return _ctx


def _disponivel(imagem):
    return int(imagem.get("disponivel", {}).get("N", 0)) if imagem else 0


def lambda_handler(event, context):
    livros_afetados = []
    for rec in event.get("Records", []):
        if rec.get("eventName") not in ("INSERT", "MODIFY"):
            continue
        dyn = rec.get("dynamodb", {})
        novo_img = dyn.get("NewImage")
        if not novo_img:
            continue
        novo = _disponivel(novo_img)
        antigo = _disponivel(dyn.get("OldImage"))
        if novo > antigo and novo > 0:
            livro_id = dyn.get("Keys", {}).get("livroId", {}).get("S") or novo_img[
                "livroId"
            ]["S"]
            if livro_id not in livros_afetados:
                livros_afetados.append(livro_id)
    agora = datetime.now(timezone.utc)
    alocados = sum(len(fila.alocar(_contexto(), lid, agora)) for lid in livros_afetados)
    return {"alocados": alocados}
