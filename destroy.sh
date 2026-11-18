#!/usr/bin/env bash
# Remove tudo o que o deploy.sh criou: site, stack e bucket de artefatos.
# Uso: ./destroy.sh   (variável opcional: STACK)
set -euo pipefail

REGION=us-east-1
export AWS_DEFAULT_REGION="$REGION"
STACK="${STACK:-sebo}"

CONTA=$(aws sts get-caller-identity --query Account --output text)
ARTEFATOS="sebo-artefatos-${CONTA}"

if aws cloudformation describe-stacks --stack-name "$STACK" >/dev/null 2>&1; then
  SITE_BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='SiteBucket'].OutputValue" --output text)
  if [ -n "$SITE_BUCKET" ] && [ "$SITE_BUCKET" != "None" ]; then
    echo "Esvaziando o bucket do site $SITE_BUCKET..."
    aws s3 rm "s3://${SITE_BUCKET}" --recursive
  fi
  echo "Apagando a stack $STACK..."
  aws cloudformation delete-stack --stack-name "$STACK"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK"
else
  echo "Stack $STACK não existe; nada a apagar."
fi

if aws s3api head-bucket --bucket "$ARTEFATOS" >/dev/null 2>&1; then
  echo "Apagando o bucket de artefatos $ARTEFATOS..."
  aws s3 rb "s3://${ARTEFATOS}" --force
fi

echo "Pronto."
