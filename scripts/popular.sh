#!/usr/bin/env bash
# Carrega 5 livros de exemplo pela API (POST /livros).
# Uso: scripts/popular.sh   (variável opcional: STACK)
# Atenção: rodar de novo cadastra os livros outra vez (duplicados, com novos livroId).
set -euo pipefail

REGION=us-east-1
export AWS_DEFAULT_REGION="$REGION"
STACK="${STACK:-sebo}"

API_URL=$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)

livro() {
  echo "Cadastrando: $1"
  curl --fail-with-body -sS -X POST "${API_URL}/livros" \
    -H "content-type: application/json" \
    -d "{\"titulo\": \"$1\", \"autor\": \"$2\", \"preco\": $3, \"quantidade\": $4}"
  echo
}

livro "Dom Casmurro" "Machado de Assis" 25.00 3
livro "Memórias Póstumas de Brás Cubas" "Machado de Assis" 30.00 2
livro "Grande Sertão: Veredas" "João Guimarães Rosa" 45.00 1
livro "Vidas Secas" "Graciliano Ramos" 20.00 0
livro "O Cortiço" "Aluísio Azevedo" 18.50 2
