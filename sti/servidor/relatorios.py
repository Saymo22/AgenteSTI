
"""
STI COMMAND CENTER
MÓDULO DE RELATÓRIOS V1

Usa a tabela audit_events existente.
Não altera o banco de dados.
"""

import csv
import io
from datetime import datetime, timedelta

from flask import (
    request,
    jsonify,
    Response,
    render_template_string,
)


PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>STI | Relatórios</title>

<style>
:root {
    --bg: #07111f;
    --panel: #101f33;
    --panel2: #14263e;
    --border: #263c55;
    --text: #edf5ff;
    --muted: #91a6c3;
    --cyan: #3be4ff;
    --green: #2be39a;
    --red: #ff6178;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: Inter, "Segoe UI", Arial, sans-serif;
}

.container {
    width: min(1400px, 94%);
    margin: 35px auto;
}

.topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
    margin-bottom: 32px;
}

.logo {
    font-size: 15px;
    font-weight: 900;
    letter-spacing: 2px;
    color: var(--cyan);
}

h1 {
    margin: 10px 0;
    font-size: clamp(25px, 4vw, 34px);
}

.subtitle {
    color: var(--muted);
    font-size: 14px;
}

.back {
    color: var(--cyan);
    text-decoration: none;
    padding: 12px 16px;
    border: 1px solid var(--border);
    border-radius: 12px;
}

.back:hover {
    background: var(--panel);
}

.card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 22px;
    margin-bottom: 20px;
}

.filters {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 15px;
}

.field label {
    display: block;
    margin-bottom: 9px;
    font-size: 12px;
    color: var(--muted);
}

.field input,
.field select {
    width: 100%;
    height: 44px;
    background: #091726;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0 12px;
    color: var(--text);
    font: inherit;
    color-scheme: dark;
}

.actions {
    display: flex;
    gap: 12px;
    margin-top: 20px;
    flex-wrap: wrap;
}

button,
.export {
    min-height: 44px;
    padding: 12px 18px;
    border: 0;
    border-radius: 11px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 800;
    text-decoration: none;
}

button {
    background: var(--cyan);
    color: var(--bg);
}

.export {
    background: rgba(43, 227, 154, .12);
    border: 1px solid rgba(43, 227, 154, .3);
    color: var(--green);
}

.stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}

.stat {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 22px;
}

.stat-label {
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 14px;
}

.stat-value {
    font-size: 32px;
    font-weight: 850;
}

.stat-value.red {
    color: var(--red);
}

.stat-value.green {
    color: var(--green);
}

.table-wrap {
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
    text-align: left;
    min-width: 850px;
}

th {
    color: var(--muted);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .8px;
    padding: 16px 12px;
}

td {
    padding: 15px 12px;
    font-size: 13px;
    border-top: 1px solid var(--border);
}

.status {
    display: inline-block;
    padding: 7px 10px;
    border-radius: 999px;
    background: #26364e;
    font-weight: 700;
    font-size: 11px;
}

.status.online {
    background: rgba(43, 227, 154, .13);
    color: var(--green);
}

.status.offline {
    background: rgba(255, 97, 120, .12);
    color: var(--red);
}

.empty {
    padding: 35px 10px;
    color: var(--muted);
    text-align: center;
}

.footer {
    margin: 25px 0;
    text-align: center;
    font-size: 12px;
    color: var(--muted);
}

@media (max-width: 900px) {
    .filters {
        grid-template-columns: repeat(2, 1fr);
    }
    .stats {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 540px) {
    .filters,
    .stats {
        grid-template-columns: 1fr;
    }
    .topbar {
        align-items: flex-start;
        flex-direction: column;
    }
}
</style>
</head>

<body>

<div class="container">

    <header class="topbar">
        <div>
            <div class="logo">STI COMMAND CENTER</div>
            <h1>Relatórios da Rede</h1>
            <div class="subtitle">
                Histórico de ocorrências e auditoria
            </div>
        </div>

        <a href="/" class="back">
            Voltar ao painel
        </a>
    </header>

    <section class="card">

        <form method="GET" action="/relatorios">

            <div class="filters">

                <div class="field">
                    <label for="start">
                        Data inicial
                    </label>
                    <input
                        type="date"
                        id="start"
                        name="start"
                        value="{{ filters.start }}"
                    >
                </div>

                <div class="field">
                    <label for="end">
                        Data final
                    </label>
                    <input
                        type="date"
                        id="end"
                        name="end"
                        value="{{ filters.end }}"
                    >
                </div>

                <div class="field">
                    <label for="ip">
                        IP do dispositivo
                    </label>
                    <input
                        type="text"
                        id="ip"
                        name="ip"
                        placeholder="Ex.: 10.2.116.121"
                        value="{{ filters.ip }}"
                    >
                </div>

                <div class="field">
                    <label for="category">
                        Categoria
                    </label>

                    <select
                        id="category"
                        name="category"
                    >
                        {% for value, label in categories %}
                        <option
                            value="{{ value }}"
                            {% if filters.category == value %}
                            selected
                            {% endif %}
                        >
                            {{ label }}
                        </option>
                        {% endfor %}
                    </select>
                </div>

            </div>

            <div class="actions">

                <button type="submit">
                    Aplicar filtros
                </button>

                <a
                    class="export"
                    href="/api/report/events.csv?{{ query_string }}"
                >
                    Exportar CSV
                </a>

            </div>

        </form>

    </section>

    <section class="stats">

        <div class="stat">
            <div class="stat-label">
                Total de eventos
            </div>
            <div class="stat-value">
                {{ stats.total }}
            </div>
        </div>

        <div class="stat">
            <div class="stat-label">
                Quedas registradas
            </div>
            <div class="stat-value red">
                {{ stats.offline }}
            </div>
        </div>

        <div class="stat">
            <div class="stat-label">
                Recuperações
            </div>
            <div class="stat-value green">
                {{ stats.online }}
            </div>
        </div>

        <div class="stat">
            <div class="stat-label">
                Outros eventos
            </div>
            <div class="stat-value">
                {{ stats.other }}
            </div>
        </div>

    </section>

    <section class="card">

        <h2>Histórico de ocorrências</h2>

        <p class="subtitle">
            Exibindo até 500 registros.
            Os indicadores consideram todos os
            eventos que correspondem aos filtros.
        </p>

        <div class="table-wrap">

            <table>

                <thead>
                    <tr>
                        <th>Data e hora</th>
                        <th>Categoria</th>
                        <th>Dispositivo</th>
                        <th>IP</th>
                        <th>Status</th>
                        <th>Descrição</th>
                    </tr>
                </thead>

                <tbody>

                    {% for event in events %}

                    <tr>

                        <td>{{ event.timestamp }}</td>

                        <td>{{ event.category }}</td>

                        <td>{{ event.name or "—" }}</td>

                        <td>{{ event.ip or "—" }}</td>

                        <td>
                            <span class="status
                                {% if event.status == 'online' %}
                                    online
                                {% elif event.status == 'offline' %}
                                    offline
                                {% endif %}
                            ">
                                {{ event.status }}
                            </span>
                        </td>

                        <td>{{ event.description }}</td>

                    </tr>

                    {% else %}

                    <tr>
                        <td
                            colspan="6"
                            class="empty"
                        >
                            Nenhum evento encontrado
                            para esses filtros.
                        </td>
                    </tr>

                    {% endfor %}

                </tbody>

            </table>

        </div>

    </section>

    <div class="footer">
        STI Command Center
        · Relatórios baseados nos registros SQLite
    </div>

</div>

</body>
</html>
"""


CATEGORIES = [
    ("", "Todas"),
    ("inventario", "Cadastro de máquinas"),
    ("dispositivo", "Dispositivos"),
    ("comando", "Comandos"),
    ("scanner", "Scanner"),
    ("seguranca", "Segurança"),
]


def parse_filters():

    filters = {
        "start": request.args.get("start", "").strip(),
        "end": request.args.get("end", "").strip(),
        "ip": request.args.get("ip", "").strip(),
        "category": request.args.get(
            "category", ""
        ).strip(),
    }

    for key in ("start", "end"):

        if filters[key]:
            datetime.strptime(
                filters[key],
                "%Y-%m-%d"
            )

    if (
        filters["start"]
        and filters["end"]
        and filters["start"] > filters["end"]
    ):
        raise ValueError(
            "Data inicial maior que a final."
        )

    allowed_categories = {
        value for value, _ in CATEGORIES
    }

    if filters["category"] not in allowed_categories:
        raise ValueError(
            "Categoria inválida."
        )

    if len(filters["ip"]) > 45:
        raise ValueError(
            "Filtro de IP muito longo."
        )

    return filters


def build_where(filters):

    conditions = []
    params = []

    if filters["start"]:
        conditions.append(
            "timestamp >= ?"
        )
        params.append(
            filters["start"]
        )

    if filters["end"]:
        conditions.append(
            "timestamp < ?"
        )
        params.append(
            (datetime.strptime(filters["end"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        )

    if filters["ip"]:
        conditions.append(
            "ip = ?"
        )
        params.append(
            filters["ip"]
        )

    if filters["category"]:
        conditions.append(
            "category = ?"
        )
        params.append(
            filters["category"]
        )

    where = (
        " WHERE " + " AND ".join(conditions)
        if conditions
        else ""
    )

    return where, params


def safe_csv(value):
    """
    Evita interpretação de campos como fórmulas
    ao abrir o CSV em uma planilha.
    """
    value = "" if value is None else str(value)

    if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + value

    return value


def registrar_relatorios(
    app,
    require_admin,
    db_connect
):

    @app.route(
        "/relatorios",
        methods=["GET"]
    )
    @require_admin
    def sti_relatorios():

        try:
            filters = parse_filters()
        except ValueError as error:
            return jsonify({
                "ok": False,
                "error": str(error)
            }), 400

        where, params = build_where(
            filters
        )

        with db_connect() as conn:

            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    category,
                    name,
                    ip,
                    status,
                    description
                FROM audit_events
                """
                + where
                + """
                ORDER BY id DESC
                LIMIT 500
                """,
                params
            ).fetchall()

            counts = conn.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(SUM(
                        CASE
                            WHEN category = 'dispositivo'
                             AND status = 'offline'
                            THEN 1 ELSE 0
                        END
                    ), 0),
                    COALESCE(SUM(
                        CASE
                            WHEN category = 'dispositivo'
                             AND status = 'online'
                            THEN 1 ELSE 0
                        END
                    ), 0)
                FROM audit_events
                """
                + where,
                params
            ).fetchone()

        columns = [
            "timestamp",
            "category",
            "name",
            "ip",
            "status",
            "description"
        ]

        events = [
            dict(zip(columns, row))
            for row in rows
        ]

        total, offline, online = counts

        from urllib.parse import urlencode

        return render_template_string(
            PAGE,
            filters=filters,
            categories=CATEGORIES,
            events=events,
            query_string=urlencode(filters),
            stats={
                "total": total,
                "offline": offline,
                "online": online,
                "other": total - offline - online
            }
        )

    @app.route(
        "/api/report/events.csv",
        methods=["GET"]
    )
    @require_admin
    def sti_export_events():

        try:
            filters = parse_filters()
        except ValueError as error:
            return jsonify({
                "ok": False,
                "error": str(error)
            }), 400

        where, params = build_where(
            filters
        )

        with db_connect() as conn:

            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    category,
                    name,
                    ip,
                    status,
                    description
                FROM audit_events
                """
                + where
                + """
                ORDER BY id DESC
                LIMIT 10000
                """,
                params
            ).fetchall()

        output = io.StringIO()

        writer = csv.writer(
            output,
            delimiter=";"
        )

        writer.writerow([
            "Data e hora",
            "Categoria",
            "Dispositivo",
            "IP",
            "Status",
            "Descrição"
        ])

        for row in rows:
            writer.writerow([
                safe_csv(value)
                for value in row
            ])

        filename = (
            "STI_Logs_"
            + datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
            + ".csv"
        )

        content = (
            "\ufeff"
            + output.getvalue()
        )

        return Response(
            content,
            mimetype=(
                "text/csv; charset=utf-8"
            ),
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{filename}"'
                ),
                "Cache-Control": "no-store"
            }
        )
