import csv

from django.db import transaction
from django.http import HttpResponse

from AdminApp.audit import registrar_historial


def normalize_csv_cell(value):
    normalized = '' if value is None else str(value)
    normalized = normalized.lstrip(' \t')
    if normalized.startswith(('=', '+', '-', '@')):
        normalized = "'" + normalized
    return normalized


def csv_response(
    request,
    *,
    filename,
    rows,
    entity,
    action='Exportar CSV',
    filters=None,
    row_count=None,
    period=None,
):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response.write('\ufeff')
    writer = csv.writer(response)
    for row in rows:
        writer.writerow(normalize_csv_cell(value) for value in row)

    with transaction.atomic():
        registrar_historial(
            actor=request.user,
            action=action,
            entity=entity,
            after={
                'filtros': filters or {},
                'filas': row_count,
            },
            period=period,
        )

    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
