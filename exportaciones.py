from flask import send_file
from datetime import datetime
import pytz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from io import BytesIO
import os
from models import Registro, Empleado

# Configuración de zona horaria
madrid_tz = pytz.timezone('Europe/Madrid')

def exportar_pdf(registros, fecha_inicio, fecha_fin):
    """Genera un PDF con los registros proporcionados"""
    # Crear el PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []
    
    # Estilos
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30
    )
    
    # Añadir logo
    logo_path = os.path.join('static', 'logo.png')
    if os.path.exists(logo_path):
        img = Image(logo_path)
        img.drawHeight = 1.5*inch
        img.drawWidth = 3.5*inch
        elements.append(img)
    
    # Título
    elements.append(Paragraph("Registro de Horarios", title_style))
    elements.append(Spacer(1, 20))
    
    # Información del período
    inicio = madrid_tz.localize(datetime.strptime(fecha_inicio + ' 00:00:00', '%Y-%m-%d %H:%M:%S'))
    fin = madrid_tz.localize(datetime.strptime(fecha_fin + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    periodo_text = f"Período: {inicio.strftime('%d/%m/%Y')} - {fin.strftime('%d/%m/%Y')}"
    elements.append(Paragraph(periodo_text, styles["Normal"]))
    elements.append(Spacer(1, 20))
    
    # Preparar datos para la tabla
    data = [['Fecha', 'Empleado', 'Entrada', 'Salida']]
    
    # Diccionario para agrupar registros por fecha y empleado
    registros_agrupados = {}
    
    for registro in registros:
        fecha = registro.fecha_madrid.strftime('%d/%m/%Y')
        empleado = f"{registro.empleado.apellidos}, {registro.empleado.nombre}"
        key = (fecha, empleado)
        
        if key not in registros_agrupados:
            registros_agrupados[key] = {
                'fecha': fecha,
                'empleado': empleado,
                'entrada': '',
                'salida': ''
            }
        
        if registro.tipo == 'entrada':
            registros_agrupados[key]['entrada'] = registro.fecha_madrid.strftime('%H:%M')
        else:
            registros_agrupados[key]['salida'] = registro.fecha_madrid.strftime('%H:%M')
    
    # Convertir el diccionario a lista y ordenar por fecha
    for registro in sorted(registros_agrupados.values(), key=lambda x: datetime.strptime(x['fecha'], '%d/%m/%Y'), reverse=True):
        data.append([
            registro['fecha'],
            registro['empleado'],
            registro['entrada'],
            registro['salida']
        ])
    
    # Crear tabla
    table = Table(data, colWidths=[2*cm, 6*cm, 3*cm, 3*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 50))
    
    # Espacio para firma y sello
    firma_text = "Firma y Sello"
    elements.append(Paragraph(firma_text, styles["Normal"]))
    
    # Generar PDF
    doc.build(elements)
    buffer.seek(0)
    
    # Nombre del archivo
    nombre_archivo = f'registros_{fecha_inicio}_{fecha_fin}.pdf'
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype='application/pdf'
    ) 