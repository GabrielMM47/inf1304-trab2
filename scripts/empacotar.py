"""Gera o pacote único das Lambdas (lambdas/ e sebo/ na raiz do zip).

Uso: python3 scripts/empacotar.py <destino.zip>
Imprime os 12 primeiros caracteres do SHA-256 do zip. O zip é determinístico
(entradas ordenadas, data fixa, permissões fixas): a mesma árvore de código gera
sempre o mesmo hash, e o deploy só envia um pacote novo quando o código muda.
"""

import hashlib
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIRETORIOS = ("lambdas", "sebo")
DATA_FIXA = (1980, 1, 1, 0, 0, 0)


def arquivos():
    for nome in DIRETORIOS:
        for caminho in (RAIZ / nome).rglob("*.py"):
            if "__pycache__" not in caminho.parts:
                yield caminho.relative_to(RAIZ).as_posix()


def empacotar(destino: Path) -> str:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(arquivos()):
            info = zipfile.ZipInfo(rel, date_time=DATA_FIXA)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, (RAIZ / rel).read_bytes())
    return hashlib.sha256(destino.read_bytes()).hexdigest()[:12]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: empacotar.py <destino.zip>")
    print(empacotar(Path(sys.argv[1])))
