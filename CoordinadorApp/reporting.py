def consolidated_report_csv_rows(period, rows, summaries):
    csv_rows = [
        ['Informe consolidado'],
        ['Período', period.nombre if period else ''],
        [],
        [
            'Detalle',
            'Delegación',
            'Cargo',
            'Funcionario',
            'Avance real',
            'Avance esperado',
            'Clasificación',
            'Ítems',
        ],
    ]
    for row in rows:
        summary = row['summary']
        csv_rows.append([
            '',
            row['delegacion'],
            row['cargo'],
            row['usuario'].get_full_name() or row['usuario'].email,
            summary['avance_real'],
            summary['avance_esperado'],
            row['clasificacion'] or 'Sin ítems',
            len(summary['items']),
        ])
    csv_rows.extend([
        [],
        ['Resumen consolidado'],
        [
            'Delegación',
            'Cargo',
            'Promedio avance real',
            'Sobre umbral',
            'Bajo umbral',
            'Sin ítems',
        ],
    ])
    for summary in summaries:
        csv_rows.append([
            summary['delegacion'],
            summary['cargo'],
            summary['promedio_avance_real'],
            summary['sobre'],
            summary['bajo'],
            summary['sin_items'],
        ])
    return csv_rows
