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
        res = supabase.table("categorias").select("*").order("nome").execute()
        return res.data if res.data else []
    except:
        return []

def carregar_chaves_db():
    try:
        res = supabase.table("config_chaves").select("*").execute()
        return res.data if res.data else []
    except:
        return []

def buscar_pool_chaves_total():
    pool = []
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if k.strip() and "gsk_" in k])
    chaves_db = carregar_chaves_db()
    if chaves_db:
        pool.extend([item['chave'].strip() for item in chaves_db if "gsk_" in item['chave']])
    return list(set(pool))

def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    # Validação crucial para evitar Erro 400 (Bad Request)
    if not texto and not audio_file:
        return "⚠️ Erro: Descrição ou áudio vazios. Nada para analisar.", ""

    chaves = buscar_pool_chaves_total()
    if not chaves: 
        return "⚠️ Sem chaves configuradas no sistema.", texto
    
    random.shuffle(chaves)
    texto_final = texto if texto else "Processo enviado via áudio."

    for chave in chaves:
        headers = {"Authorization": f"Bearer {chave.strip()}"}
        try:
            # Transcrição de Áudio
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, timeout=20)
                if res_audio.status_code == 200:
                    transcricao = res_audio.json().get('text', '')
                    texto_final = f"[Transcrição]: {transcricao}\nContexto: {texto}"

            # Chamada da IA - Formato Rigoroso para evitar Erro 400
            payload = {
                "model": "llama-3.3-70b-specdec",
                "messages": [
                    {"role": "system", "content": "Você é um Engenheiro de Processos. Analise a rotina operacional de forma técnica."},
                    {"role": "user", "content": f"Domínio: {categoria}\nGatilho: {gatilho}\nComplexidade: {complexidade}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3,
                "max_tokens": 1024
            }
            
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions", 
                headers={"Content-Type": "application/json", **headers}, 
                json=payload, 
                timeout=30
            )
            
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
            else:
                st.warning(f"Chave {chave[:10]}... recusada pela Groq (Erro {res.status_code}).")
                continue
        except Exception as e:
            st.warning(f"Erro técnico na chave {chave[:10]}...: {str(e)}")
            continue
            
    return "❌ Falha técnica: A IA não conseguiu processar sua descrição.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

if not supabase: 
    st.stop()

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    with st.form("form_registro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        cats_db = carregar_categorias()
        nomes_cats = [c['nome'] for c in cats_db] if cats_db else ["Financeiro", "Contábil", "Gestão"]
        cat_sel = c2.selectbox("Domínio:", nomes_cats)
        comp_sel = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho = st.text_input("Gatilho:")
        audio_in = st.audio_input("Explicação por voz")
        descricao = st.text_area("Descrição detalhada do Processo:")
        
        if st.form_submit_button("Sincronizar com Nuvem"):
            if not descricao and not audio_in:
                st.error("Por favor, descreva o processo ou grave um áudio antes de sincronizar.")
            else:
                with st.spinner("IA Analisando..."):
                    analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, audio_file=audio_in)
                    try:
                        supabase.table("registros").insert({
                            "data": data_sel.strftime("%Y-%m-%d"),
                            "dominio": cat_sel,
                            "gatilho": gatilho,
                            "complexidade": comp_sel,
                            "descricao": texto_full,
                            "mapeamento_ia": analise
                        }).execute()
                        st.success("✅ Registro salvo com sucesso no Supabase!")
                        st.markdown(f"### 🤖 Resultado da Análise:\n{analise}")
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

with aba_dash:
    st.subheader("📊 Panorama de Processos")
    if st.button("🔄 Atualizar"): st.rerun()
    try:
        res_view = supabase.table("registros").select("*").order("id", desc=True).execute()
        if res_view.data:
            st.dataframe(pd.DataFrame(res_view.data), use_container_width=True)
    except:
        st.info("Aguardando dados.")

with aba_conf:
    st.subheader("⚙️ Painel de Controle")
    with st.expander("📁 Categorias", expanded=True):
        col_c1, col_c2 = st.columns([3, 1])
        n_cat = col_c1.text_input("Nova Categoria:")
        if col_c2.button("➕"):
            if n_cat:
                supabase.table("categorias").insert({"nome": n_cat.strip()}).execute()
                st.rerun()
        for cat in carregar_categorias():
            c_ed1, c_ed2, c_ed3 = st.columns([3, 1, 1])
            novo_val = c_ed1.text_input(f"e_{cat['id']}", value=cat['nome'], key=f"c_{cat['id']}", label_visibility="collapsed")
            if c_ed2.button("💾", key=f"s_{cat['id']}"):
                supabase.table("categorias").update({"nome": novo_val}).eq("id", cat['id']).execute()
                st.rerun()
            if c_ed3.button("🗑️", key=f"d_{cat['id']}"):
                supabase.table("categorias").delete().eq("id", cat['id']).execute()
                st.rerun()

    with st.expander("🔑 Chaves Groq", expanded=True):
        col_k1, col_k2 = st.columns([3, 1])
        n_key = col_k1.text_input("Nova Chave:", type="password")
        if col_k2.button("➕", key="ak"):
            if n_key.startswith("gsk_"):
                supabase.table("config_chaves").insert({"chave": n_key.strip()}).execute()
                st.rerun()
        for k_obj in carregar_chaves_db():
            k1, k2, k3 = st.columns([3, 1, 1])
            k1.text(f"Ativa: {k_obj['chave'][:10]}...")
            if k3.button("🗑️", key=f"dk_{k_obj['id']}"):
                supabase.table("config_chaves").delete().eq("id", k_obj['id']).execute()
                st.rerun()
