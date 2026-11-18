#!/usr/bin/env bash
# Implanta o Sebo na Nuvem no AWS Academy Learner Lab (us-east-1).
# Uso: ./deploy.sh   (variáveis opcionais: STACK, PRAZO_RESERVA_MINUTOS)
set -euo pipefail

REGION=us-east-1
export AWS_DEFAULT_REGION="$REGION"
STACK="${STACK:-sebo}"
PRAZO="${PRAZO_RESERVA_MINUTOS:-2}"

cd "$(dirname "$0")"

if ! CONTA=$(aws sts get-caller-identity --query Account --output text); then
  echo "ERRO: credenciais AWS inválidas ou expiradas. Copie as credenciais do lab (AWS Details) para ~/.aws/credentials." >&2
  exit 1
fi
ARTEFATOS="sebo-artefatos-${CONTA}"

if ! aws s3api head-bucket --bucket "$ARTEFATOS" >/dev/null 2>&1; then
  echo "Criando bucket de artefatos $ARTEFATOS..."
  aws s3api create-bucket --bucket "$ARTEFATOS" >/dev/null
fi

echo "Empacotando as Lambdas..."
mkdir -p build
HASH=$(python3 scripts/empacotar.py build/pacote.zip)
CHAVE="pacote-${HASH}.zip"
if ! aws s3api head-object --bucket "$ARTEFATOS" --key "$CHAVE" >/dev/null 2>&1; then
  aws s3 cp build/pacote.zip "s3://${ARTEFATOS}/${CHAVE}"
fi

ESTADO=$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].StackStatus" --output text 2>/dev/null || true)
if [ "$ESTADO" = "ROLLBACK_COMPLETE" ] || [ "$ESTADO" = "ROLLBACK_FAILED" ]; then
  echo "AVISO: a stack $STACK está em $ESTADO porque a primeira implantação falhou." >&2
  echo "Uma stack nesse estado não pode ser atualizada; apagando-a antes de implantar de novo..." >&2
  aws cloudformation delete-stack --stack-name "$STACK"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK"
fi

echo "Implantando a stack $STACK..."
aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file infra/template.yaml \
  --s3-bucket "$ARTEFATOS" \
  --s3-prefix templates \
  --parameter-overrides \
    "PrazoReservaMinutos=${PRAZO}" \
    "PacoteS3Bucket=${ARTEFATOS}" \
    "PacoteS3Key=${CHAVE}" \
  --no-fail-on-empty-changeset

saida() {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
API_URL=$(saida ApiUrl)
SITE_URL=$(saida SiteUrl)
SITE_BUCKET=$(saida SiteBucket)
TOPICO_ARN=$(saida TopicoArn)

printf 'window.SEBO_API = "%s";\n' "$API_URL" > build/config.js

if [ -d web ]; then
  echo "Publicando o site em s3://${SITE_BUCKET}/..."
  aws s3 sync web/ "s3://${SITE_BUCKET}/" --delete --exclude config.js
  aws s3 cp build/config.js "s3://${SITE_BUCKET}/config.js" --content-type application/javascript
else
  echo "AVISO: diretório web/ não encontrado; site não publicado (build/config.js foi gerado mesmo assim)." >&2
fi

echo
echo "Site:       ${SITE_URL}"
echo "API:        ${API_URL}"
echo "Tópico SNS: ${TOPICO_ARN}"
