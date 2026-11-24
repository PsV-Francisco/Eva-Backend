import csv
from io import BytesIO

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone

from AdminApp.audit import registrar_historial


def normalize_csv_cell(value):
    normalized = '' if value is None else str(value)
    normalized = normalized.lstrip(' \t')
    if normalized.startswith(('=', '+', '-', '@')):
        normalized = "'" + normalized
    return normalized


def quarter_label(period=None, reference_date=None):
    if period is not None:
        if getattr(period, 'nombre', None):
            return period.nombre
        reference_date = getattr(period, 'fecha_inicio', None)
    dt = reference_date or timezone.localdate()
    quarter = ((dt.month - 1) // 3) + 1
    return f'T{quarter} {dt.year}'


def build_report_metadata_rows(
    request,
    *,
    title,
    period=None,
    delegation=None,
    filters=None,
):
    now_str = timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M:%S')
    actor_label = (
        request.user.get_full_name() or request.user.email
        if getattr(request, 'user', None) and request.user.is_authenticated
        else 'Sistema'
    )
    delegation_label = (
        delegation.nombre
        if hasattr(delegation, 'nombre')
        else (str(delegation) if delegation else 'Todas / Según alcance')
    )
    period_label = (
        period.nombre
        if hasattr(period, 'nombre')
        else (str(period) if period else 'Todos los períodos')
    )
    clean_filters = {
        k: v for k, v in (filters or {}).items()
        if v not in (None, '')
    }
    filters_label = (
        ', '.join(f'{k}: {v}' for k, v in clean_filters.items())
        if clean_filters else 'Sin filtros adicionales'
    )
    return [
        [title],
        ['Fecha y hora de generación', now_str],
        ['Trimestre / Período', f'{quarter_label(period)} ({period_label})'],
        ['Delegación', delegation_label],
        ['Generado por', actor_label],
        ['Filtros aplicados', filters_label],
        [],
    ]


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
    title=None,
    delegation=None,
    include_header=True,
):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')

    if include_header:
        header_rows = build_report_metadata_rows(
            request,
            title=title or entity,
            period=period,
            delegation=delegation,
            filters=filters,
        )
        for h_row in header_rows:
            writer.writerow(normalize_csv_cell(value) for value in h_row)

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


def excel_rows_response(
    request,
    *,
    filename,
    rows,
    entity,
    action='Exportar Excel',
    filters=None,
    row_count=None,
    period=None,
    title=None,
    delegation=None,
):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = 'Reporte'
    ws.views.sheetView[0].showGridLines = True

    # Paleta institucional
    navy_fill = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
    sub_fill = PatternFill(start_color='EEF3F8', end_color='EEF3F8', fill_type='solid')
    zebra_fill = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')
    thin_side = Side(border_style='thin', color='CBD5E1')
    cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    total_cols = max((len(r) for r in rows), default=4)
    total_cols = max(total_cols, 4)

    meta_rows = build_report_metadata_rows(
        request,
        title=title or entity,
        period=period,
        delegation=delegation,
        filters=filters,
    )

    # Fila 1: Banner de título combinado
    ws.append([normalize_csv_cell(meta_rows[0][0])])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    banner = ws['A1']
    banner.font = Font(name='Calibri', bold=True, size=14, color='FFFFFF')
    banner.fill = navy_fill
    banner.alignment = Alignment(horizontal='left', vertical='center', indent=1)
    ws.row_dimensions[1].height = 30

    # Filas 2..6: Ficha técnica de metadatos con estilo tarjeta
    for idx, m_row in enumerate(meta_rows[1:-1], start=2):
        ws.append([normalize_csv_cell(m_row[0]), normalize_csv_cell(m_row[1])])
        ws.merge_cells(start_row=idx, start_column=2, end_row=idx, end_column=total_cols)
        lbl = ws.cell(row=idx, column=1)
        val = ws.cell(row=idx, column=2)
        lbl.font = Font(name='Calibri', bold=True, size=10, color='1E3A5F')
        lbl.fill = sub_fill
        val.font = Font(name='Calibri', size=10, color='1E293B')
        ws.row_dimensions[idx].height = 20
        for c in range(1, total_cols + 1):
            ws.cell(row=idx, column=c).border = cell_border

    # Fila separadora en blanco
    sep_row = len(meta_rows)
    ws.append([])
    ws.row_dimensions[sep_row].height = 10

    # Tablas de datos (detecta automáticamente subtablas como "Resumen consolidado")
    start_data_row = sep_row + 1
    is_next_header = True
    data_stripe = 0

    for offset, raw_row in enumerate(rows):
        r_idx = start_data_row + offset
        cleaned = [normalize_csv_cell(v) for v in raw_row]

        if not cleaned or all(v == '' for v in cleaned):
            ws.append([])
            ws.row_dimensions[r_idx].height = 10
            is_next_header = True
            data_stripe = 0
            continue

        # Subtítulo de sección (ej: "Resumen consolidado")
        if len(cleaned) == 1:
            ws.append(cleaned)
            ws.merge_cells(start_row=r_idx, start_column=1, end_row=r_idx, end_column=total_cols)
            sec = ws.cell(row=r_idx, column=1)
            sec.font = Font(name='Calibri', bold=True, size=11, color='1E3A5F')
            sec.fill = sub_fill
            ws.row_dimensions[r_idx].height = 24
            is_next_header = True
            data_stripe = 0
            continue

        ws.append(cleaned)
        if is_next_header:
            ws.row_dimensions[r_idx].height = 24
            for c_idx in range(1, len(cleaned) + 1):
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.font = Font(name='Calibri', bold=True, size=10, color='FFFFFF')
                cell.fill = navy_fill
                cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                cell.border = cell_border
            is_next_header = False
        else:
            ws.row_dimensions[r_idx].height = 20
            data_stripe += 1
            for c_idx in range(1, len(cleaned) + 1):
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.font = Font(name='Calibri', size=10, color='0F172A')
                if data_stripe % 2 == 0:
                    cell.fill = zebra_fill
                cell.border = cell_border
                cell.alignment = Alignment(vertical='center')

    # Autoajuste generoso de columnas para evitar "#########"
    for col_idx in range(1, total_cols + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 14
        for row_idx in range(2, ws.max_row + 1):
            # Ignorar celdas combinadas en el cálculo de ancho
            if any(
                rng.min_row <= row_idx <= rng.max_row and rng.min_col <= col_idx <= rng.max_col
                for rng in ws.merged_cells.ranges
            ):
                continue
            val = ws.cell(row=row_idx, column=col_idx).value
            if val is not None:
                max_len = max(max_len, len(str(val)))
        ws.column_dimensions[col_letter].width = min(max_len + 5, 50)

    ws.freeze_panes = f'A{start_data_row + 1}'

    buf = BytesIO()
    wb.save(buf)

    with transaction.atomic():
        registrar_historial(
            actor=request.user,
            action=action,
            entity=entity,
            after={'filtros': filters or {}, 'filas': row_count},
            period=period,
        )

    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

def pdf_rows_response(
    request,
    *,
    filename,
    rows,
    entity,
    action,
    title=None,
    delegation=None,
    filters=None,
    row_count=None,
    period=None,
):
    from io import BytesIO
    from django.http import HttpResponse
    from django.utils import timezone
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=28,
        rightMargin=28,
        topMargin=28,
        bottomMargin=28,
    )
    styles = getSampleStyleSheet()
    elements = []

    report_title = title or 'Reporte SGR - Municipalidad de La Serena'
    elements.append(Paragraph(f'<b>{report_title}</b>', styles['Title']))
    meta = f'Generado el {timezone.localtime().strftime("%d/%m/%Y %H:%M")}'
    if delegation:
        meta += f' | Delegación: {delegation}'
    if period:
        meta += f' | Período: {period}'
    elements.append(Paragraph(meta, styles['Normal']))
    elements.append(Spacer(1, 12))

    table_data = [[str(cell) if cell is not None else '' for cell in row] for row in rows]
    if not table_data:
        table_data = [['Sin datos disponibles para los filtros seleccionados.']]

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9E1B1E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7F7F7')]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(table)
    doc.build(elements)

    registrar_historial(
        actor=request.user,
        action=action,
        entity=entity,
        before=None,
        after={
            'formato': 'PDF',
            'archivo': filename,
            'filtros': filters or {},
            'filas': row_count if row_count is not None else max(0, len(rows) - 1),
        },
        period=period,
    )

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
