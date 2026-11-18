import base64
import binascii
import functools
import json
import logging
from decimal import Decimal

from sebo.erros import DadosInvalidos, ErroSebo

log = logging.getLogger(__name__)


def ler_json(evento: dict) -> dict:
    corpo = evento.get("body")
    if not corpo:
        raise DadosInvalidos("corpo da requisição ausente")
    if evento.get("isBase64Encoded"):
        try:
            corpo = base64.b64decode(corpo).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            raise DadosInvalidos("corpo da requisição inválido")
    try:
        dados = json.loads(corpo)
    except ValueError:
        raise DadosInvalidos("corpo da requisição não é JSON válido")
    if not isinstance(dados, dict):
        raise DadosInvalidos("corpo da requisição deve ser um objeto JSON")
    return dados


def _padrao(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    raise TypeError(f"não serializável: {type(obj).__name__}")


def resposta(status: int, corpo) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(corpo, default=_padrao),
    }


def tratar_erros(fn):
    @functools.wraps(fn)
    def envolvido(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ErroSebo as e:
            return resposta(e.status, {"erro": str(e)})
        except Exception:
            log.exception("erro inesperado")
            return resposta(500, {"erro": "erro interno"})

    return envolvido


def campo(dados: dict, nome: str, tipo: type):
    valor = dados.get(nome)
    if not isinstance(valor, tipo) or isinstance(valor, bool):
        raise DadosInvalidos(f"campo '{nome}' ausente ou inválido")
    return valor


def numero(dados: dict, nome: str) -> Decimal:
    valor = dados.get(nome)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise DadosInvalidos(f"campo '{nome}' deve ser um número")
    return Decimal(str(valor))
