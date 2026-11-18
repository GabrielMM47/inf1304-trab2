# Sebo na Nuvem

Sistema de reservas de livros usados, implantado na AWS Academy (Learner Lab, região `us-east-1`). Trabalho 2 da disciplina INF1304 (Distribuição e Concorrência), 2026/2.

O cliente informa, numa página web, o livro em que tem interesse:

- se há exemplar disponível, o exemplar fica **reservado** para ele por um prazo e ele recebe um e-mail para ir à livraria efetivar a compra;
- se não há, ele entra na **fila de espera** daquele livro (ordem de chegada) e recebe um e-mail com a posição;
- se não comprar dentro do prazo, a reserva **expira** e o exemplar passa para o próximo da fila.

O funcionário cadastra livros, registra a chegada de exemplares, vê as reservas ativas e confirma vendas.

A descrição completa (requisitos, modelo de dados, regras de concorrência e API) está em [docs/design.md](docs/design.md). O diagrama de blocos da arquitetura está na seção [4. Arquitetura](docs/design.md#4-arquitetura).

## Pré-requisitos

- Uma conta do **AWS Academy Learner Lab**, com o lab iniciado (botão **Start Lab**, aguardar a bolinha ficar verde).
- Um dos dois ambientes:
  - **CloudShell** (recomendado): no console da AWS, na região `us-east-1`, abra o CloudShell. Já vem com AWS CLI e Python 3; não é preciso instalar nada.
  - **Máquina local**: AWS CLI v2, Python 3 e `bash`. Copie as credenciais do lab (**AWS Details** → **Show** em *AWS CLI*) para `~/.aws/credentials`:
    ```ini
    [default]
    aws_access_key_id = ...
    aws_secret_access_key = ...
    aws_session_token = ...
    ```
    As credenciais expiram junto com a sessão do lab (cerca de 4 h). Quando isso acontecer, o `deploy.sh` avisa que elas são inválidas: inicie o lab de novo e atualize o arquivo.

O Learner Lab não permite criar papéis IAM, então todas as Lambdas usam o papel existente `LabRole`.

## Instalação

```bash
git clone https://github.com/GabrielMM47/inf1304-trab2.git
cd inf1304-trab2
./deploy.sh
```

O `deploy.sh`:

1. confere as credenciais (`aws sts get-caller-identity`) e cria o bucket de artefatos `sebo-artefatos-<conta>`, se não existir;
2. empacota as Lambdas num único zip com `scripts/empacotar.py` (só biblioteca padrão do Python) e envia ao bucket;
3. implanta a stack CloudFormation `sebo` a partir de `infra/template.yaml`;
4. gera `build/config.js` com a URL da API e publica o site (`web/`) no bucket do site;
5. imprime a URL do site, a URL da API e o ARN do tópico SNS.

Se a stack estiver em `ROLLBACK_COMPLETE` (porque a primeira implantação falhou), o script a apaga e refaz a implantação. Para reimplantar depois de mudar o código, basta rodar `./deploy.sh` de novo: só um pacote novo é enviado quando o código muda.

Variáveis opcionais:

- `STACK`: nome da stack (padrão `sebo`). Os nomes das tabelas e funções derivam dele.
- `PRAZO_RESERVA_MINUTOS`: prazo da reserva em minutos (padrão `2`). Ver [Como mudar o prazo](#como-mudar-o-prazo).

Depois de implantar, carregue alguns livros de exemplo:

```bash
scripts/popular.sh
```

Esse script cadastra 5 livros pela API. Rodá-lo de novo cadastra os livros outra vez, em duplicata.

## Notificações por e-mail (SNS)

Os e-mails saem por um tópico SNS (`sebo-notificacoes`), com protocolo `email`. Cada cliente precisa se inscrever no tópico **uma vez**, com uma **filter policy** que contém o próprio e-mail.

Por que o filtro é necessário: o tópico é único e todas as mensagens chegam a todos os inscritos. Sem o filtro, cada cliente receberia os e-mails de reserva, fila e expiração de todos os outros. Cada publicação leva o atributo de mensagem `email` com o destinatário, e a filter policy deixa passar só a mensagem cujo `email` é igual ao do inscrito. Os e-mails são normalizados para minúsculas (tanto no cadastro do interesse quanto na inscrição do script), então a filter policy deve estar em minúsculas.

### Pelo console

1. Console da AWS → **Amazon SNS** → **Topics** → `sebo-notificacoes` → **Create subscription**.
2. **Protocol**: `Email`. **Endpoint**: o e-mail do cliente, em minúsculas.
3. Expanda **Subscription filter policy** e marque **Enable subscription filter policy**.
4. **Filter policy scope**: `Message attributes`.
5. Em **Subscription filter policy**, cole o JSON abaixo, trocando o e-mail:
   ```json
   {
     "email": ["cliente@exemplo.com"]
   }
   ```
6. Clique em **Create subscription**.
7. O cliente abre o e-mail "AWS Notification - Subscription Confirmation" e clica em **Confirm subscription**. Enquanto isso não for feito, a inscrição fica *pending confirmation* e nenhum e-mail é entregue.

### Pelo script

```bash
scripts/inscrever_cliente.sh cliente@exemplo.com
```

O script converte o e-mail para minúsculas, lê o `TopicoArn` das saídas da stack e cria a inscrição com a mesma filter policy. Depois, o cliente ainda precisa confirmar pelo link do e-mail.

## Operação

### Site

Abra a **URL do site** impressa pelo `deploy.sh` (também está em *Outputs* da stack, chave `SiteUrl`). Há duas páginas:

- **Área do comprador** (`comprador.html`): lista os livros com estoque. Informe o e-mail, clique em **Tenho interesse** e a página mostra se o livro ficou reservado (com o horário limite) ou a posição na fila. Também é possível atualizar o catálogo.
- **Área do funcionário** (`funcionario.html`): cadastra livro (título, autor, preço, quantidade); registra a chegada de N exemplares de um livro já cadastrado; lista as reservas ativas de um livro e confirma a venda de uma delas.

Os horários na tela aparecem no fuso do navegador; os e-mails informam o horário em UTC.

### Demonstração da expiração

Com o prazo padrão de 2 minutos:

1. Cadastre um livro com `quantidade` = 1 na área do funcionário (ou use um dos livros de `popular.sh` com 1 exemplar).
2. Na área do comprador, com o e-mail `a@exemplo.com` (inscrito no tópico), clique em **Tenho interesse**. Deve chegar o e-mail "Reserva confirmada".
3. Com o e-mail `b@exemplo.com` (também inscrito), faça o mesmo pedido. Ele entra na fila e recebe o e-mail "Você está na fila".
4. Aguarde cerca de 2 minutos. A varredura roda a cada 1 minuto, então a expiração pode demorar até 1 minuto a mais.
5. A reserva de `a` expira: `a` recebe o e-mail "Reserva expirada", e `b` recebe a reserva ("Reserva confirmada").

Enquanto a reserva de `b` estiver ativa, ela aparece em **Reservas ativas** na área do funcionário, onde a venda pode ser confirmada.

### Como mudar o prazo

O prazo é o parâmetro `PrazoReservaMinutos` do template (padrão `2`, pensado para a demonstração; `2880` equivale a 48 h). Há três formas:

1. **Pelo deploy** (recomendada, fica no código): `PRAZO_RESERVA_MINUTOS=2880 ./deploy.sh`.
2. **Pelo console do CloudFormation**: **CloudFormation** → stack `sebo` → **Update** → **Use current template** → altere o parâmetro `PrazoReservaMinutos` → avance e confirme.
3. **Pelo console do Lambda**: **Lambda** → função (por exemplo `sebo-registrar_interesse`) → **Configuration** → **Environment variables** → altere `PRAZO_RESERVA_MINUTOS`. Atenção: a alteração vale só para a função editada (cada uma das seis Lambdas tem sua própria cópia da variável), e é sobrescrita pelo próximo `./deploy.sh`. Por isso as formas 1 e 2 são mais seguras.

Reservas já criadas mantêm o `expiraEm` que tinham; a mudança vale para as reservas feitas depois.

### Teste de concorrência

O script `scripts/teste_concorrencia.py` dispara vários pedidos de interesse ao mesmo tempo para um mesmo livro e conta o resultado:

```bash
API=$(aws cloudformation describe-stacks --stack-name sebo \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
curl -s "$API/livros"   # anote o livroId de um livro com quantidade = 1
python3 scripts/teste_concorrencia.py "$API" <livroId> 20
```

Argumentos: `<api_url> <livroId> <n> [copias]`. Com `n` pedidos simultâneos (e-mails `cliente1@teste.com` a `clienteN@teste.com`) e `copias` exemplares (padrão 1), o resultado esperado é exatamente `copias` pedidos `RESERVADO`, e os demais `PENDENTE`. O script imprime a contagem por status e sai com código 1 se o número de `RESERVADO` for diferente. Use um livro novo a cada execução: e-mails que já têm interesse pendente ou reservado no mesmo livro são recusados (409) e contados como `erro`.

## Testes locais

Os testes não usam a conta da AWS: DynamoDB e SNS são simulados com `moto`.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Remoção

```bash
./destroy.sh
```

Esvazia o bucket do site, apaga a stack `sebo` (com as tabelas, as Lambdas, a API, o tópico e o bucket do site) e apaga o bucket de artefatos. **Os dados (livros, reservas e vendas) são apagados junto com as tabelas.** Como o script também apaga o bucket de artefatos, o próximo `./deploy.sh` recria tudo do zero.

## Estrutura do repositório

```
lambdas/<nome>/handler.py   handlers finos, um por função Lambda
sebo/                       lógica compartilhada (estoque, fila, reservas, e-mail)
tests/                      testes com pytest e moto
web/                        páginas do comprador e do funcionário (HTML + JS puro)
infra/template.yaml         stack CloudFormation
deploy.sh  destroy.sh       implantação e remoção
scripts/                    popular.sh, inscrever_cliente.sh, teste_concorrencia.py, empacotar.py
docs/design.md              documento de design
```

## Limitações conhecidas

- **Sem autenticação.** A área do funcionário não tem senha e qualquer pessoa com a URL pode cadastrar livros, registrar chegadas e confirmar vendas. O cliente se identifica só pelo e-mail.
- **Interesse duplicado não é transacional.** A verificação de "já existe interesse PENDENTE ou RESERVADO deste e-mail neste livro" e a gravação do novo interesse não são atômicas: dois pedidos idênticos do mesmo e-mail, enviados exatamente ao mesmo tempo, podem ambos entrar na fila.
- **E-mail perdido se a publicação falhar.** A reserva é gravada antes do envio do e-mail. Se a publicação no SNS falhar depois disso, o cliente não recebe o aviso, mas a reserva continua válida.
- **Sem inscrição confirmada, sem e-mail.** Um cliente sem inscrição confirmada no tópico, ou sem a filter policy com o próprio e-mail, não recebe nenhuma notificação. A reserva e a fila funcionam do mesmo jeito.
- **Expiração com atraso.** A varredura de expiração roda a cada 1 minuto, então uma reserva pode continuar ativa até cerca de 1 minuto depois do horário limite.
- **Credenciais temporárias.** No Learner Lab, o acesso local expira com a sessão do lab; é preciso atualizar `~/.aws/credentials` depois.
