#!/usr/bin/env bash
# Religa a varredura de expiração de reservas (regra EventBridge a cada minuto).
# Reservas que venceram durante a pausa expiram na primeira execução.
set -euo pipefail

export AWS_DEFAULT_REGION=us-east-1
STACK="${STACK:-sebo}"

REGRA=$(aws cloudformation describe-stack-resource --stack-name "$STACK" \
  --logical-resource-id RegraExpiracao \
  --query "StackResourceDetail.PhysicalResourceId" --output text)

aws events enable-rule --name "$REGRA"
echo "Varredura de expiração ATIVA ($REGRA)."
