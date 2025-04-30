from flask import send_file
from io import BytesIO
import pandas as pd
import pytz
from datetime import datetime

# Configuración de zona horaria
madrid_tz = pytz.timezone('Europe/Madrid')

def exportar_excel(registros, fecha_inicio, fecha_fin):
    """Genera un archivo Excel con los registros proporcionados"""
    # Preparar datos para el DataFrame
    registros_agrupados = {}
    
    for registro in registros:
        fecha = registro.fecha_madrid.strftime('%d/%m/%Y')
        empleado = f"{registro.empleado.apellidos}, {registro.empleado.nombre}"
        key = (fecha, empleado)
        
        if key not in registros_agrupados:
            registros_agrupados[key] = {
                'Fecha': fecha,
                'Empleado': empleado,
                'Entrada': '',
                'Salida': ''
            }
        
        if registro.tipo == 'entrada':
            registros_agrupados[key]['Entrada'] = registro.fecha_madrid.strftime('%H:%M')
        else:
            registros_agrupados[key]['Salida'] = registro.fecha_madrid.strftime('%H:%M')
    
    # Convertir el diccionario a lista y ordenar por fecha
    data = sorted(registros_agrupados.values(), 
                 key=lambda x: datetime.strptime(x['Fecha'], '%d/%m/%Y'), 
                 reverse=True)
    
    # Crear DataFrame
    df = pd.DataFrame(data)
    
    # Crear archivo Excel en memoria
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Registros', index=False)
        
        # Obtener el objeto workbook y worksheet
        workbook = writer.book
        worksheet = writer.sheets['Registros']
        
        # Formato para el encabezado
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#D7E4BC',
            'border': 1
        })
        
        # Aplicar formato al encabezado
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, 15)  # Ancho de columna
    
    output.seek(0)
    
    # Nombre del archivo
    nombre_archivo = f'registros_{fecha_inicio}_{fecha_fin}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ) 