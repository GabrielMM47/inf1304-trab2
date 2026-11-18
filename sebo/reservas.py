from datetime import datetime
from uuid import uuid4

from sebo import livros
from sebo.erros import ReservaInativa
from sebo.fila import _para_dict
from sebo.notificacao import Notificador
from sebo.tempo import iso


def _vencidas(ctx, agora: datetime) -> list[dict]:
    resultado = []
    kwargs = {
        "TableName": ctx.tabela_interesses,
        "IndexName": "status-expiraEm",
        "KeyConditionExpression": "#s = :reservado AND expiraEm < :agora",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {
            ":reservado": {"S": "RESERVADO"},
            ":agora": {"S": iso(agora)},
        },
    }
    while True:
        resp = ctx.dynamodb.query(**kwargs)
        resultado.extend(_para_dict(i) for i in resp["Items"])
        if "LastEvaluatedKey" not in resp:
            return resultado
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def expirar_vencidas(ctx, agora: datetime) -> list[dict]:
    expirados = []
    notificador = Notificador(ctx)
    for interesse in _vencidas(ctx, agora):
        try:
            ctx.dynamodb.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": ctx.tabela_interesses,
                            "Key": {
                                "livroId": {"S": interesse["livroId"]},
                                "ordem": {"S": interesse["ordem"]},
                            },
                            "UpdateExpression": "SET #s = :expirado",
                            "ConditionExpression": "#s = :reservado AND expiraEm < :agora",
                            "ExpressionAttributeNames": {"#s": "status"},
                            "ExpressionAttributeValues": {
                                ":expirado": {"S": "EXPIRADO"},
                                ":reservado": {"S": "RESERVADO"},
                                ":agora": {"S": iso(agora)},
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": ctx.tabela_livros,
                            "Key": {"livroId": {"S": interesse["livroId"]}},
                            "UpdateExpression": "ADD disponivel :um",
                            "ExpressionAttributeValues": {":um": {"N": "1"}},
                        }
                    },
                ]
            )
        except ctx.dynamodb.exceptions.TransactionCanceledException:
            continue
        interesse["status"] = "EXPIRADO"
        titulo = livros.obter(ctx, interesse["livroId"])["titulo"]
        notificador.reserva_expirada(interesse["email"], titulo)
        expirados.append(interesse)
    return expirados


def listar_ativas(ctx, livro_id: str) -> list[dict]:
    resultado = []
    kwargs = {
        "TableName": ctx.tabela_interesses,
        "KeyConditionExpression": "livroId = :l",
        "FilterExpression": "#s = :reservado",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {
            ":l": {"S": livro_id},
            ":reservado": {"S": "RESERVADO"},
        },
        "ScanIndexForward": True,
        "ConsistentRead": True,
    }
    while True:
        resp = ctx.dynamodb.query(**kwargs)
        for i in resp["Items"]:
            d = _para_dict(i)
            resultado.append(
                {k: d[k] for k in ("ordem", "email", "reservadoEm", "expiraEm")}
            )
        if "LastEvaluatedKey" not in resp:
            return resultado
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def vender(ctx, livro_id: str, ordem: str, agora: datetime) -> str:
    resp = ctx.dynamodb.get_item(
        TableName=ctx.tabela_interesses,
        Key={"livroId": {"S": livro_id}, "ordem": {"S": ordem}},
        ConsistentRead=True,
    )
    if "Item" not in resp:
        raise ReservaInativa("Reserva não encontrada.")
    interesse = _para_dict(resp["Item"])
    livro = livros.obter(ctx, livro_id)
    venda_id = uuid4().hex
    try:
        ctx.dynamodb.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": ctx.tabela_interesses,
                        "Key": {"livroId": {"S": livro_id}, "ordem": {"S": ordem}},
                        "UpdateExpression": "SET #s = :vendido",
                        "ConditionExpression": "#s = :reservado AND expiraEm > :agora",
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":vendido": {"S": "VENDIDO"},
                            ":reservado": {"S": "RESERVADO"},
                            ":agora": {"S": iso(agora)},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": ctx.tabela_livros,
                        "Key": {"livroId": {"S": livro_id}},
                        "UpdateExpression": "SET quantidade = quantidade - :um",
                        "ConditionExpression": "quantidade > :zero",
                        "ExpressionAttributeValues": {
                            ":um": {"N": "1"},
                            ":zero": {"N": "0"},
                        },
                    }
                },
                {
                    "Put": {
                        "TableName": ctx.tabela_vendas,
                        "Item": {
                            "vendaId": {"S": venda_id},
                            "livroId": {"S": livro_id},
                            "email": {"S": interesse["email"]},
                            "preco": {"N": str(livro["preco"])},
                            "data": {"S": iso(agora)},
                            "ordemInteresse": {"S": ordem},
                        },
                        "ConditionExpression": "attribute_not_exists(vendaId)",
                    }
                },
            ]
        )
    except ctx.dynamodb.exceptions.TransactionCanceledException:
        raise ReservaInativa(
            "A reserva não está mais ativa (expirada ou já vendida)."
        ) from None
    return venda_id
