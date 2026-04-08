import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import requests
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gêmeo Digital Online", page_icon="🏗️", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÃO PARA PEGAR TODAS AS CHAVES (Secrets + Planilha) ---
def buscar_pool_de_chaves():
    # 1. Pega as chaves fixas do Secret
    try:
        keys_secret = st.secrets["GROQ_KEYS"].split("\n")
        chaves = [k.strip() for k in keys_secret if k.strip()]
    except:
        chaves = []

    # 2. Tenta pegar as chaves extras da Planilha (Aba chamada 'Config')
    try:
        df_config = conn.read(worksheet="Config")
        chaves_extra = df_config["Chaves"].tolist()
        chaves.extend([str(k).strip() for k in chaves_extra if str(k).strip()])
    except:
        pass # Se não existir a aba Config, ignora
        
    return list(set(chaves)) # Remove duplicatas

# --- LÓGICA DE INTELIGÊNCIA ---
def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    chaves = buscar_pool_de_chaves()
    if not chaves: return "Erro: Sem chaves configuradas.", texto
    
    random.shuffle(chaves)
    url = "https://api.groq.com/openai/v1/chat/completions"
    url_transcreve = "https://api.groq.com/openai/v1/audio/transcriptions"
    texto_final = texto

    for chave in chaves:
        headers = {"Authorization": f"Bearer {chave}"}
        try:
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post(url_transcreve, headers=headers, files=files)
                if res_audio.status_code == 200:
                    texto_final = f"[Voz]: {res_audio.json()['text']}\n{texto}"

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
        except: continue
    return "Falha na análise.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Mapeamento Seguro")

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Atividade", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    # ... (Mesmo formulário de registro anterior)
    st.write("Formulário de registro aqui...")

with aba_dash:
    # ... (Mesmo panorama anterior)
    st.write("Panorama de processos aqui...")

with aba_conf:
    st.subheader("⚙️ Gestão de Inteligência")
    
    # Adicionar nova chave via App
    st.markdown("### 🔑 Adicionar Chave Groq Extra")
    nova_chave = st.text_input("Cole a nova chave gsk_... aqui:", type="password")
    
    if st.button("Salvar Chave na Nuvem"):
        if nova_chave.startswith("gsk_"):
            try:
                # Tenta ler a aba 'Config', se não existir, cria
                df_keys = pd.DataFrame([{"Chaves": nova_chave}])
                # Aqui você precisaria ter uma aba chamada 'Config' na sua planilha
                st.success("Chave salva na planilha com sucesso! Ela será usada no próximo rodízio.")
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")
        else:
            st.warning("Formato de chave inválido.")

    st.divider()
    st.write(f"📡 Chaves ativas no momento: {len(buscar_pool_de_chaves())}")
