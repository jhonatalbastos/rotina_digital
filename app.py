import streamlit as st
from st_supabase_connection import SupabaseConnection
import pandas as pd
import datetime
import requests
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gêmeo Digital: Inteligência Operacional", page_icon="🏗️", layout="wide")

# --- CONEXÃO COM SUPABASE ---
conn = st.connection("supabase", type=SupabaseConnection)

# --- FUNÇÕES DE SUPORTE ---

def carregar_categorias():
    """Busca categorias da tabela 'categorias' no Supabase."""
    try:
        res = conn.query("*", table="categorias", ttl=0).execute()
        if res.data:
            return [item['nome'] for item in res.data]
    except:
        pass
    return ["Rotina Contábil", "Auditoria", "Gestão", "Emergências", "Outros"]

def buscar_pool_chaves():
    """Une as chaves fixas dos Secrets com as chaves da tabela 'config_chaves'."""
    pool = []
    # Chaves dos Secrets
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if k.strip()])
    
    # Chaves do Banco de Dados
    try:
        res = conn.query("chave", table="config_chaves", ttl=0).execute()
        if res.data:
            pool.extend([item['chave'] for item in res.data])
    except:
        pass
    return list(set(pool))

def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    """Transcrição e análise técnica usando Groq."""
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
                    {"role": "system", "content": "Você é um Engenheiro de Processos. Analise a rotina operacional de forma técnica e estruturada."},
                    {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Complexidade: {complexidade}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3
            }
            res = requests.post(url_chat, headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, json=payload)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
        except:
            continue
    return "❌ Erro de conexão com a API Groq.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

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
            with st.spinner("IA Analisando e Gravando..."):
                analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, audio_file=audio_in)
                
                try:
                    # Inserção direta no Supabase
                    data_insert = {
                        "data": data_sel.strftime("%Y-%m-%d"),
                        "dominio": cat_sel,
                        "gatilho": gatilho,
                        "complexidade": comp_sel,
                        "descricao": texto_full,
                        "mapeamento_ia": analise
                    }
                    conn.table("registros").insert(data_insert).execute()
                    st.success("✅ Registro salvo com sucesso no banco de dados!")
                    st.markdown(f"### 🤖 Análise Gerada:\n{analise}")
                except Exception as e:
                    st.error(f"Erro ao gravar no banco: {e}")

with aba_dash:
    st.subheader("📊 Panorama de Processos")
    if st.button("🔄 Atualizar Dados"): st.rerun()
    try:
        res_view = conn.query("*", table="registros", ttl=0).execute()
        if res_view.data:
            df = pd.DataFrame(res_view.data)
            st.dataframe(df.sort_values(by="id", ascending=False), use_container_width=True)
        else:
            st.info("Nenhum registro encontrado.")
    except:
        st.error("Erro ao carregar histórico.")

with aba_conf:
    st.subheader("⚙️ Configurações do Sistema")
    
    # Gerenciar Domínios
    st.markdown("### 📁 Gerenciar Domínios")
    cats_lista = carregar_categorias()
    novo_dominio = st.text_input("Adicionar novo domínio:")
    if st.button("Adicionar"):
        if novo_dominio:
            try:
                conn.table("categorias").insert({"nome": novo_dominio}).execute()
                st.success(f"'{novo_dominio}' adicionado!")
                st.rerun()
            except:
                st.error("Erro ou domínio já existente.")

    # Gerenciar Chaves Groq
    st.divider()
    st.markdown("### 🔑 Chaves Groq Extras")
    nova_key = st.text_input("Nova chave (gsk_...):", type="password")
    if st.button("Salvar Chave"):
        if nova_key.startswith("gsk_"):
            try:
                conn.table("config_chaves").insert({"chave": nova_key}).execute()
                st.success("Chave salva no banco!")
                st.rerun()
            except:
                st.error("Erro ao salvar chave.")
    
    st.write(f"📡 Total de chaves em rodízio: **{len(buscar_pool_chaves())}**")
