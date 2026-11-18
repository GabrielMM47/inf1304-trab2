#!/usr/bin/env bash
# Inscreve um cliente no tópico SNS de notificações, com filter policy pelo e-mail.
# Uso: scripts/inscrever_cliente.sh <email>   (variável opcional: STACK)
# Após o comando, o cliente precisa clicar no link de confirmação enviado ao e-mail.
set -euo pipefail

REGION=us-east-1
export AWS_DEFAULT_REGION="$REGION"
STACK="${STACK:-sebo}"

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo "uso: $0 <email>" >&2
  exit 1
fi

EMAIL=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')

TOPICO=$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='TopicoArn'].OutputValue" --output text)

# json.dumps escapa o e-mail corretamente (aspas, barras etc.).
ATRIBUTOS=$(python3 -c '
import json, sys
email = sys.argv[1]
print(json.dumps({
    "FilterPolicy": json.dumps({"email": [email]}),
    "FilterPolicyScope": "MessageAttributes",
}))' "$EMAIL")

aws sns subscribe \
  --topic-arn "$TOPICO" \
  --protocol email \
  --notification-endpoint "$EMAIL" \
  --attributes "$ATRIBUTOS" \
  --output text

echo "Inscrição criada para $EMAIL (filtro: email = $EMAIL)."
echo "Lembrete: o cliente precisa abrir o e-mail da AWS e clicar em \"Confirm subscription\"."
