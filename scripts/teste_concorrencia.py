"""Dispara N pedidos de interesse simultâneos para um mesmo livro.

Uso: python3 scripts/teste_concorrencia.py <api_url> <livroId> <n> [copias]

Cada pedido usa um e-mail diferente (cliente{i}@teste.com). Com `copias`
exemplares disponíveis, o esperado é exatamente `copias` pedidos RESERVADO;
os demais ficam PENDENTE. O script sai com código 1 se a contagem de RESERVADO
for diferente de `copias`.
"""

import argparse
import collections
import json
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def enviar(api_url, livro_id, email, barreira):
    corpo = json.dumps({"livroId": livro_id, "email": email}).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url}/interesses",
        data=corpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    barreira.wait()  # todas as threads partem juntas
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8")).get("status", "erro")
    except urllib.error.HTTPError:
        return "erro"
    except (urllib.error.URLError, OSError, ValueError):
        return "erro"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("api_url")
    parser.add_argument("livro_id")
    parser.add_argument("n", type=int)
    parser.add_argument("copias", type=int, nargs="?", default=1)
    args = parser.parse_args()
    if args.n < 1 or args.copias < 0:
        parser.error("n deve ser >= 1 e copias >= 0")

    api_url = args.api_url.rstrip("/")
    barreira = threading.Barrier(args.n)
    with ThreadPoolExecutor(max_workers=args.n) as pool:
        futuros = [
            pool.submit(enviar, api_url, args.livro_id, f"cliente{i}@teste.com", barreira)
            for i in range(1, args.n + 1)
        ]
        resultados = [f.result() for f in futuros]

    contagem = collections.Counter(resultados)
    print(f"Pedidos simultâneos: {args.n} | exemplares esperados: {args.copias}")
    for status in ("RESERVADO", "PENDENTE", "erro"):
        print(f"  {status:<10} {contagem.get(status, 0)}")

    reservados = contagem.get("RESERVADO", 0)
    if reservados != args.copias:
        print(f"FALHOU: {reservados} RESERVADO, esperado {args.copias}.")
        return 1
    print("OK: contagem de reservas correta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
