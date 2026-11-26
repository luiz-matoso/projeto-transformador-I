from datetime import datetime, timedelta, timezone
from collections.abc import Mapping


DEFAULT_VALIDITY_PERIOD = timedelta(hours=24)


def evaluate_observation(observation: Mapping | None, *, validity_period: timedelta = DEFAULT_VALIDITY_PERIOD,
                         evaluated_at: datetime | None = None) -> dict:
    """Validade em [observed_at, expires_at); datas devem informar fuso horário."""
    if not isinstance(validity_period, timedelta) or validity_period <= timedelta(0):
        raise ValueError("O prazo de validade deve ser um timedelta positivo")
    now = evaluated_at if evaluated_at is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("evaluated_at deve conter fuso horário")
    now = now.astimezone(timezone.utc)
    data = observation or {}
    raw = data.get("observed_at")
    result = {"source": data.get("source"), "observed_at": raw.isoformat() if isinstance(raw, datetime) else raw,
              "evaluated_at": now.isoformat(), "validity_seconds": validity_period.total_seconds(),
              "expires_at": None, "is_valid": False}
    if raw is None or raw == "":
        code, message = "observation_date_missing", "Data e hora da observação ausentes."
    else:
        try:
            date = datetime.fromisoformat(raw.replace("Z", "+00:00")) if isinstance(raw, str) else raw
            if not isinstance(date, datetime) or date.tzinfo is None or date.utcoffset() is None:
                raise ValueError("Data sem fuso horário")
            date = date.astimezone(timezone.utc)
            expires = date + validity_period
            result.update(observed_at=date.isoformat(), expires_at=expires.isoformat())
            if date > now:
                code, message = "observation_date_future", "A data da observação está no futuro."
            elif now >= expires:
                code, message = "observation_expired", "As informações do trecho estão desatualizadas: observação vencida."
            else:
                code, message = "observation_valid", "Observação dentro do prazo de validade."
                result["is_valid"] = True
        except (ValueError, TypeError, OverflowError):
            code, message = "observation_date_invalid", "Data da observação inválida ou sem fuso horário."
    source = result["source"]
    if result["is_valid"] and (not isinstance(source, str) or not source.strip()):
        code, message = "observation_source_missing", "Origem da observação ausente."
        result["is_valid"] = False
    result.update(code=code, message=message)
    return result
