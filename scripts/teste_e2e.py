#!/usr/bin/env python3
"""Teste de ponta a ponta contra a stack implantada na AWS.

Percorre o fluxo completo (reserva, fila, chegada, expiração, próximo da fila,
venda) chamando a API real e conferindo os e-mails publicados no SNS por meio
de filas SQS inscritas no tópico ("caixas de e-mail espiãs"):

- uma fila sem filtro, que recebe tudo o que é publicado;
- uma fila com a mesma filter policy de um cliente, para provar que cada
  cliente só recebe as próprias mensagens.

Uso: python3 scripts/teste_e2e.py            (STACK=sebo por padrão)
Requer credenciais da AWS válidas e boto3. Leva cerca de 4 minutos, por causa
do prazo de reserva (2 min) e da varredura de expiração (1 min).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

import boto3

REGIAO = "us-east-1"
STACK = os.environ.get("STACK", "sebo")
SUFIXO = uuid.uuid4().hex[:6]
ANA, BRUNO, CAIO = (f"{n}.{SUFIXO}@teste.com" for n in ("ana", "bruno", "caio"))

cf = boto3.client("cloudformation", region_name=REGIAO)
sqs = boto3.client("sqs", region_name=REGIAO)
sns = boto3.client("sns", region_name=REGIAO)

falhas = []


def verificar(descricao, condicao, detalhe=""):
    print(f"[{'OK ' if condicao else 'FALHOU'}] {descricao}" + (f" — {detalhe}" if detalhe and not condicao else ""))
    if not condicao:
        falhas.append(descricao)


def saidas_da_stack():
    stack = cf.describe_stacks(StackName=STACK)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


def api(metodo, caminho, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(API + caminho, data=dados, method=metodo,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def criar_fila_espia(nome, topico_arn, filtro_email=None):
    url = sqs.create_queue(QueueName=nome)["QueueUrl"]
    arn = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    politica = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow", "Principal": {"Service": "sns.amazonaws.com"},
            "Action": "sqs:SendMessage", "Resource": arn,
            "Condition": {"ArnEquals": {"aws:SourceArn": topico_arn}},
        }],
    }
    sqs.set_queue_attributes(QueueUrl=url, Attributes={"Policy": json.dumps(politica)})
    atributos = {}
    if filtro_email:
        atributos = {"FilterPolicy": json.dumps({"email": [filtro_email]}),
                     "FilterPolicyScope": "MessageAttributes"}
    inscricao = sns.subscribe(TopicArn=topico_arn, Protocol="sqs", Endpoint=arn,
                              Attributes=atributos, ReturnSubscriptionArn=True)["SubscriptionArn"]
    return url, inscricao


caixas = {"todos": [], "ana": []}


def drenar(url, destino):
    while True:
        r = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=1)
        msgs = r.get("Messages", [])
        if not msgs:
            return
        for m in msgs:
            env = json.loads(m["Body"])
            destino.append({
                "email": env.get("MessageAttributes", {}).get("email", {}).get("Value"),
                "assunto": env.get("Subject", ""),
                "texto": env.get("Message", ""),
            })
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])


def esperar_email(email, prefixo_assunto, limite_s):
    fim = time.time() + limite_s
    while time.time() < fim:
        drenar(URL_TODOS, caixas["todos"])
        drenar(URL_ANA, caixas["ana"])
        if any(m["email"] == email and m["assunto"].startswith(prefixo_assunto) for m in caixas["todos"]):
            return True
        time.sleep(3)
    return False


def status_de(livro_id, email):
    _, reservas = api("GET", f"/reservas?livroId={livro_id}")
    return any(r["email"] == email for r in reservas)


saidas = saidas_da_stack()
API = saidas["ApiUrl"].rstrip("/")
TOPICO = saidas["TopicoArn"]
print(f"API: {API}\nClientes de teste: {ANA}, {BRUNO}, {CAIO}\n")

URL_TODOS, SUB_TODOS = criar_fila_espia(f"sebo-espiao-todos-{SUFIXO}", TOPICO)
URL_ANA, SUB_ANA = criar_fila_espia(f"sebo-espiao-ana-{SUFIXO}", TOPICO, filtro_email=ANA)
time.sleep(5)  # propagação das inscrições

try:
    st, corpo = api("POST", "/livros", {"titulo": f"Livro de teste {SUFIXO}", "autor": "Teste",
                                        "preco": 10, "quantidade": 1})
    verificar("cadastrar livro com 1 exemplar (201)", st == 201, f"{st} {corpo}")
    livro = corpo["livroId"]

    st, r = api("POST", "/interesses", {"livroId": livro, "email": ANA.upper()})
    verificar("Ana registra interesse com estoque → RESERVADO", st == 201 and r.get("status") == "RESERVADO", f"{st} {r}")
    verificar("Ana recebe e-mail 'Reserva confirmada'", esperar_email(ANA, "Reserva confirmada", 30))

    st, r = api("POST", "/interesses", {"livroId": livro, "email": BRUNO})
    verificar("Bruno sem estoque → PENDENTE, posição 1", st == 201 and r.get("status") == "PENDENTE" and r.get("posicaoFila") == 1, f"{st} {r}")
    verificar("Bruno recebe e-mail 'Você está na fila'", esperar_email(BRUNO, "Você está na fila", 30))

    st, r = api("POST", "/interesses", {"livroId": livro, "email": CAIO})
    verificar("Caio sem estoque → PENDENTE, posição 2", st == 201 and r.get("posicaoFila") == 2, f"{st} {r}")

    st, r = api("POST", "/interesses", {"livroId": livro, "email": BRUNO})
    verificar("interesse duplicado do Bruno → 409", st == 409, f"{st} {r}")

    st, r = api("POST", f"/livros/{livro}/chegada", {"quantidade": 1})
    verificar("registrar chegada de 1 exemplar (200)", st == 200, f"{st} {r}")
    verificar("stream reserva para o Bruno (1º da fila) e envia e-mail",
              esperar_email(BRUNO, "Reserva confirmada", 60))
    verificar("Caio continua na fila (não furou)", not status_de(livro, CAIO))

    # Bruno compra no balcão antes do prazo; a Ana não aparece e perde a vez.
    _, reservas = api("GET", f"/reservas?livroId={livro}")
    do_bruno = [r for r in reservas if r["email"] == BRUNO]
    if do_bruno:
        st, r = api("POST", "/vendas", {"livroId": livro, "ordem": do_bruno[0]["ordem"]})
        verificar("venda da reserva ativa do Bruno (201)", st == 201 and "vendaId" in r, f"{st} {r}")
        st, r = api("POST", "/vendas", {"livroId": livro, "ordem": do_bruno[0]["ordem"]})
        verificar("segunda venda da mesma reserva → 409", st == 409, f"{st} {r}")
    else:
        verificar("reserva do Bruno ativa para vender", False, f"reservas ativas: {reservas}")

    print("\nAguardando a reserva da Ana expirar (prazo 2 min + varredura de 1 min)...")
    verificar("Ana recebe e-mail 'Reserva expirada'", esperar_email(ANA, "Reserva expirada", 240))
    verificar("exemplar devolvido passa para o Caio (próximo da fila)",
              esperar_email(CAIO, "Reserva confirmada", 60))

    _, livros = api("GET", "/livros")
    estado = next(l for l in livros if l["livroId"] == livro)
    verificar("estoque final: quantidade 1 (2 chegaram, 1 vendido), disponível 0 (Caio reservado)",
              estado["quantidade"] == 1 and estado["disponivel"] == 0, str(estado))

    drenar(URL_ANA, caixas["ana"])
    so_da_ana = all(m["email"] == ANA for m in caixas["ana"]) and len(caixas["ana"]) >= 2
    verificar("filtro SNS: a caixa da Ana só recebeu mensagens da Ana",
              so_da_ana, f"{[(m['email'], m['assunto']) for m in caixas['ana']]}")
finally:
    for sub in (SUB_TODOS, SUB_ANA):
        sns.unsubscribe(SubscriptionArn=sub)
    for url in (URL_TODOS, URL_ANA):
        sqs.delete_queue(QueueUrl=url)

print("\nE-mails publicados durante o teste:")
for m in caixas["todos"]:
    print(f"  {m['email']:<28} {m['assunto']}")
print(f"\n{'TUDO OK' if not falhas else f'{len(falhas)} FALHA(S)'}")
sys.exit(1 if falhas else 0)
