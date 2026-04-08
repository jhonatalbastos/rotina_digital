import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import requests
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gêmeo Digital - Mapeamento", page_icon="🏗️", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
# ttl=0 garante que o app ignore dados em cache e valide as permissões da Service Account em tempo real
conn = st.connection("gsheets", type=GSheetsConnection, ttl=0)

# --- FUNÇÕES DE SUPORTE ---

def carregar_categorias_nuvem():
    """Lê os domínios salvos na aba 'Categorias'."""
    try:
        st.cache_data.clear()
        df_cat = conn.read(worksheet="Categorias", ttl=0)
        if not df_cat.empty and "Nome" in df_cat.columns:
            return [str(c).strip() for c in df_cat["Nome"].dropna().tolist() if str(c).strip()]
    except:
        pass
    return ["Rotina Financeira", "Rotina Contábil", "Auditoria", "Gestão", "Fiscal"]

def buscar_todas_as_chaves():
    """Consolida chaves dos Secrets e da aba 'Config'."""
    pool = []
    if "GROQ_KEYS" in st.secrets:
        secret_keys = st.secrets["GROQ_KEYS"].split("\n")
        pool.extend([k.strip() for k in secret_keys if k.strip()])
    
    try:
        df_config = conn.read(worksheet="Config", ttl=0)
        if not df_config.empty and "Chaves" in df_config.columns:
            extras = df_config["Chaves"].dropna().astype(str).tolist()
            pool.extend([k.strip() for k in extras if k.strip()])
    except:
        pass
    return list(set(pool))

def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    """Transcrição e análise com rodízio de chaves Groq."""
    chaves = buscar_todas_as_chaves()
    if not chaves: 
        return "⚠️ Nenhuma chave Groq configurada.", texto
    
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
                    {"role": "system", "content": "Você é um Engenheiro de Processos. Analise a rotina técnica e operacional de forma estruturada."},
                    {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Complexidade: {complexidade}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3
            }
            res = requests.post(url, headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, json=payload)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
        except:
            continue
    return "❌ Erro na comunicação com a IA.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Mapeamento de Inteligência")

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Atividade", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    with st.form("form_mapping", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        cat_sel = c2.selectbox("Domínio:", carregar_categorias_nuvem())
        comp_sel = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho = st.text_input("Gatilho:")
        audio_in = st.audio_input("Explicação por voz")
        descricao = st.text_area("Descrição do Processo:")
        
        if st.form_submit_button("Sincronizar com Nuvem"):
            with st.spinner("Analisando..."):
                analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, audio_file=audio_in)
                novo_dado = pd.DataFrame([{
                    "Data": data_sel.strftime("%d/%m/%Y"), "Dominio": cat_sel, 
                    "Gatilho": gatilho, "Complexidade": comp_sel, 
                    "Descricao": texto_full, "Mapeamento_IA": analise
                }])
                try:
                    df_atual = conn.read(worksheet="Página1", ttl=0)
                    df_final = pd.concat([df_atual, novo_dado], ignore_index=True)
                    conn.update(worksheet="Página1", data=df_final)
                    st.success("Salvo com sucesso!")
                    st.markdown(f"### 🤖 Análise:\n{analise}")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

with aba_dash:
    st.subheader("📊 Histórico")
    try:
        df_view = conn.read(worksheet="Página1", ttl=0)
        st.dataframe(df_view.iloc[::-1], use_container_width=True)
    except:
        st.info("Nenhum dado disponível.")

with aba_conf:
    st.subheader("⚙️ Painel de Controle")
    
    # Gerenciar Categorias
    st.markdown("### 📁 Domínios de Trabalho")
    cats_lista = carregar_categorias_nuvem()
    texto_area = st.text_area("Categorias (uma por linha):", value="\n".join(cats_lista), height=150)
    
    if st.button("Salvar Domínios"):
        novas = [c.strip() for c in texto_area.split("\n") if c.strip()]
        df_cats = pd.DataFrame({"Nome": novas})
        try:
            st.cache_data.clear()
            conn.update(worksheet="Categorias", data=df_cats)
            st.success("Domínios atualizados!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro técnico: {str(e)}")

    st.divider()

    # Gerenciar Chaves
    st.markdown("### 🔑 Chaves Groq Extras")
    nova_key = st.text_input("Nova chave (gsk_...):", type="password")
    if st.button("Adicionar Chave"):
        if nova_key.startswith("gsk_"):
            try:
                df_c = conn.read(worksheet="Config", ttl=0)
                df_n = pd.concat([df_c, pd.DataFrame([{"Chaves": nova_key}])], ignore_index=True)
                conn.update(worksheet="Config", data=df_n)
                st.success("Chave adicionada!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
