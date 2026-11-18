from datetime import datetime, timezone

FORMATO = "%Y-%m-%dT%H:%M:%S.%fZ"


def iso(dt: datetime) -> str:
    """Formata um datetime como UTC no formato fixo da aplicação."""
    return dt.astimezone(timezone.utc).strftime(FORMATO)


def de_iso(s: str) -> datetime:
    """Lê uma string no formato fixo e devolve datetime ciente de fuso (UTC)."""
    return datetime.strptime(s, FORMATO).replace(tzinfo=timezone.utc)
