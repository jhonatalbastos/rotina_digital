import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gêmeo Digital: Inteligência Operacional", page_icon="🏗️", layout="wide")

# --- CONEXÃO MANUAL COM SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["connections"]["supabase"]["url"]
        key = st.secrets["connections"]["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Erro ao ler credenciais do Secrets: {e}")
        return None

supabase: Client = init_connection()

# --- FUNÇÕES DE SUPORTE ---

def carregar_categorias():
    try:
        res = supabase.table("categorias").select("nome").execute()
        if res.data:
            return [item['nome'] for item in res.data]
    except:
        pass
    return ["Rotina Contábil", "Auditoria", "Gestão", "Emergências", "Outros"]

def buscar_pool_chaves():
    pool = []
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if k.strip()])
    try:
        res = supabase.table("config_chaves").select("chave").execute()
        if res.data:
            pool.extend([item['chave'] for item in res.data])
    except:
        pass
    return list(set(pool))

def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    chaves = buscar_pool_chaves()
    if not chaves: return "⚠️ Sem chaves configuradas.", texto
    
    random.shuffle(chaves)
    url_chat = "https://api.groq.com/openai/v1/chat/completions"
    url_audio = "https://api.groq.com/openai/v1/audio/transcriptions"
    texto_final = texto

    for chave in chaves:
        headers = {"Authorization": f"Bearer {chave}"}
        try:
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post(url_audio, headers=headers, files=files)
                if res_audio.status_code == 200:
                    texto_final = f"[Transcrição]: {res_audio.json()['text']}\n{texto}"

            payload = {
                "model": "llama-3.3-70b-specdec",
                "messages": [
                    {"role": "system", "content": "Você é um Engenheiro de Processos especialista. Analise a rotina operacional de forma estruturada."},
                    {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Complexidade: {complexidade}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3
            }
            res = requests.post(url_chat, headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, json=payload)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
        except:
            continue
    return "❌ Erro na API Groq.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

if not supabase:
    st.stop() # Interrompe o app se a conexão falhar

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    with st.form("form_registro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        cat_sel = c2.selectbox("Domínio:", carregar_categorias())
        comp_sel = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho = st.text_input("Gatilho:")
        audio_in = st.audio_input("Explicação por voz")
        descricao = st.text_area("Descrição do Processo:")
        
        if st.form_submit_button("Sincronizar com Supabase"):
            with st.spinner("IA Analisando..."):
                analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, audio_file=audio_in)
                
                try:
                    data_insert = {
                        "data": data_sel.strftime("%Y-%m-%d"),
                        "dominio": cat_sel,
                        "gatilho": gatilho,
                        "complexidade": comp_sel,
                        "descricao": texto_full,
                        "mapeamento_ia": analise
                    }
                    supabase.table("registros").insert(data_insert).execute()
                    st.success("✅ Salvo no Supabase!")
                    st.markdown(f"### 🤖 Análise:\n{analise}")
                except Exception as e:
                    st.error(f"Erro ao gravar: {e}")

with aba_dash:
    st.subheader("📊 Panorama de Processos")
    if st.button("🔄 Atualizar"): st.rerun()
    try:
        res_view = supabase.table("registros").select("*").order("id", desc=True).execute()
        if res_view.data:
            st.dataframe(pd.DataFrame(res_view.data), use_container_width=True)
        else:
            st.info("Nenhum registro.")
    except:
        st.error("Erro ao carregar dados.")

with aba_conf:
    st.subheader("⚙️ Configurações")
    
    # Categorias
    cats_atuais = carregar_categorias()
    st.write(f"Categorias ativas: {', '.join(cats_atuais)}")
    novo_dom = st.text_input("Novo domínio:")
    if st.button("Adicionar"):
        if novo_dom:
            supabase.table("categorias").insert({"nome": novo_dom}).execute()
            st.rerun()

    st.divider()
    
    # Chaves Groq
    st.markdown("### 🔑 Chaves Groq")
    nova_key = st.text_input("Nova chave extra:", type="password")
    if st.button("Salvar Chave"):
        if nova_key.startswith("gsk_"):
            supabase.table("config_chaves").insert({"chave": nova_key}).execute()
            st.rerun()
