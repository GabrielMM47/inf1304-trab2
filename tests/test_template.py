import importlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
TEMPLATE = RAIZ / "infra" / "template.yaml"

FUNCOES = [
    "listar_livros",
    "gerenciar_estoque",
    "registrar_interesse",
    "alocar_reservas",
    "expirar_reservas",
    "registrar_venda",
]

ROTAS = {
    "GET /livros",
    "POST /livros",
    "POST /livros/{id}/chegada",
    "POST /interesses",
    "GET /reservas",
    "POST /vendas",
}

VARIAVEIS = {
    "TABELA_LIVROS",
    "TABELA_INTERESSES",
    "TABELA_VENDAS",
    "TOPICO_SNS",
    "PRAZO_RESERVA_MINUTOS",
}


class _CfnLoader(yaml.SafeLoader):
    pass


def _tag(loader, prefixo, no):
    if isinstance(no, yaml.ScalarNode):
        valor = loader.construct_scalar(no)
    elif isinstance(no, yaml.SequenceNode):
        valor = loader.construct_sequence(no, deep=True)
    else:
        valor = loader.construct_mapping(no, deep=True)
    nome = prefixo.lstrip("!")
    chave = "Ref" if nome == "Ref" else f"Fn::{nome}"
    return {chave: valor}


_CfnLoader.add_multi_constructor("!", _tag)


@pytest.fixture(scope="module")
def template():
    with open(TEMPLATE, encoding="utf-8") as f:
        return yaml.load(f, Loader=_CfnLoader)


def _recursos(template, tipo):
    return {
        nome: r
        for nome, r in template["Resources"].items()
        if r["Type"] == tipo
    }


def test_cfn_lint_sem_erros():
    cfn_lint = shutil.which("cfn-lint") or str(Path(sys.executable).parent / "cfn-lint")
    proc = subprocess.run(
        [cfn_lint, str(TEMPLATE)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_lambdas_usam_labrole_e_nenhum_iam(template):
    funcoes = _recursos(template, "AWS::Lambda::Function")
    assert len(funcoes) == 6
    for nome, f in funcoes.items():
        assert "role/LabRole" in str(f["Properties"]["Role"]), nome
    for nome, r in template["Resources"].items():
        assert not r["Type"].startswith("AWS::IAM::"), nome


def test_lambdas_handler_codigo_e_ambiente(template):
    funcoes = _recursos(template, "AWS::Lambda::Function")
    handlers = set()
    for nome, f in funcoes.items():
        p = f["Properties"]
        assert p["Runtime"] == "python3.12", nome
        assert p["Timeout"] == 30, nome
        assert p["Code"] == {
            "S3Bucket": {"Ref": "PacoteS3Bucket"},
            "S3Key": {"Ref": "PacoteS3Key"},
        }, nome
        assert set(p["Environment"]["Variables"]) == VARIAVEIS, nome
        handlers.add(p["Handler"])
    assert handlers == {f"lambdas.{n}.handler.lambda_handler" for n in FUNCOES}


@pytest.mark.parametrize("nome", FUNCOES)
def test_handler_importavel_pelo_caminho_pontuado(nome):
    modulo = importlib.import_module(f"lambdas.{nome}.handler")
    assert callable(modulo.lambda_handler)


def test_rotas_da_api(template):
    rotas = _recursos(template, "AWS::ApiGatewayV2::Route")
    assert {r["Properties"]["RouteKey"] for r in rotas.values()} == ROTAS


def test_prazo_padrao_2(template):
    p = template["Parameters"]["PrazoReservaMinutos"]
    assert p["Type"] == "Number"
    assert p["Default"] == 2


def test_topico_sns_e_outputs(template):
    topicos = _recursos(template, "AWS::SNS::Topic")
    assert [t["Properties"]["TopicName"] for t in topicos.values()] == [
        "sebo-notificacoes"
    ]
    assert set(template["Outputs"]) == {"ApiUrl", "SiteUrl", "SiteBucket", "TopicoArn"}


def test_expiracao_a_cada_minuto(template):
    regras = _recursos(template, "AWS::Events::Rule")
    assert [r["Properties"]["ScheduleExpression"] for r in regras.values()] == [
        "rate(1 minute)"
    ]


def test_pacote_contem_so_lambdas_e_sebo(tmp_path):
    destino = tmp_path / "pacote.zip"
    subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "empacotar.py"), str(destino)],
        check=True,
        cwd=RAIZ,
        capture_output=True,
    )
    with zipfile.ZipFile(destino) as z:
        nomes = z.namelist()
    assert "sebo/contexto.py" in nomes
    for n in FUNCOES:
        assert f"lambdas/{n}/handler.py" in nomes
    for n in nomes:
        assert n.split("/")[0] in ("lambdas", "sebo"), n
        assert "__pycache__" not in n and not n.endswith(".pyc"), n


def test_pacote_deterministico(tmp_path):
    hashes = []
    for i in range(2):
        proc = subprocess.run(
            [sys.executable, str(RAIZ / "scripts" / "empacotar.py"), str(tmp_path / f"p{i}.zip")],
            check=True,
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        hashes.append(proc.stdout.strip())
    assert hashes[0] == hashes[1]
    assert len(hashes[0]) == 12
    assert (tmp_path / "p0.zip").read_bytes() == (tmp_path / "p1.zip").read_bytes()
