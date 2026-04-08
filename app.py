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

# --- FUNÇÕES DE SUPORTE ---

def carregar_categorias_nuvem():
    try:
        df_cat = conn.read(worksheet="Categorias")
        if not df_cat.empty and "Nome" in df_cat.columns:
            return df_cat["Nome"].dropna().astype(str).tolist()
    except:
        pass
    return ["Rotina Contábil", "Auditoria", "Gestão", "Fiscal"]

def buscar_todas_as_chaves():
    pool = []
    # 1. Chaves dos Secrets
    try:
        secret_keys = st.secrets["GROQ_KEYS"].split("\n")
        pool.extend([k.strip() for k in secret_keys if k.strip()])
    except:
        pass
    # 2. Chaves da Planilha
    try:
        df_config = conn.read(worksheet="Config")
        if not df_config.empty and "Chaves" in df_config.columns:
            extras = df_config["Chaves"].dropna().astype(str).tolist()
            pool.extend([k.strip() for k in extras if k.strip()])
    except:
        pass
    return list(set(pool))

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
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post(url_transcreve, headers=headers, files=files)
                if res_audio.status_code == 200:
                    texto_final = f"[Transcrição]: {res_audio.json()['text']}\n{texto}"

            payload = {
                "model": "llama-3.3-70b-specdec",
                "messages": [
                    {"role": "system", "content": "Você é um Engenheiro de Processos. Mapeie a lógica operacional do Jhonata na FECD."},
                    {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Complexidade: {complexidade}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3
            }
            res = requests.post(url, headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, json=payload)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
        except: continue
    return "❌ Erro nas chaves Groq.", texto_final

# --- INTERFACE PRINCIPAL ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

# Definição das Abas (Aqui é onde aba_conf é criada)
aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    with st.form("form_mapping", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        
        # Carrega categorias dinamicamente da planilha
        lista_cats = carregar_categorias_nuvem()
        cat_sel = c2.selectbox("Domínio:", lista_cats)
        
        comp_sel = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho = st.text_input("Gatilho (O que iniciou isso?):")
        audio_in = st.audio_input("Grave sua lógica")
        descricao = st.text_area("Descrição do Processo:")
        
        if st.form_submit_button("Sincronizar com Nuvem"):
            with st.spinner("IA Processando..."):
                analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, audio_file=audio_in)
                
                novo_dado = pd.DataFrame([{
                    "Data": data_sel.strftime("%d/%m/%Y"), 
                    "Dominio": cat_sel, 
                    "Gatilho": gatilho, 
                    "Complexidade": comp_sel, 
                    "Descricao": texto_full, 
                    "Mapeamento_IA": analise
                }])
                
                df_main = conn.read(worksheet="Página1")
                df_final = pd.concat([df_main, novo_dado], ignore_index=True)
                conn.update(worksheet="Página1", data=df_final)
                
                st.success("Mapeamento realizado!")
                st.markdown(f"### 🤖 DNA do Processo:\n{analise}")

with aba_dash:
    st.subheader("📊 Panorama de Processos")
    try:
        df_view = conn.read(worksheet="Página1")
        if not df_view.empty:
            st.dataframe(df_view.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhum registro encontrado.")
    except:
        st.error("Erro ao carregar a Página1 da planilha.")

with aba_conf:
    st.subheader("⚙️ Configurações de Inteligência")
    
    # --- GERENCIAR DOMÍNIOS ---
    st.markdown("### 📁 Gerenciar Domínios")
    lista_atual = carregar_categorias_nuvem()
    texto_cats = st.text_area("Edite os domínios (um por linha):", value="\n".join(lista_atual), height=150)
    
    if st.button("Atualizar Domínios"):
        novas_cats = [c.strip() for c in texto_cats.split("\n") if c.strip()]
        df_new_cats = pd.DataFrame({"Nome": novas_cats})
        conn.update(worksheet="Categorias", data=df_new_cats)
        st.success("Domínios atualizados!")
        st.rerun()

    st.divider()

    # --- ADICIONAR CHAVES ---
    st.markdown("### 🔑 Adicionar Chave Groq Extra")
    nova_key = st.text_input("Cole a nova chave gsk_...", type="password")
    
    if st.button("Salvar Chave"):
        if nova_key.startswith("gsk_"):
            df_config = conn.read(worksheet="Config")
            novo_key_df = pd.DataFrame([{"Chaves": nova_key}])
            df_config_final = pd.concat([df_config, novo_key_df], ignore_index=True)
            conn.update(worksheet="Config", data=df_config_final)
            st.success("Chave salva na aba Config!")
            st.rerun()
        else:
            st.error("Formato de chave inválido.")

    st.write(f"📡 Chaves em rodízio: **{len(buscar_todas_as_chaves())}**")
