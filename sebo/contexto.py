import os
from dataclasses import dataclass
from datetime import timedelta

import boto3


@dataclass
class Contexto:
    dynamodb: object
    sns: object
    tabela_livros: str
    tabela_interesses: str
    tabela_vendas: str
    topico_sns: str
    prazo_reserva: timedelta

    @classmethod
    def de_ambiente(cls) -> "Contexto":
        return cls(
            dynamodb=boto3.client("dynamodb"),
            sns=boto3.client("sns"),
            tabela_livros=os.environ["TABELA_LIVROS"],
            tabela_interesses=os.environ["TABELA_INTERESSES"],
            tabela_vendas=os.environ["TABELA_VENDAS"],
            topico_sns=os.environ["TOPICO_SNS"],
            prazo_reserva=timedelta(
                minutes=float(os.environ.get("PRAZO_RESERVA_MINUTOS", "2"))
            ),
        )
