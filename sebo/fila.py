import re
from datetime import datetime
from uuid import uuid4

from sebo import livros
from sebo.erros import DadosInvalidos, InteresseDuplicado
from sebo.notificacao import Notificador
from sebo.tempo import de_iso, iso

MAX_ITERACOES = 100
PADRAO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def reservar(ctx, livro_id: str, ordem: str, agora: datetime) -> bool:
    try:
        ctx.dynamodb.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": ctx.tabela_livros,
                        "Key": {"livroId": {"S": livro_id}},
                        "UpdateExpression": "SET disponivel = disponivel - :um",
                        "ConditionExpression": "disponivel > :zero",
                        "ExpressionAttributeValues": {
                            ":um": {"N": "1"},
                            ":zero": {"N": "0"},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": ctx.tabela_interesses,
                        "Key": {"livroId": {"S": livro_id}, "ordem": {"S": ordem}},
                        "UpdateExpression": (
                            "SET #s = :reservado, reservadoEm = :agora, expiraEm = :expira"
                        ),
                        "ConditionExpression": "#s = :pendente",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":reservado": {"S": "RESERVADO"},
                            ":pendente": {"S": "PENDENTE"},
                            ":agora": {"S": iso(agora)},
                            ":expira": {"S": iso(agora + ctx.prazo_reserva)},
                        },
                    }
                },
            ]
        )
    except ctx.dynamodb.exceptions.TransactionCanceledException:
        return False
    return True


def _para_dict(item: dict) -> dict:
    return {k: v["S"] for k, v in item.items()}


def pendentes(ctx, livro_id: str) -> list[dict]:
    resultado = []
    kwargs = {
        "TableName": ctx.tabela_interesses,
        "KeyConditionExpression": "livroId = :l",
        "FilterExpression": "#s = :pendente",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {
            ":l": {"S": livro_id},
            ":pendente": {"S": "PENDENTE"},
        },
        "ScanIndexForward": True,
        "ConsistentRead": True,
    }
    while True:
        resp = ctx.dynamodb.query(**kwargs)
        resultado.extend(_para_dict(i) for i in resp["Items"])
        if "LastEvaluatedKey" not in resp:
            return resultado
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def alocar(ctx, livro_id: str, agora: datetime) -> list[dict]:
    reservados = []
    notificador = Notificador(ctx)
    for _ in range(MAX_ITERACOES):
        livro = livros.obter(ctx, livro_id)
        if livro["disponivel"] <= 0:
            break
        fila = pendentes(ctx, livro_id)
        if not fila:
            break
        proximo = fila[0]
        if reservar(ctx, livro_id, proximo["ordem"], agora):
            proximo["status"] = "RESERVADO"
            proximo["reservadoEm"] = iso(agora)
            proximo["expiraEm"] = iso(agora + ctx.prazo_reserva)
            notificador.reserva_confirmada(
                proximo["email"], livro["titulo"], de_iso(proximo["expiraEm"])
            )
            reservados.append(proximo)
    return reservados


def posicao_na_fila(ctx, livro_id: str, ordem: str) -> int:
    return 1 + sum(1 for i in pendentes(ctx, livro_id) if i["ordem"] < ordem)


def _ja_ativo(ctx, livro_id: str, email: str) -> bool:
    kwargs = {
        "TableName": ctx.tabela_interesses,
        "KeyConditionExpression": "livroId = :l",
        "FilterExpression": "email = :e AND #s IN (:p, :r)",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {
            ":l": {"S": livro_id},
            ":e": {"S": email},
            ":p": {"S": "PENDENTE"},
            ":r": {"S": "RESERVADO"},
        },
        "ConsistentRead": True,
    }
    while True:
        resp = ctx.dynamodb.query(**kwargs)
        if resp["Items"]:
            return True
        if "LastEvaluatedKey" not in resp:
            return False
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def registrar_interesse(ctx, livro_id: str, email: str, agora: datetime) -> dict:
    email = (email or "").strip().lower()
    if not PADRAO_EMAIL.match(email):
        raise DadosInvalidos("e-mail inválido")
    livro = livros.obter(ctx, livro_id)
    if _ja_ativo(ctx, livro_id, email):
        raise InteresseDuplicado("já existe interesse ativo deste e-mail para o livro")

    ordem = f"{iso(agora)}#{uuid4().hex}"
    ctx.dynamodb.put_item(
        TableName=ctx.tabela_interesses,
        Item={
            "livroId": {"S": livro_id},
            "ordem": {"S": ordem},
            "email": {"S": email},
            "status": {"S": "PENDENTE"},
            "criadoEm": {"S": iso(agora)},
        },
        ConditionExpression="attribute_not_exists(ordem)",
    )
    alocar(ctx, livro_id, agora)

    item = _para_dict(
        ctx.dynamodb.get_item(
            TableName=ctx.tabela_interesses,
            Key={"livroId": {"S": livro_id}, "ordem": {"S": ordem}},
            ConsistentRead=True,
        )["Item"]
    )
    if item["status"] == "RESERVADO":
        return {"ordem": ordem, "status": "RESERVADO", "expiraEm": item["expiraEm"]}
    posicao = posicao_na_fila(ctx, livro_id, ordem)
    Notificador(ctx).na_fila(email, livro["titulo"], posicao)
    return {"ordem": ordem, "status": "PENDENTE", "posicaoFila": posicao}
