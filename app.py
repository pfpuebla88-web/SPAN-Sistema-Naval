import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Título de la App
st.title("⚓ SPAN: Sistema de Planificación Naval")
st.subheader("Verificación de Conectividad")

# 1. Configuración de Credenciales (Autenticación Segura)
# Intentamos conectar usando los secretos guardados en la nube
try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Aquí el sistema busca las llaves que configuraremos en el siguiente paso
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    st.success("✅ Autenticación exitosa con Google.")

    # 2. Conexión a la Base de Datos
    nombre_archivo = "SPAN_BD_2026"  # Debe ser IDÉNTICO a tu Google Sheet
    sheet = client.open(nombre_archivo)
    
    # 3. Lectura de Prueba (Pestaña CURSOS)
    worksheet = sheet.worksheet("CURSOS")
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    st.write("Si puedes ver la siguiente tabla, la conexión es perfecta:")
    st.dataframe(df)

except Exception as e:
    st.error("❌ Error de Conexión.")
    st.warning("Asegúrate de haber configurado los 'Secrets' y compartido el Excel con el correo del robot.")
    st.code(e)
