# Sebo na Nuvem — Documento de Design

INF1304 Distribuição e Concorrência — Trabalho 2 (2026/2)

## 1. Objetivo

Aplicação para um sebo hospedada na AWS Academy (Learner Lab). Um cliente informa, por uma página web, o livro em que tem interesse:

- se houver exemplar disponível, o exemplar fica **reservado** para ele por um prazo, e ele recebe um e-mail para comparecer à livraria e efetivar a compra;
- se não houver, ele entra numa **fila de espera** daquele livro (ordem de chegada). Quando um exemplar chegar, ou uma reserva anterior expirar, o primeiro da fila recebe a reserva e o e-mail;
- se o cliente não comprar dentro do prazo, a reserva expira e passa para o próximo da fila.

Os dados ficam num banco para controle de estoque e vendas.

Requisitos obrigatórios do enunciado: ≥ 3 funções Lambda, ≥ 1 tabela de banco, envio de e-mail e interface com usuário. Entrega: código e instruções num repositório Git; implementação numa conta da AWS Academy; relatório com o que funcionou e o que não funcionou, instalação, operação, diagrama de blocos e diagrama UML de sequência.

### Metas
- Fluxo completo de interesse → reserva → venda / expiração → próximo da fila.
- **Correção sob concorrência:** dois clientes nunca recebem o mesmo exemplar, e a fila é respeitada.
- Implantação reproduzível com um comando (`deploy.sh`).
- Lógica testada localmente com TDD, sem depender da conta da Academy.

### Fora do escopo
- Pagamento online (a compra acontece no balcão).
- Login e autenticação de usuários (o cliente se identifica pelo e-mail; a tela do funcionário não tem senha, e isso é registrado no relatório como limitação).
- Inscrição automática do cliente no tópico de e-mail (o enunciado manda considerar que o cliente já se inscreveu pela interface da AWS).

### Anti-metas (o que tornaria o trabalho um fracasso mesmo "funcionando")
- Dois clientes avisados de que o mesmo exemplar está reservado para eles.
- Um cliente que chegou depois passar na frente de quem já estava na fila.
- E-mail de um cliente chegando a todos os inscritos do tópico.

## 2. Restrições (AWS Academy Learner Lab)
- Não é possível criar papéis IAM: todas as Lambdas usam o papel existente `LabRole`.
- Região `us-east-1`.
- As credenciais expiram a cada sessão do lab (cerca de 4 h); os recursos persistem.
- O SES normalmente é bloqueado; o e-mail sai pelo **SNS** (protocolo `email`).
- Orçamento limitado: só serviços serverless, sem servidores ligados.

## 3. Abordagens consideradas (provisionamento)

| Abordagem | Prós | Contras |
|---|---|---|
| **CloudFormation + `deploy.sh`** (escolhida) | Reproduzível, um comando, qualquer integrante sobe na própria conta, o template documenta a arquitetura | Exige aprender a sintaxe do CloudFormation |
| Console manual + passo a passo | Sem ferramenta nova | Fácil errar, trabalhoso de refazer, código colado à mão |
| SAM / Terraform | Mais ergonômicos | Ferramentas extras; atrito com o Learner Lab (papéis IAM, credenciais temporárias) |

Interface: **página web estática no S3 + API Gateway** (escolhida), em vez de CLI local, por ser apresentável e totalmente hospedada na Academy.

Semântica de disponibilidade: **com reserva, fila FIFO e prazo** (escolhida), em vez de só avisar "tem o livro", que permitiria dois clientes irem atrás do mesmo exemplar.

## 4. Arquitetura

```
 Navegador ──► S3 (site estático: comprador.html, funcionario.html)
     │
     └──► API Gateway (HTTP API) ──► Lambdas de API ──► DynamoDB ──(Stream)──► alocar_reservas ──► SNS ──► e-mail
                                                            ▲                          │
                          EventBridge (a cada 1 min) ──► expirar_reservas ─────────────┘
```

### 4.1 Funções Lambda (Python 3.12)

| Função | Gatilho | Responsabilidade |
|---|---|---|
| `listar_livros` | `GET /livros` | Catálogo com quantidade disponível |
| `gerenciar_estoque` | `POST /livros`, `POST /livros/{id}/chegada` | Funcionário cadastra livro e registra chegada de N exemplares |
| `registrar_interesse` | `POST /interesses` | Cria o interesse na fila (`PENDENTE`) e tenta alocar imediatamente |
| `alocar_reservas` | DynamoDB Stream da tabela `Livros` | Quando `disponivel` aumenta, reserva exemplares para os primeiros da fila e envia os e-mails |
| `expirar_reservas` | EventBridge, a cada 1 min | Expira reservas vencidas, devolve o exemplar (o que aciona `alocar_reservas` para o próximo) e avisa o cliente |
| `registrar_venda` | `GET /reservas?livroId=`, `POST /vendas` | Funcionário lista as reservas ativas e confirma a venda de uma |

O código comum (acesso ao banco, alocação, envio de e-mail) fica num pacote compartilhado (`sebo/`), empacotado junto com cada Lambda.

### 4.2 Modelo de dados (DynamoDB)

**`Livros`** (PK `livroId`)
- `titulo`, `autor`, `preco`
- `quantidade`: exemplares físicos na loja (reservados ou não)
- `disponivel`: exemplares não reservados. Invariante: `0 ≤ disponivel ≤ quantidade`.
- Stream habilitado (`NEW_AND_OLD_IMAGES`).

**`Interesses`** (PK `livroId`, SK `ordem` = `<timestamp ISO>#<uuid>`)
- `email`, `status` ∈ {`PENDENTE`, `RESERVADO`, `VENDIDO`, `EXPIRADO`}, `criadoEm`, `reservadoEm`, `expiraEm`
- A ordenação da SK dá a fila FIFO por livro.
- GSI `status-expiraEm` (PK `status`, SK `expiraEm`) para encontrar reservas vencidas.

**`Vendas`** (PK `vendaId`)
- `livroId`, `email`, `preco`, `data`, `ordemInteresse`

### 4.3 Regras de concorrência

Todas as transições de estado usam **escritas condicionais / `TransactWriteItems`**, então execuções concorrentes de Lambdas não corrompem o estado:

- **Reservar** (único caminho para RESERVADO), em uma transação:
  `Livros.disponivel -= 1` com condição `disponivel > 0`, **e**
  `Interesse.status = RESERVADO, expiraEm = agora + PRAZO` com condição `status = PENDENTE`.
  Se a transação falha, outra execução já pegou o exemplar ou o interesse; o alocador relê e continua ou para.
- **Alocar(livroId):** enquanto `disponivel > 0`, pega o interesse `PENDENTE` mais antigo (query pela SK, ascendente) e tenta reservar. É idempotente, e várias execuções simultâneas são seguras. Chamado por `registrar_interesse` (logo após gravar o pendente) e por `alocar_reservas` (stream).
- **FIFO:** um interesse novo sempre entra como `PENDENTE` no fim da fila; só o alocador reserva, sempre do mais antigo. Logo, quem chega depois nunca passa na frente.
- **Expirar:** transação `Interesse RESERVADO → EXPIRADO` (condição `status = RESERVADO e expiraEm < agora`) + `Livros.disponivel += 1`. O aumento dispara o stream, e o próximo da fila é reservado.
- **Vender:** transação `Interesse RESERVADO → VENDIDO` (condição `status = RESERVADO`) + `Livros.quantidade -= 1` + inserção em `Vendas`. Se a reserva expirou um instante antes, a venda é recusada com mensagem clara.
- **Interesse duplicado:** o mesmo e-mail com interesse `PENDENTE` ou `RESERVADO` no mesmo livro é recusado (HTTP 409).

`PRAZO_RESERVA_MINUTOS` é parâmetro do template: **2 minutos por padrão** (pensado para a demonstração); o README explica como mudar para um valor realista (ex.: 2880 = 48 h).

### 4.4 E-mail (SNS)

- Um tópico `sebo-notificacoes`. Cada cliente se inscreve (protocolo email) pelo console e configura na inscrição a **filter policy** `{"email": ["cliente@exemplo.com"]}`. O README traz o passo a passo, e o script opcional `scripts/inscrever_cliente.sh` faz o mesmo pela CLI.
- As Lambdas publicam com o atributo de mensagem `email`, então só o destinatário recebe.
- Mensagens: **reserva confirmada** (livro, prazo, endereço da loja), **reserva expirada** (perdeu a vez; pode registrar novo interesse) e **interesse registrado / na fila** (posição na fila).

### 4.5 API (HTTP API, CORS liberado para o site)

| Método | Rota | Corpo / resposta |
|---|---|---|
| GET | `/livros` | `[{livroId, titulo, autor, preco, quantidade, disponivel}]` |
| POST | `/livros` | `{titulo, autor, preco, quantidade}` → `201 {livroId}` |
| POST | `/livros/{id}/chegada` | `{quantidade}` → `200` |
| POST | `/interesses` | `{livroId, email}` → `201 {status: RESERVADO\|PENDENTE, posicaoFila?, expiraEm?}`; `409` se duplicado; `404` se o livro não existe |
| GET | `/reservas?livroId=` | reservas `RESERVADO` ativas |
| POST | `/vendas` | `{livroId, ordem}` → `201 {vendaId}`; `409` se a reserva não está mais ativa |

Erros de validação → `400` com `{erro: "..."}`.

### 4.6 Interface (S3, HTML + JS puro)
- `comprador.html`: catálogo, campo de e-mail e botão "Tenho interesse"; mostra se ficou reservado (com prazo) ou a posição na fila.
- `funcionario.html`: cadastrar livro, registrar chegada, listar reservas ativas por livro e confirmar venda.
- A URL da API é injetada num `config.js` gerado pelo `deploy.sh`.

## 5. Infraestrutura e implantação
- `infra/template.yaml` (CloudFormation): 3 tabelas (stream em `Livros`, GSI em `Interesses`), tópico SNS, 6 Lambdas com `Role: arn:aws:iam::<conta>:role/LabRole`, HTTP API + integrações + permissões, regra EventBridge, mapeamento do stream, bucket S3 com hospedagem de site estático e acesso público de leitura.
- `deploy.sh`: empacota as Lambdas (zip), cria/usa um bucket de artefatos, roda `aws cloudformation deploy`, gera o `config.js` e sincroniza o site no S3. Imprime as URLs do site e da API.
- `destroy.sh`: esvazia os buckets e apaga a stack.
- `scripts/popular.sh`: carrega alguns livros de exemplo.
- Roda no CloudShell do console ou numa máquina com AWS CLI e as credenciais do lab ("AWS Details" → `~/.aws/credentials`).

## 6. Testes (TDD)
- `pytest` + `moto` (DynamoDB e SNS simulados). Cada regra da seção 4.3 vira teste antes do código, por exemplo:
  - interesse com estoque → RESERVADO, `disponivel` decrementado, e-mail publicado com atributo correto;
  - interesse sem estoque → PENDENTE com posição correta, sem e-mail de reserva;
  - chegada de N exemplares com M pendentes → os min(N, M) mais antigos reservados, em ordem;
  - expiração → próximo da fila reservado, e-mail de expiração enviado;
  - venda de reserva expirada → recusada;
  - duplicado → 409;
  - concorrência: muitas tentativas simultâneas (threads) de reservar o último exemplar → exatamente uma vence.
- Handlers testados com eventos de API Gateway, Stream e EventBridge de exemplo.
- Teste manual de ponta a ponta na AWS (roteiro no README), com evidências (prints) no relatório.

## 7. Organização do repositório
```
lambdas/<nome>/handler.py   # um handler fino por função
sebo/                       # lógica compartilhada (repositório, alocação, notificação)
tests/
web/                        # comprador.html, funcionario.html, app.js, estilo.css
infra/template.yaml
deploy.sh  destroy.sh  scripts/
docs/                       # design, relatório, diagramas (Mermaid)
README.md                   # instalação e operação
```
Desenvolvimento em branches por funcionalidade, commits pequenos e merge na `main` só com testes passando.

## 8. Relatório (entregável)
`docs/relatorio.md`: o que foi implementado, o que funcionou e o que não funcionou, instalação, operação, **diagrama de blocos** (arquitetura da seção 4) e **diagramas UML de sequência** (interesse com estoque; interesse sem estoque → chegada → reserva; expiração → próximo da fila), em Mermaid e exportados como imagem.

## 9. Decisões tomadas pelo implementador (revisáveis)
- Python 3.12 e DynamoDB.
- Estoque modelado como `quantidade` + `disponivel` no próprio livro, sem um item por exemplar físico.
- Alocação disparada pelo stream de `Livros` (desacopla chegada/expiração do envio de e-mails).
- Prazo configurável (padrão 2 min); a varredura de expiração a cada 1 min (o TTL do DynamoDB pode atrasar até 48 h, então não serve).
- Cliente identificado só pelo e-mail; sem autenticação.
- Também é enviado e-mail de "você está na fila (posição X)" ao registrar interesse sem estoque.
