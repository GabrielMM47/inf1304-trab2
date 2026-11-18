from datetime import timedelta

from sebo.contexto import Contexto


def test_contexto_de_ambiente(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "teste")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "teste")
    monkeypatch.setenv("TABELA_LIVROS", "Livros-teste")
    monkeypatch.setenv("TABELA_INTERESSES", "Interesses-teste")
    monkeypatch.setenv("TABELA_VENDAS", "Vendas-teste")
    monkeypatch.setenv("TOPICO_SNS", "arn:aws:sns:us-east-1:123456789012:t")
    monkeypatch.delenv("PRAZO_RESERVA_MINUTOS", raising=False)
    c = Contexto.de_ambiente()
    assert c.prazo_reserva == timedelta(minutes=2)
    assert c.tabela_livros == "Livros-teste"
    assert c.tabela_interesses == "Interesses-teste"
    assert c.tabela_vendas == "Vendas-teste"
    assert c.topico_sns == "arn:aws:sns:us-east-1:123456789012:t"


def test_contexto_prazo_configuravel(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "teste")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "teste")
    for v in ("TABELA_LIVROS", "TABELA_INTERESSES", "TABELA_VENDAS", "TOPICO_SNS"):
        monkeypatch.setenv(v, "x")
    monkeypatch.setenv("PRAZO_RESERVA_MINUTOS", "5")
    assert Contexto.de_ambiente().prazo_reserva == timedelta(minutes=5)


def test_fixture_cria_tabelas(ctx):
    desc = ctx.dynamodb.describe_table(TableName=ctx.tabela_interesses)["Table"]
    assert desc["GlobalSecondaryIndexes"][0]["IndexName"] == "status-expiraEm"
    livros = ctx.dynamodb.describe_table(TableName=ctx.tabela_livros)["Table"]
    assert livros["StreamSpecification"]["StreamViewType"] == "NEW_AND_OLD_IMAGES"
    ctx.dynamodb.describe_table(TableName=ctx.tabela_vendas)


def test_fixture_emails_entrega_mensagens(ctx, emails):
    ctx.sns.publish(
        TopicArn=ctx.topico_sns,
        Subject="Assunto",
        Message="Texto",
        MessageAttributes={"email": {"DataType": "String", "StringValue": "a@b.com"}},
    )
    assert emails() == [{"email": "a@b.com", "assunto": "Assunto", "texto": "Texto"}]
    assert emails() == []
