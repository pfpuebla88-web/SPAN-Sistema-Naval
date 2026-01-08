import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="SPAN Naval", page_icon="⚓", layout="wide")

# --- FUNCIONES AUXILIARES ---
def limpiar_fecha(fecha_str):
    """Intenta entender la fecha sea como sea que venga del Excel"""
    try:
        if isinstance(fecha_str, (datetime, pd.Timestamp)):
            return fecha_str
        return pd.to_datetime(fecha_str, dayfirst=True)
    except:
        return None

# --- MÓDULO 1: CONEXIÓN ---
def cargar_datos():
    try:
        # Configuración de credenciales
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Abrir archivo principal
        sheet = client.open("SPAN_BD_2026")
        
        db = {}
        tablas_requeridas = ["CONFIGURACION", "CURSOS", "MATERIAS", "INTERRUPCIONES", "HISTORIAL_CAMBIOS"]
        
        for tabla in tablas_requeridas:
            try:
                # Leer datos
                ws = sheet.worksheet(tabla)
                data = ws.get_all_records()
                df = pd.DataFrame(data)
                
                # --- CORRECCIÓN DEL ERROR ---
                # Forzamos que los nombres de columnas sean texto antes de limpiar
                if not df.empty:
                    df.columns = df.columns.astype(str).str.strip()
                
                db[tabla.lower()] = df
                
            except gspread.exceptions.WorksheetNotFound:
                st.error(f"❌ Error Crítico: No encuentro la pestaña '{tabla}' en el Excel. Verifica el nombre exacto.")
                st.stop()
        
        return db, sheet

    except Exception as e:
        st.error(f"❌ Error General de Conexión: {str(e)}")
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
    try:
        df_cursos = db["cursos"]
        if df_cursos.empty:
            return None
            
        # Filtrar curso
        info_curso = df_cursos[df_cursos["ID_Curso"] == curso_seleccionado]
        if info_curso.empty:
            st.error(f"No hay datos definidos para el curso: {curso_seleccionado}")
            return None
        
        info_curso = info_curso.iloc[0]
        
        # Fechas
        fecha_inicio = limpiar_fecha(info_curso["Inicio_Clases_Real"])
        fecha_fin = limpiar_fecha(info_curso["Fin_Clases_Real"])
        
        if pd.isna(fecha_inicio) or pd.isna(fecha_fin):
            st.error(f"Las fechas del curso {curso_seleccionado} no son válidas en el Excel.")
            return None

        # Materias
        materias = db["materias"][db["materias"]["Curso"] == curso_seleccionado].copy()
        
        # Interrupciones
        interrupciones = db["interrupciones"]
        mask = (interrupciones["Estado"] == "ACTIVO") & \
               ((interrupciones["Alcance"] == "GLOBAL") | (interrupciones["Afectados"] == curso_seleccionado))
        eventos_curso = interrupciones[mask]

        # Simulación
        dias_perdidos = 0
        horas_disponibles_reales = 0
        log_diario = []

        fecha_actual = fecha_inicio
        while fecha_actual <= fecha_fin:
            es_fin_semana = fecha_actual.weekday() >= 5
            fecha_str = fecha_actual.strftime("%Y-%m-%d")
            
            evento_hoy = None
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

        total_horas_necesarias = materias["Horas_Totales"].sum() if not materias.empty else 0
        
        # Evitar división por cero
        if total_horas_necesarias > 0:
            cobertura = min(100, int((horas_disponibles_reales / total_horas_necesarias) * 100))
        else:
            cobertura = 100

        return {
            "dias_perdidos": dias_perdidos,
            "horas_reales": horas_disponibles_reales,
            "cobertura": cobertura,
            "detalle": log_diario
        }
    except Exception as e:
        st.error(f"Error calculando cronograma: {str(e)}")
        return None

# --- INTERFAZ PRINCIPAL ---
st.title("⚓ Sistema de Planificación Académica Naval (SPAN)")

db, sheet_obj = cargar_datos()

if db:
    st.sidebar.header("👮‍♂️ Panel de Control")
    
    if db["cursos"].empty:
        st.warning("⚠️ La tabla CURSOS está vacía en el Excel.")
    else:
        # Aseguramos que la columna ID_Curso existe
        if "ID_Curso" not in db["cursos"].columns:
            st.error("Error: No encuentro la columna 'ID_Curso' en la pestaña CURSOS. Revisa los encabezados.")
        else:
            lista_cursos = db["cursos"]["ID_Curso"].dropna().unique()
            curso_actual = st.sidebar.selectbox("Seleccione Curso:", lista_cursos)
            
            tab1, tab2, tab3 = st.tabs(["📊 Situación", "📅 Gestión", "📝 Auditoría"])
            
            with tab1:
                st.header(f"Análisis: {curso_actual}")
                if st.button("🔄 Actualizar Datos"):
                    st.rerun()
                
                res = calcular_cronograma(db, curso_actual)
                
                if res:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Cobertura Académica", f"{res['cobertura']}%")
                    c2.metric("Días Perdidos", f"{res['dias_perdidos']} días")
                    c3.metric("Horas Reales Disp.", res['horas_reales'])
                    
                    if res['cobertura'] < 85:
                        st.error("🚨 CRÍTICO: No se alcanza a cubrir el pensum.")
                    elif res['cobertura'] < 100:
                        st.warning("⚠️ ATENCIÓN: Se requieren horas extra.")
                    else:
                        st.success("✅ OPERATIVO: Tiempo suficiente.")
                        
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
                    user = st.text_input("Grado y Apellido")
                    
                    if st.form_submit_button("Guardar Evento"):
                        if not user or not justif:
                            st.error("Falta usuario o justificación.")
                        else:
                            ws = sheet_obj.worksheet("INTERRUPCIONES")
                            afectados = curso_actual if alcance == "ESPECIFICO" else ""
                            # Formato de fecha para excel
                            fi_str = fi.strftime("%Y-%m-%d")
                            ff_str = ff.strftime("%Y-%m-%d")
                            
                            row = [f"EVT-{int(time.time())}", nombre, fi_str, ff_str, "Militar", alcance, afectados, "ACTIVO", justif]
                            ws.append_row(row)
                            registrar_auditoria(sheet_obj, user, "CREACION", "N/A", f"Creó: {nombre}")
                            st.success("Guardado Exitosamente")
                            time.sleep(1)
                            st.rerun()

            with tab3:
                st.header("Historial de Cambios")
                st.dataframe(db["historial"])
