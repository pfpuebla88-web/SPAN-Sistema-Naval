import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="SPAN Naval", page_icon="⚓", layout="wide")

# --- LISTA DE EVENTOS REALES (Extraídos de tu Excel) ---
TIPOS_EVENTO_NAVAL = [
    "Feriado /Franquicia /Vacaciones",
    "Ceremonias/Desfiles y repasos",
    "Ejercicio de Campaña / Supervivencia / Polígono",
    "Integracion de Escuelas Militares",
    "Semana del Guardiamarina",
    "Combate Naval Jambelí",
    "Crucero Internacional",
    "Visitas profesionales / Crucero Nacional",
    "Exámenes",
    "Exámenes de recuperación",
    "Junta Académica",
    "Prácticas Pre Profesionales",
    "Defensa Tesis",
    "Ceremonia de Graduación",
    "Curso Contraincendio",
    "Imprevisto / Sanción"
]

def limpiar_fecha(fecha_str):
    try:
        if isinstance(fecha_str, (datetime, pd.Timestamp)): return fecha_str
        return pd.to_datetime(fecha_str, dayfirst=True)
    except: return None

def cargar_datos():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("SPAN_BD_2026")
        
        db = {}
        mapa = {"CONFIGURACION": "config", "CURSOS": "cursos", "MATERIAS": "materias", 
                "INTERRUPCIONES": "interrupciones", "HISTORIAL_CAMBIOS": "historial"}
        
        for pestana, nombre in mapa.items():
            try:
                df = pd.DataFrame(sheet.worksheet(pestana).get_all_records())
                if not df.empty: df.columns = df.columns.astype(str).str.strip()
                db[nombre] = df
            except: st.error(f"Falta pestaña: {pestana}"); st.stop()
        
        # Auto-correcciones
        if "Estado" not in db["interrupciones"].columns: db["interrupciones"]["Estado"] = "ACTIVO"
        if "Alcance" not in db["interrupciones"].columns: db["interrupciones"]["Alcance"] = "GLOBAL"
        if "Afectados" not in db["interrupciones"].columns: db["interrupciones"]["Afectados"] = ""

        return db, sheet
    except Exception as e: st.error(f"Error Conexión: {e}"); st.stop()

def registrar_auditoria(sheet, usuario, accion, id_evt, justif):
    try:
        sheet.worksheet("HISTORIAL_CAMBIOS").append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), usuario, accion, id_evt, justif
        ])
    except: pass

def calcular_cronograma(db, curso):
    try:
        info = db["cursos"][db["cursos"]["ID_Curso"] == curso].iloc[0]
        fi = limpiar_fecha(info["Inicio_Clases_Real"])
        ff = limpiar_fecha(info["Fin_Clases_Real"])
        
        if pd.isna(fi) or pd.isna(ff): return None
        
        # Lógica de Materias
        materias = db["materias"]
        if "Curso" in materias.columns: materias = materias[materias["Curso"] == curso]
        
        # Lógica de Interrupciones
        ints = db["interrupciones"]
        mask = (ints["Estado"] == "ACTIVO") & ((ints["Alcance"] == "GLOBAL") | (ints["Afectados"] == curso))
        eventos = ints[mask]
        
        # Simulación
        dias_perdidos = 0
        horas_reales = 0
        log = []
        
        curr = fi
        while curr <= ff:
            es_fds = curr.weekday() >= 5
            estado = "CLASE"
            
            # Buscar evento
            evt_hoy = None
            for _, e in eventos.iterrows():
                efi, eff = limpiar_fecha(e["Fecha_Inicio"]), limpiar_fecha(e["Fecha_Fin"])
                if efi and eff and (efi <= curr <= eff):
                    evt_hoy = e["Nombre_Evento"]
                    break
            
            if es_fds: estado = "FIN DE SEMANA"
            elif evt_hoy: 
                estado = f"⛔ {evt_hoy}"
                dias_perdidos += 1
            else: 
                horas_reales += 6 # Horas pedagógicas promedio
            
            log.append({"Fecha": curr.strftime("%Y-%m-%d"), "Estado": estado})
            curr += timedelta(days=1)
            
        total_req = materias["Horas_Totales"].sum() if "Horas_Totales" in materias.columns else 0
        cobertura = min(100, int((horas_reales / total_req)*100)) if total_req > 0 else 100
        
        return {"dias_perdidos": dias_perdidos, "horas_reales": horas_reales, "cobertura": cobertura, "detalle": log}
    except: return None

# --- INTERFAZ ---
st.title("⚓ SPAN: Planificación Naval 2026")
db, sheet = cargar_datos()

if db:
    st.sidebar.header("👮‍♂️ Panel Oficial")
    if db["cursos"].empty: st.warning("Llenar pestaña CURSOS en Excel.")
    else:
        col_id = "ID_Curso" if "ID_Curso" in db["cursos"].columns else db["cursos"].columns[0]
        curso = st.sidebar.selectbox("Seleccione Curso:", db["cursos"][col_id].dropna().unique())
        
        tab1, tab2, tab3 = st.tabs(["📊 Semáforo Académico", "📅 Gestión Eventos", "📝 Auditoría"])
        
        with tab1:
            st.header(f"Estado de Fuerza: {curso}")
            if st.button("🔄 Actualizar"): st.rerun()
            res = calcular_cronograma(db, curso)
            
            if res:
                c1, c2, c3 = st.columns(3)
                c1.metric("Cobertura Pensum", f"{res['cobertura']}%")
                c2.metric("Días Operativos Perdidos", res['dias_perdidos'])
                c3.metric("Horas Disponibles", res['horas_reales'])
                
                if res['cobertura'] < 85: st.error("🚨 CRÍTICO: No se cumple la carga horaria.")
                elif res['cobertura'] < 100: st.warning("⚠️ ALERTA: Se requiere recuperación.")
                else: st.success("✅ SIN NOVEDAD: Planificación viable.")
                
                with st.expander("Ver Calendario Detallado"):
                    st.dataframe(pd.DataFrame(res["detalle"]))

        with tab2:
            st.subheader("Registrar Nueva Interrupción")
            with st.form("new_evt"):
                # AQUI ESTÁ LA MAGIA: Tu lista real de eventos
                tipo = st.selectbox("Tipo de Evento (Según Reglamento)", TIPOS_EVENTO_NAVAL)
                nombre = st.text_input("Detalle Adicional (Opcional)")
                c1, c2 = st.columns(2)
                fi = c1.date_input("Inicio")
                ff = c2.date_input("Fin")
                alcance = st.radio("Alcance", ["GLOBAL", "ESPECIFICO"])
                justif = st.text_area("Orden General / Justificación")
                user = st.text_input("Responsable")
                
                if st.form_submit_button("Guardar"):
                    ws = sheet.worksheet("INTERRUPCIONES")
                    nom_final = f"{tipo} - {nombre}" if nombre else tipo
                    afec = curso if alcance == "ESPECIFICO" else ""
                    row = [f"EVT-{int(time.time())}", nom_final, str(fi), str(ff), "Militar", alcance, afec, "ACTIVO", justif]
                    ws.append_row(row)
                    registrar_auditoria(sheet, user, "CREACION", "N/A", f"Creó: {nom_final}")
                    st.success("Registrado"); time.sleep(1); st.rerun()
            
            st.divider()
            st.subheader("Anular Evento")
            evts = db["interrupciones"]
            activos = evts[evts["Estado"]=="ACTIVO"]["Nombre_Evento"].unique()
            if len(activos)>0:
                evt_del = st.selectbox("Seleccione evento a anular:", activos)
                m_del = st.text_input("Motivo Anulación")
                u_del = st.text_input("Oficial que anula")
                if st.button("Confirmar Anulación"):
                    cell = sheet.worksheet("INTERRUPCIONES").find(evt_del)
                    sheet.worksheet("INTERRUPCIONES").update_cell(cell.row, 7, "CANCELADO") # Columna Estado aprox
                    registrar_auditoria(sheet, u_del, "ANULACION", "N/A", f"Anuló: {evt_del} - {m_del}")
                    st.success("Anulado"); st.rerun()

        with tab3:
            st.dataframe(db["historial"])
