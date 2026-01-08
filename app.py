import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="SPAN Naval", page_icon="⚓", layout="wide")

# --- FUNCIONES AUXILIARES (Para evitar errores de formato) ---
def limpiar_fecha(fecha_str):
    """Intenta entender la fecha sea como sea que venga del Excel"""
    try:
        # Si ya es fecha, devolverla
        if isinstance(fecha_str, (datetime, pd.Timestamp)):
            return fecha_str
        # Si es texto, intentar convertir
        return pd.to_datetime(fecha_str, dayfirst=True) # Asume DD/MM/AAAA si es ambiguo
    except:
        return None

# --- MÓDULO 1: CONEXIÓN ---
def cargar_datos():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("SPAN_BD_2026")
        
        # Leemos las pestañas y limpiamos nombres de columnas (quitamos espacios extra)
        db = {}
        tablas_requeridas = ["CONFIGURACION", "CURSOS", "MATERIAS", "INTERRUPCIONES", "HISTORIAL_CAMBIOS"]
        
        for tabla in tablas_requeridas:
            try:
                data = sheet.worksheet(tabla).get_all_records()
                df = pd.DataFrame(data)
                # Limpieza de columnas: " ID_Curso " -> "ID_Curso"
                df.columns = df.columns.str.strip() 
                db[tabla.lower()] = df
            except gspread.exceptions.WorksheetNotFound:
                st.error(f"❌ Error Crítico: No encuentro la pestaña '{tabla}' en el Excel.")
                st.stop()
        
        return db, sheet
    except Exception as e:
        st.error(f"❌ Error de Conexión con Google: {str(e)}")
        st.stop()

def registrar_auditoria(sheet, usuario, accion, id_evento, justificacion):
    try:
        ws_historial = sheet.worksheet("HISTORIAL_CAMBIOS")
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        nueva_fila = [ahora, usuario, accion, id_evento, justificacion]
        ws_historial.append_row(nueva_fila)
    except Exception as e:
        st.warning(f"No se pudo guardar auditoría: {e}")

# --- MÓDULO 2: CEREBRO DE CÁLCULO ---
def calcular_cronograma(db, curso_seleccionado):
    # 1. Obtener datos del curso
    try:
        df_cursos = db["cursos"]
        # Filtrar
        info_curso = df_cursos[df_cursos["ID_Curso"] == curso_seleccionado].iloc[0]
        
        # Procesar Fechas con la función inteligente
        fecha_inicio = limpiar_fecha(info_curso["Inicio_Clases_Real"])
        fecha_fin = limpiar_fecha(info_curso["Fin_Clases_Real"])
        
        if pd.isna(fecha_inicio) or pd.isna(fecha_fin):
            st.error(f"Error en fechas del curso {curso_seleccionado}. Revisa el formato en el Excel.")
            return None
            
    except IndexError:
        st.error(f"No encontré información para el curso: {curso_seleccionado}")
        return None

    # 2. Filtrar Materias
    materias = db["materias"][db["materias"]["Curso"] == curso_seleccionado].copy()
    
    # 3. Filtrar Interrupciones
    interrupciones = db["interrupciones"]
    mask = (interrupciones["Estado"] == "ACTIVO") & \
           ((interrupciones["Alcance"] == "GLOBAL") | (interrupciones["Afectados"] == curso_seleccionado))
    eventos_curso = interrupciones[mask]

    # 4. Simulación
    dias_totales = (fecha_fin - fecha_inicio).days + 1
    dias_perdidos = 0
    horas_disponibles_reales = 0
    log_diario = []

    fecha_actual = fecha_inicio
    while fecha_actual <= fecha_fin:
        es_fin_semana = fecha_actual.weekday() >= 5
        fecha_str = fecha_actual.strftime("%Y-%m-%d")
        
        evento_hoy = None
        # Revisar si hay evento hoy
        for _, evento in eventos_curso.iterrows():
            fi = limpiar_fecha(evento["Fecha_Inicio"])
            ff = limpiar_fecha(evento["Fecha_Fin"])
            if fi and ff and (fi <= fecha_actual <= ff):
                evento_hoy = evento["Nombre_Evento"]
                break
        
        estado_dia = "CLASE"
        if es_fin_semana:
            estado_dia = "FIN DE SEMANA"
        elif evento_hoy:
            estado_dia = f"INTERRUPCIÓN: {evento_hoy}"
            dias_perdidos += 1
        else:
            horas_disponibles_reales += 6 
        
        log_diario.append({"Fecha": fecha_str, "Estado": estado_dia})
        fecha_actual += timedelta(days=1)

    # 5. Resultados
    total_horas_necesarias = materias["Horas_Totales"].sum() if not materias.empty else 0
    
    return {
        "dias_perdidos": dias_perdidos,
        "horas_reales": horas_disponibles_reales,
        "cobertura": min(100, int((horas_disponibles_reales / total_horas_necesarias) * 100)) if total_horas_necesarias > 0 else 100,
        "detalle": log_diario
    }

# --- INTERFAZ PRINCIPAL ---
st.title("⚓ Sistema de Planificación Académica Naval (SPAN)")

# Carga inicial con manejo de errores
db, sheet_obj = cargar_datos()

if db:
    st.sidebar.header("👮‍♂️ Panel de Control")
    
    # Verificar que existan cursos
    if db["cursos"].empty:
        st.error("La pestaña CURSOS está vacía o no tiene datos.")
    else:
        lista_cursos = db["cursos"]["ID_Curso"].dropna().unique()
        curso_actual = st.sidebar.selectbox("Seleccione Curso:", lista_cursos)
        
        tab1, tab2, tab3 = st.tabs(["📊 Situación", "📅 Gestión", "📝 Auditoría"])
        
        with tab1:
            st.header(f"Análisis: {curso_actual}")
            if st.button("🔄 Actualizar"):
                st.rerun()
            
            res = calcular_cronograma(db, curso_actual)
            
            if res:
                c1, c2, c3 = st.columns(3)
                c1.metric("Cobertura", f"{res['cobertura']}%")
                c2.metric("Días Perdidos", res['dias_perdidos'])
                c3.metric("Horas Reales", res['horas_reales'])
                
                with st.expander("Ver Calendario Detallado"):
                    st.dataframe(pd.DataFrame(res["detalle"]))

        with tab2:
            st.header("Registrar Interrupción")
            with st.form("add_event"):
                nombre = st.text_input("Nombre Evento")
                col_dates = st.columns(2)
                fi = col_dates[0].date_input("Inicio")
                ff = col_dates[1].date_input("Fin")
                alcance = st.radio("Alcance", ["GLOBAL", "ESPECIFICO"])
                justif = st.text_area("Justificación")
                user = st.text_input("Usuario")
                
                if st.form_submit_button("Guardar"):
                    # Guardado simple para prueba
                    ws = sheet_obj.worksheet("INTERRUPCIONES")
                    afectados = curso_actual if alcance == "ESPECIFICO" else ""
                    row = [f"EVT-{int(time.time())}", nombre, str(fi), str(ff), "Militar", alcance, afectados, "ACTIVO", justif]
                    ws.append_row(row)
                    registrar_auditoria(sheet_obj, user, "CREACION", "N/A", f"Evento: {nombre}")
                    st.success("Guardado")
                    time.sleep(1)
                    st.rerun()

        with tab3:
            st.dataframe(db["historial"])
