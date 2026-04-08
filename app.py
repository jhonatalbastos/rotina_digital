import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import requests
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gêmeo Digital - Mapeamento", page_icon="🏗️", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÃO PARA CONSOLIDAR POOL DE CHAVES (Secrets + Planilha) ---
def buscar_todas_as_chaves():
    # 1. Carrega chaves mestras dos Secrets
    try:
        secret_keys = st.secrets["GROQ_KEYS"].split("\n")
        pool = [k.strip() for k in secret_keys if k.strip()]
    except:
        pool = []

    # 2. Carrega chaves extras da aba 'Config' da planilha
    try:
        df_config = conn.read(worksheet="Config")
        if not df_config.empty and "Chaves" in df_config.columns:
            extras = df_config["Chaves"].dropna().astype(str).tolist()
            pool.extend([k.strip() for k in extras if k.strip()])
    except:
        pass 
        
    return list(set(pool)) # Remove duplicatas para não gastar requests à toa

# --- LÓGICA DE INTELIGÊNCIA ---
def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    chaves = buscar_todas_as_chaves()
    if not chaves: return "⚠️ Nenhuma chave Groq configurada.", texto
    
    random.shuffle(chaves)
    url = "https://api.groq.com/openai/v1/chat/completions"
    url_transcreve = "https://api.groq.com/openai/v1/audio/transcriptions"
    texto_final = texto

    for chave in chaves:
        headers = {"Authorization": f"Bearer {chave}"}
        try:
            # Transcrição de Voz
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post(url_transcreve, headers=headers, files=files)
                if res_audio.status_code == 200:
                    texto_final = f"[Transcrição]: {res_audio.json()['text']}\n{texto}"

            # Análise de Engenharia de Processo
            payload = {
                "model": "llama-3.3-70b-specdec",
                "messages": [
                    {"role": "system", "content": "Você é um Engenheiro de Processos. Mapeie a lógica operacional do Jhonata na FECD."},
                    {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3
            }
            res = requests.post(url, headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, json=payload)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
            elif res.status_code == 429: continue
        except: continue
    return "❌ Erro nas chaves Groq.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    with st.form("form_mapping", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        cat_sel = c2.selectbox("Domínio:", ["Rotina Contábil", "Auditoria", "Gestão", "Fiscal"])
        comp_sel = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho = st.text_input("Gatilho (O que iniciou isso?):")
        audio_in = st.audio_input("Grave sua lógica")
        descricao = st.text_area("Descrição do Processo:")
        
        if st.form_submit_button("Sincronizar com Nuvem"):
            with st.spinner("IA Processando..."):
                analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, audio_file=audio_in)
                
                # Salva na aba principal (Página1)
                novo_dado = pd.DataFrame([{"Data": data_sel.strftime("%d/%m/%Y"), "Dominio": cat_sel, "Gatilho": gatilho, "Complexidade": comp_sel, "Descricao": texto_full, "Mapeamento_IA": analise}])
                df_main = conn.read(worksheet="Página1")
                df_final = pd.concat([df_main, novo_dado], ignore_index=True)
                conn.update(worksheet="Página1", data=df_final)
                
                st.success("Mapeamento realizado!")
                st.markdown(f"### 🤖 DNA do Processo:\n{analise}")

with aba_dash:
    st.subheader("📊 Panorama de Processos")
    try:
        df_view = conn.read(worksheet="Página1")
        st.dataframe(df_view.iloc[::-1], use_container_width=True)
    except: st.info("Sem dados registrados.")

with aba_conf:
    st.subheader("⚙️ Configurações de Inteligência")
    
    # Adicionar chave nova
    st.markdown("### 🔑 Adicionar Chave Groq Extra")
    nova_key = st.text_input("Cole a nova chave gsk_...", type="password")
    
    if st.button("Salvar Chave na Planilha"):
        if nova_key.startswith("gsk_"):
            df_config = conn.read(worksheet="Config")
            # Adiciona a nova chave à coluna 'Chaves'
            novo_key_df = pd.DataFrame([{"Chaves": nova_key}])
            df_config_final = pd.concat([df_config, novo_key_df], ignore_index=True)
            conn.update(worksheet="Config", data=df_config_final)
            st.success("Chave salva com sucesso na aba Config!")
            st.rerun()
        else:
            st.error("Formato inválido.")

    st.divider()
    st.write(f"📡 Total de chaves em rodízio: **{len(buscar_todas_as_chaves())}**")
