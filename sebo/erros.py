class ErroSebo(Exception):
    status: int = 500


class DadosInvalidos(ErroSebo):
    status = 400


class LivroNaoEncontrado(ErroSebo):
    status = 404


class InteresseDuplicado(ErroSebo):
    status = 409


class ReservaInativa(ErroSebo):
    status = 409
