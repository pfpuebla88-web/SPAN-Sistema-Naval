import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.title("🕵️‍♂️ Modo Diagnóstico")

try:
    # 1. Autenticación
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    st.success("✅ Conexión con Google Exitosa")
    
    # 2. Identificación del Robot
    email_robot = creds.service_account_email
    st.info(f"🤖 Soy el robot con correo: {email_robot}")
    st.write("---")

    # 3. Listar archivos visibles
    st.write("📂 **Archivos que puedo ver en este momento:**")
    archivos = client.list_spreadsheet_files()
    
    if len(archivos) == 0:
        st.warning("⚠️ No veo ningún archivo. ¡Estoy ciego!")
        st.markdown(f"""
        **SOLUCIÓN:**
        1. Copia mi correo: `{email_robot}`
        2. Ve a tu Google Sheet.
        3. Botón 'Compartir' -> Pega mi correo -> Elige 'Editor' -> Enviar.
        """)
    else:
        for archivo in archivos:
            st.write(f"- 📄 {archivo['name']} (ID: {archivo['id']})")
            
        # Intentar abrir el archivo específico
        nombre_buscado = "SPAN_BD_2026"
        st.write("---")
        st.write(f"Intentando abrir específicamente: `{nombre_buscado}`...")
        
        try:
            sheet = client.open(nombre_buscado)
            st.success(f"¡Lo encontré! Abriendo pestaña 'CURSOS'...")
            worksheet = sheet.worksheet("CURSOS")
            data = worksheet.get_all_records()
            st.dataframe(pd.DataFrame(data))
        except Exception as e_inner:
            st.error(f"❌ Lo veo en la lista, pero no pude abrirlo. Error: {e_inner}")

except Exception as e:
    st.error("❌ Error Grave de Configuración:")
    st.code(e)
