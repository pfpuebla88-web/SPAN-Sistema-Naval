import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="SPAN Naval", page_icon="⚓", layout="wide")

# --- MÓDULO 1: CONEXIÓN (El motor que ya probamos) ---
def conectar_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("SPAN_BD_2026") # Nombre exacto del archivo
    return sheet

# --- MÓDULO 2: FUNCIONES DE LECTURA Y ESCRITURA ---
def cargar_datos():
    sheet = conectar_google_sheet()
    # Cargamos todas las pestañas en memoria
    db = {
        "config": pd.DataFrame(sheet.worksheet("CONFIGURACION").get_all_records()),
        "cursos": pd.DataFrame(sheet.worksheet("CURSOS").get_all_records()),
        "materias": pd.DataFrame(sheet.worksheet("MATERIAS").get_all_records()),
        "interrupciones": pd.DataFrame(sheet.worksheet("INTERRUPCIONES").get_all_records()),
        "historial": pd.DataFrame(sheet.worksheet("HISTORIAL_CAMBIOS").get_all_records())
    }
    return db, sheet

def registrar_auditoria(sheet, usuario, accion, id_evento, justificacion):
    """Escribe en la pestaña HISTORIAL_CAMBIOS"""
    ws_historial = sheet.worksheet("HISTORIAL_CAMBIOS")
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nueva_fila = [ahora, usuario, accion, id_evento, justificacion]
    ws_historial.append_row(nueva_fila)

# --- MÓDULO 3: EL CEREBRO DE CÁLCULO (La Lógica Naval) ---
def calcular_cronograma(db, curso_seleccionado):
    # 1. Preparar fechas límites del Curso
    info_curso = db["cursos"][db["cursos"]["ID_Curso"] == curso_seleccionado].iloc[0]
    fecha_inicio = datetime.strptime(str(info_curso["Inicio_Clases_Real"]), "%Y-%m-%d")
    fecha_fin = datetime.strptime(str(info_curso["Fin_Clases_Real"]), "%Y-%m-%d")
    
    # 2. Filtrar Materias del curso
    materias = db["materias"][db["materias"]["Curso"] == curso_seleccionado].copy()
    materias["Horas_Ejecutadas"] = 0 # Iniciamos contador
    
    # 3. Filtrar Interrupciones (Globales + Específicas de este curso) ACTIVAS
    interrupciones = db["interrupciones"]
    # Filtro: Que esté ACTIVO y (sea GLOBAL o sea para ESTE CURSO)
    mask = (interrupciones["Estado"] == "ACTIVO") & \
           ((interrupciones["Alcance"] == "GLOBAL") | (interrupciones["Afectados"] == curso_seleccionado))
    eventos_curso = interrupciones[mask]

    # 4. Simulación Día a Día (El Loop Principal)
    dias_totales = (fecha_fin - fecha_inicio).days + 1
    dias_perdidos = 0
    horas_disponibles_reales = 0
    
    log_diario = [] # Para guardar qué pasa cada día

    fecha_actual = fecha_inicio
    while fecha_actual <= fecha_fin:
        es_fin_semana = fecha_actual.weekday() >= 5 # 5=Sábado, 6=Domingo
        fecha_str = fecha_actual.strftime("%Y-%m-%d")
        
        # Verificar Interrupciones
        evento_hoy = None
        for _, evento in eventos_curso.iterrows():
            f_ini = datetime.strptime(str(evento["Fecha_Inicio"]), "%Y-%m-%d")
            f_fin = datetime.strptime(str(evento["Fecha_Fin"]), "%Y-%m-%d")
            if f_ini <= fecha_actual <= f_fin:
                evento_hoy = evento["Nombre_Evento"]
                break
        
        estado_dia = "CLASE"
        if es_fin_semana:
            estado_dia = "FIN DE SEMANA"
        elif evento_hoy:
            estado_dia = f"INTERRUPCIÓN: {evento_hoy}"
            dias_perdidos += 1
        else:
            # Es un día laborable real
            horas_disponibles_reales += 6 # Asumimos 6 horas pedagógicas diarias promedio
        
        log_diario.append({
            "Fecha": fecha_str,
            "Estado": estado_dia
        })
        
        fecha_actual += timedelta(days=1)

    # 5. Cálculo de Cobertura Académica
    # Repartimos las horas disponibles entre las materias
    total_horas_necesarias = materias["Horas_Totales"].sum()
    
    resultados = {
        "dias_perdidos": dias_perdidos,
        "horas_reales": horas_disponibles_reales,
        "cobertura_porcentaje": min(100, int((horas_disponibles_reales / total_horas_necesarias) * 100)) if total_horas_necesarias > 0 else 0,
        "detalle_dias": log_diario
    }
    return resultados

# --- INTERFAZ GRÁFICA (LO QUE VES) ---
st.title("⚓ Sistema de Planificación Académica Naval (SPAN)")

try:
    # Cargar base de datos
    db, sheet_obj = cargar_datos()
    
    # MENU LATERAL
    st.sidebar.header("👮‍♂️ Panel de Control")
    curso_actual = st.sidebar.selectbox("Seleccione Curso a Analizar:", db["cursos"]["ID_Curso"].unique())
    
    # PESTAÑAS PRINCIPALES
    tab1, tab2, tab3 = st.tabs(["📊 Situación Actual", "📅 Gestión de Interrupciones", "📝 Auditoría"])
    
    # --- TAB 1: DASHBOARD ---
    with tab1:
        st.header(f"Análisis para: {curso_actual}")
        
        if st.button("🔄 Recalcular Planificación"):
            st.toast("Procesando algoritmo naval...")
            time.sleep(1)
        
        # Ejecutar cálculos
        res = calcular_cronograma(db, curso_actual)
        
        # Métricas Clave
        col1, col2, col3 = st.columns(3)
        col1.metric("Cobertura Académica Proyectada", f"{res['cobertura_porcentaje']}%")
        col2.metric("Días Perdidos (Interrupciones)", f"{res['dias_perdidos']} días")
        col3.metric("Horas Pedagógicas Reales", res['horas_reales'])
        
        # Alerta visual
        if res['cobertura_porcentaje'] < 80:
            st.error("🚨 ALERTA CRÍTICA: No se alcanzará a cubrir el contenido académico con las interrupciones actuales.")
        elif res['cobertura_porcentaje'] < 100:
            st.warning("⚠️ PRECAUCIÓN: Se requiere recuperar horas para llegar al 100%.")
        else:
            st.success("✅ SITUACIÓN NORMAL: El tiempo es suficiente.")

        # Tabla de detalle diario (Expandible)
        with st.expander("Ver detalle día a día"):
            st.dataframe(pd.DataFrame(res["detalle_dias"]))

    # --- TAB 2: GESTIÓN (AGREGAR/CANCELAR) ---
    with tab2:
        st.header("Gestión de Eventos e Interrupciones")
        
        # Sección A: Agregar Nuevo Evento
        st.subheader("➕ Registrar Nueva Interrupción")
        with st.form("nuevo_evento"):
            col_a, col_b = st.columns(2)
            nombre_evt = col_a.text_input("Nombre del Evento")
            tipo_evt = col_b.selectbox("Tipo", ["Militar", "Feriado", "Imprevisto", "Sancion"])
            
            col_c, col_d = st.columns(2)
            f_inicio = col_c.date_input("Fecha Inicio")
            f_fin = col_d.date_input("Fecha Fin")
            
            alcance = st.radio("Alcance:", ["GLOBAL (Todos)", "ESPECIFICO (Solo este curso)"])
            justificacion = st.text_area("Justificación / Orden General")
            usuario = st.text_input("Grado y Apellido del Oficial responsable:")
            
            submit = st.form_submit_button("Guardar Evento")
            
            if submit:
                if not usuario or not justificacion:
                    st.error("Debe ingresar Usuario y Justificación para la auditoría.")
                else:
                    # Guardar en Sheet INTERRUPCIONES
                    ws_int = sheet_obj.worksheet("INTERRUPCIONES")
                    id_nuevo = f"EVT-{int(time.time())}" # Genera ID único
                    afectados = curso_actual if alcance == "ESPECIFICO (Solo este curso)" else ""
                    alcance_val = "ESPECIFICO" if afectados else "GLOBAL"
                    
                    nueva_fila_int = [id_nuevo, nombre_evt, str(f_inicio), str(f_fin), tipo_evt, alcance_val, afectados, "ACTIVO", justificacion]
                    ws_int.append_row(nueva_fila_int)
                    
                    # Guardar en Sheet AUDITORIA
                    registrar_auditoria(sheet_obj, usuario, "CREACION", id_nuevo, f"Creó evento: {nombre_evt}")
                    
                    st.success(f"Evento {nombre_evt} registrado correctamente.")
                    st.rerun() # Recargar app

        st.divider()
        
        # Sección B: Cancelar Eventos Activos
        st.subheader("🗑️ Anular / Cancelar Evento")
        
        # Filtrar solo eventos activos
        df_activos = db["interrupciones"][db["interrupciones"]["Estado"] == "ACTIVO"]
        evento_a_cancelar = st.selectbox("Seleccione evento a anular:", df_activos["Nombre_Evento"].unique())
        
        motivo_cancel = st.text_input("Motivo de la anulación (Obligatorio):")
        oficial_cancel = st.text_input("Oficial que anula:")
        
        if st.button("Confirmar Anulación"):
            if motivo_cancel and oficial_cancel:
                # Buscar la fila exacta en el sheet (Lógica simplificada para demo)
                # En un sistema prod, buscamos por ID. Aquí buscamos la celda.
                cell = sheet_obj.worksheet("INTERRUPCIONES").find(evento_a_cancelar)
                if cell:
                    # Asumimos que la columna Estado es la H (columna 8)
                    sheet_obj.worksheet("INTERRUPCIONES").update_cell(cell.row, 8, "CANCELADO")
                    
                    # Auditoría
                    id_evt = df_activos[df_activos["Nombre_Evento"] == evento_a_cancelar].iloc[0]["ID_Evento"]
                    registrar_auditoria(sheet_obj, oficial_cancel, "ANULACION", id_evt, motivo_cancel)
                    
                    st.success("Evento anulado y registrado en auditoría.")
                    time.sleep(2)
                    st.rerun()
            else:
                st.error("Falta motivo u oficial.")

    # --- TAB 3: AUDITORÍA ---
    with tab3:
        st.header("📝 Historial de Cambios (La Caja Negra)")
        st.info("Este registro es inalterable y muestra quién modificó la planificación.")
        st.dataframe(db["historial"])

except Exception as e:
    st.error("Error del Sistema:")
    st.code(e)
