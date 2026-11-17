"""Contrato da conectividade, independente da presença na rede local."""
import math
from datetime import datetime, timedelta, timezone

MAX_AGE = 180
STATUSES = {'available', 'limited', 'unavailable', 'unknown'}


def validate_report(report):
    if report is None:
        return None  # Compatibilidade com agentes anteriores à versão 3.5.1.
    if not isinstance(report, dict) or not isinstance(report.get('status'), str) or report['status'] not in STATUSES:
        raise ValueError('Estado de internet inválido.')
    ping, http = report.get('ping'), report.get('http')
    if any(value is not None and type(value) is not bool for value in (ping, http)):
        raise ValueError('Resultados de conectividade inválidos.')
    expected = 'available' if http is True else 'limited' if ping is True else 'unavailable' if ping is False and http is False else 'unknown'
    if report['status'] != expected:
        raise ValueError('Estado de internet incompatível com os testes.')
    age = report.get('checked_ago_seconds')
    if age is None and ping is None and http is None:
        return None
    if isinstance(age, bool) or not isinstance(age, (int, float)) or not math.isfinite(age) or not 0 <= age <= 86400:
        raise ValueError('Idade do teste de internet inválida.')
    return {'status': expected, 'ping': ping, 'http': http,
            'checked_at': (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()}


def public_status(report, agent_online):
    result = {'status': 'unknown', 'checked_at': None, 'age_seconds': None, 'ping': None, 'http': None}
    if not isinstance(report, dict):
        return result
    try:
        checked = datetime.fromisoformat(report['checked_at'])
        age = (datetime.now(timezone.utc) - checked).total_seconds()
    except (KeyError, TypeError, ValueError):
        return result
    result.update(checked_at=checked.isoformat(), age_seconds=max(0, age),
                  ping=report.get('ping'), http=report.get('http'))
    if agent_online and 0 <= age <= MAX_AGE and report.get('status') in STATUSES:
        result['status'] = report['status']
    return result
