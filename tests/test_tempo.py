from datetime import datetime, timezone

from sebo.tempo import de_iso, iso


def test_iso_formato_fixo_e_ida_e_volta():
    dt = datetime(2026, 11, 17, 12, 0, 0, 123456, tzinfo=timezone.utc)
    assert iso(dt) == "2026-11-17T12:00:00.123456Z"
    assert de_iso(iso(dt)) == dt
