#!/usr/bin/env bash
# Desliga a varredura de expiração (regra EventBridge que roda a cada minuto),
# a única parte do sistema que executa sozinha. Os demais recursos só geram
# custo quando são usados, então ficam implantados para consulta/correção.
# Enquanto pausado, reservas vencidas não expiram. Use scripts/retomar.sh
# antes de testar ou apresentar.
set -euo pipefail

export AWS_DEFAULT_REGION=us-east-1
STACK="${STACK:-sebo}"

REGRA=$(aws cloudformation describe-stack-resource --stack-name "$STACK" \
  --logical-resource-id RegraExpiracao \
  --query "StackResourceDetail.PhysicalResourceId" --output text)

aws events disable-rule --name "$REGRA"
echo "Varredura de expiração PAUSADA ($REGRA)."
echo "Para religar: ./scripts/retomar.sh"
