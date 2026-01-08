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

# --- MÓDULO 1: CONEXIÓN ROBUSTA ---
def cargar_datos():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("SPAN_BD_2026")
        
        db = {}
        # Mapeo exacto: Nombre en Excel -> Nombre en Código
        mapa_pestanas = {
            "CONFIGURACION": "config",
            "CURSOS": "cursos",
            "MATERIAS": "materias",
            "INTERRUPCIONES": "interrupciones",
            "HISTORIAL_CAMBIOS": "historial"
        }
        
        for pestana_excel, nombre_codigo in mapa_pestanas.items():
            try:
                ws = sheet.worksheet(pestana_excel)
                data = ws.get_all_records()
                df = pd.DataFrame(data)
                
                # 1. Limpiar encabezados (quitar espacios)
                if not df.empty:
                    df.columns = df.columns.astype(str).str.strip()
                
                db[nombre_codigo] = df
                
            except gspread.exceptions.WorksheetNotFound:
                st.error(f"❌ Falta la pestaña '{pestana_excel}' en el Excel.")
                st.stop()
        
        # --- AUTO-CORRECCIONES (SANITY CHECK) ---
        # Si falta la columna 'Estado' en Interrupciones, la creamos virtualmente
        if "Estado" not in db["interrupciones"].columns:
            st.toast("⚠️ Aviso: No encontré columna 'Estado' en Interrupciones. Asumiendo todo como ACTIVO.")
            db["interrupciones"]["Estado"] = "ACTIVO"
            
        # Si falta columna 'Alcance', asumimos GLOBAL
        if "Alcance" not in db["interrupciones"].columns:
            db["interrupciones"]["Alcance"] = "GLOBAL"

        # Si falta columna 'Afectados', asumimos vacío
        if "Afectados" not in db["interrupciones"].columns:
            db["interrupciones"]["Afectados"] = ""

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

# --- MÓDULO 2: CÁLCULO ---
def calcular_cronograma(db, curso_seleccionado):
    try:
        df_cursos = db["cursos"]
        if df_cursos.empty: return None
            
        info_curso = df_cursos[df_cursos["ID_Curso"] == curso_seleccionado]
        if info_curso.empty:
            st.error(f"Curso no encontrado: {curso_seleccionado}")
            return None
        
        info_curso = info_curso.iloc[0]
        fecha_inicio = limpiar_fecha(info_curso["Inicio_Clases_Real"])
        fecha_fin = limpiar_fecha(info_curso["Fin_Clases_Real"])
        
        if pd.isna(fecha_inicio) or pd.isna(fecha_fin):
            st.error("Fechas inválidas en curso.")
            return None

        # Materias
        materias = db["materias"]
        if "Curso" in materias.columns:
            materias = materias[materias["Curso"] == curso_seleccionado]
        
        # Interrupciones
        interrupciones = db["interrupciones"]
        
        # Filtro seguro
        mask = (interrupciones["Estado"] == "ACTIVO") & \
               ((interrupciones["Alcance"] == "GLOBAL") | (interrupciones["Afectados"] == curso_seleccionado))
        eventos_curso = interrupciones[mask]

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

        total_horas_necesarias = materias["Horas_Totales"].sum() if "Horas_Totales" in materias.columns else 0
        
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
        st.error(f"Error detallado en cálculo: {str(e)}")
        return None

# --- INTERFAZ ---
st.title("⚓ Sistema de Planificación Académica Naval (SPAN)")

db, sheet_obj = cargar_datos()

if db:
    st.sidebar.header("👮‍♂️ Panel de Control")
    
    if db["cursos"].empty:
        st.warning("⚠️ Tabla CURSOS vacía.")
    else:
        col_id = "ID_Curso" if "ID_Curso" in db["cursos"].columns else db["cursos"].columns[0]
        lista_cursos = db["cursos"][col_id].dropna().unique()
        curso_actual = st.sidebar.selectbox("Seleccione Curso:", lista_cursos)
        
        tab1, tab2, tab3 = st.tabs(["📊 Situación", "📅 Gestión", "📝 Auditoría"])
        
        with tab1:
            st.header(f"Análisis: {curso_actual}")
            if st.button("🔄 Actualizar"): st.rerun()
            
            res = calcular_cronograma(db, curso_actual)
            
            if res:
                c1, c2, c3 = st.columns(3)
                c1.metric("Cobertura", f"{res['cobertura']}%")
                c2.metric("Días Perdidos", f"{res['dias_perdidos']}")
                c3.metric("Horas Reales", res['horas_reales'])
                
                if res['cobertura'] < 85: st.error("🚨 CRÍTICO")
                elif res['cobertura'] < 100: st.warning("⚠️ ATENCIÓN")
                else: st.success("✅ OPERATIVO")
                
                with st.expander("Ver Detalle"):
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
                    ws = sheet_obj.worksheet("INTERRUPCIONES")
                    afectados = curso_actual if alcance == "ESPECIFICO" else ""
                    fi_str = fi.strftime("%Y-%m-%d")
                    ff_str = ff.strftime("%Y-%m-%d")
                    # ID, Nombre, Ini, Fin, Tipo, Alcance, Afectados, ESTADO, Justif
                    row = [f"EVT-{int(time.time())}", nombre, fi_str, ff_str, "Militar", alcance, afectados, "ACTIVO", justif]
                    ws.append_row(row)
                    registrar_auditoria(sheet_obj, user, "CREACION", "N/A", f"Creó: {nombre}")
                    st.success("Guardado")
                    time.sleep(1)
                    st.rerun()

        with tab3:
            st.header("Historial")
            # Corrección del error de visualización
            if not db["historial"].empty:
                st.dataframe(db["historial"])
            else:
                st.info("No hay registros de auditoría aún.")
