from datetime import datetime

from sebo.contexto import Contexto

LIMITE_ASSUNTO = 100


class Notificador:
    def __init__(self, ctx: Contexto):
        self._ctx = ctx

    def _publicar(self, email: str, assunto: str, texto: str) -> None:
        self._ctx.sns.publish(
            TopicArn=self._ctx.topico_sns,
            Subject=assunto[:LIMITE_ASSUNTO],
            Message=texto,
            MessageAttributes={"email": {"DataType": "String", "StringValue": email}},
        )

    def reserva_confirmada(self, email: str, titulo: str, expira_em: datetime) -> None:
        limite = expira_em.strftime("%d/%m/%Y %H:%M")
        self._publicar(
            email,
            f"Reserva confirmada: {titulo}",
            f"Sua reserva de \"{titulo}\" está confirmada. "
            f"Compareça à livraria para efetivar a compra até {limite} (UTC).",
        )

    def na_fila(self, email: str, titulo: str, posicao: int) -> None:
        self._publicar(
            email,
            f"Você está na fila: {titulo}",
            f"\"{titulo}\" já está reservado. Você está na posição {posicao} da fila.",
        )

    def reserva_expirada(self, email: str, titulo: str) -> None:
        self._publicar(
            email,
            f"Reserva expirada: {titulo}",
            f"Sua reserva de \"{titulo}\" expirou e passou para o próximo da fila. "
            "Se ainda quiser o livro, você pode registrar novo interesse.",
        )
