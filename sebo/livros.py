from decimal import Decimal
from uuid import uuid4

from sebo.erros import DadosInvalidos, LivroNaoEncontrado


def _para_dict(item: dict) -> dict:
    return {
        "livroId": item["livroId"]["S"],
        "titulo": item["titulo"]["S"],
        "autor": item["autor"]["S"],
        "preco": Decimal(item["preco"]["N"]),
        "quantidade": int(item["quantidade"]["N"]),
        "disponivel": int(item["disponivel"]["N"]),
    }


def _quantidade_valida(q, minimo: int) -> bool:
    return isinstance(q, int) and not isinstance(q, bool) and q >= minimo


def cadastrar(ctx, titulo: str, autor: str, preco: Decimal, quantidade: int) -> str:
    if not titulo or not autor:
        raise DadosInvalidos("Título e autor são obrigatórios.")
    if not isinstance(preco, Decimal) or not preco.is_finite() or preco < 0:
        raise DadosInvalidos("Preço inválido.")
    if not _quantidade_valida(quantidade, 0):
        raise DadosInvalidos("Quantidade inválida.")
    livro_id = uuid4().hex
    ctx.dynamodb.put_item(
        TableName=ctx.tabela_livros,
        Item={
            "livroId": {"S": livro_id},
            "titulo": {"S": titulo},
            "autor": {"S": autor},
            "preco": {"N": str(preco)},
            "quantidade": {"N": str(quantidade)},
            "disponivel": {"N": str(quantidade)},
        },
    )
    return livro_id


def obter(ctx, livro_id: str) -> dict:
    resp = ctx.dynamodb.get_item(
        TableName=ctx.tabela_livros,
        Key={"livroId": {"S": livro_id}},
        ConsistentRead=True,
    )
    if "Item" not in resp:
        raise LivroNaoEncontrado(f"Livro {livro_id} não encontrado.")
    return _para_dict(resp["Item"])


def listar(ctx) -> list[dict]:
    itens = []
    kwargs = {"TableName": ctx.tabela_livros}
    while True:
        resp = ctx.dynamodb.scan(**kwargs)
        itens.extend(_para_dict(i) for i in resp["Items"])
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return sorted(itens, key=lambda l: l["titulo"])


def registrar_chegada(ctx, livro_id: str, quantidade: int) -> dict:
    if not _quantidade_valida(quantidade, 1):
        raise DadosInvalidos("Quantidade deve ser um inteiro positivo.")
    try:
        resp = ctx.dynamodb.update_item(
            TableName=ctx.tabela_livros,
            Key={"livroId": {"S": livro_id}},
            UpdateExpression="ADD quantidade :n, disponivel :n",
            ConditionExpression="attribute_exists(livroId)",
            ExpressionAttributeValues={":n": {"N": str(quantidade)}},
            ReturnValues="ALL_NEW",
        )
    except ctx.dynamodb.exceptions.ConditionalCheckFailedException:
        raise LivroNaoEncontrado(f"Livro {livro_id} não encontrado.") from None
    return _para_dict(resp["Attributes"])
