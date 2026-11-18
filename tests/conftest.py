import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from sebo.contexto import Contexto

RAIZ = Path(__file__).resolve().parent.parent


def carregar_handler(nome: str):
    caminho = RAIZ / "lambdas" / nome / "handler.py"
    spec = importlib.util.spec_from_file_location(f"handler_{nome}", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    with mock_aws():
        dynamodb = boto3.client("dynamodb", region_name="us-east-1")
        sns = boto3.client("sns", region_name="us-east-1")
        dynamodb.create_table(
            TableName="Livros",
            AttributeDefinitions=[{"AttributeName": "livroId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "livroId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
            StreamSpecification={
                "StreamEnabled": True,
                "StreamViewType": "NEW_AND_OLD_IMAGES",
            },
        )
        dynamodb.create_table(
            TableName="Interesses",
            AttributeDefinitions=[
                {"AttributeName": "livroId", "AttributeType": "S"},
                {"AttributeName": "ordem", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "expiraEm", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "livroId", "KeyType": "HASH"},
                {"AttributeName": "ordem", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status-expiraEm",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "expiraEm", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        dynamodb.create_table(
            TableName="Vendas",
            AttributeDefinitions=[{"AttributeName": "vendaId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "vendaId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        topico = sns.create_topic(Name="sebo-notificacoes")["TopicArn"]
        yield Contexto(
            dynamodb=dynamodb,
            sns=sns,
            tabela_livros="Livros",
            tabela_interesses="Interesses",
            tabela_vendas="Vendas",
            topico_sns=topico,
            prazo_reserva=timedelta(minutes=2),
        )


@pytest.fixture
def emails(ctx):
    sqs = boto3.client("sqs", region_name="us-east-1")
    url = sqs.create_queue(QueueName="fila-emails")["QueueUrl"]
    arn = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]
    ctx.sns.subscribe(
        TopicArn=ctx.topico_sns,
        Protocol="sqs",
        Endpoint=arn,
        Attributes={"RawMessageDelivery": "false"},
    )

    def drenar() -> list[dict]:
        saida = []
        while True:
            resp = sqs.receive_message(
                QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=0
            )
            msgs = resp.get("Messages", [])
            if not msgs:
                return saida
            for m in msgs:
                env = json.loads(m["Body"])
                attrs = env.get("MessageAttributes", {})
                saida.append(
                    {
                        "email": attrs.get("email", {}).get("Value"),
                        "assunto": env.get("Subject"),
                        "texto": env.get("Message"),
                    }
                )
                sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])

    return drenar
