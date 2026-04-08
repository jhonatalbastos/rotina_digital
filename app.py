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
    # Chaves fixas do Secrets
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if k.strip()])
    
    # Chaves dinâmicas do Banco
    chaves_db = carregar_chaves_db()
    if chaves_db:
        pool.extend([item['chave'] for item in chaves_db])
    
    return list(set(pool))

def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    chaves = buscar_pool_chaves_total()
    if not chaves: return "⚠️ Nenhuma chave Groq disponível.", texto
    
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
    return "❌ Falha em todas as chaves tentadas.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

if not supabase:
    st.stop()

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    with st.form("form_registro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        
        cats = carregar_categorias()
        nomes_cats = [c['nome'] for c in cats] if cats else ["Padrão"]
        cat_sel = c2.selectbox("Domínio:", nomes_cats)
        
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
                    st.success("✅ Processo mapeado e salvo!")
                    st.markdown(f"### 🤖 Análise:\n{analise}")
                except Exception as e:
                    st.error(f"Erro ao gravar: {e}")

with aba_dash:
    st.subheader("📊 Panorama de Processos")
    if st.button("🔄 Atualizar Histórico"): st.rerun()
    try:
        res_view = supabase.table("registros").select("*").order("id", desc=True).execute()
        if res_view.data:
            st.dataframe(pd.DataFrame(res_view.data), use_container_width=True)
    except:
        st.info("Aguardando registros...")

with aba_conf:
    st.subheader("⚙️ Painel de Controle")
    
    # --- SEÇÃO 1: CATEGORIAS ---
    with st.expander("📁 Gestão de Domínios (Categorias)", expanded=True):
        col_c1, col_c2 = st.columns([3, 1])
        n_cat = col_c1.text_input("Nova Categoria:")
        if col_c2.button("➕ Adicionar", key="add_cat"):
            if n_cat:
                supabase.table("categorias").insert({"nome": n_cat.strip()}).execute()
                st.rerun()

        st.write("---")
        for cat in carregar_categorias():
            c_ed1, c_ed2, c_ed3 = st.columns([3, 1, 1])
            novo_val = c_ed1.text_input(f"Cat_{cat['id']}", value=cat['nome'], key=f"cat_in_{cat['id']}", label_visibility="collapsed")
            if c_ed2.button("💾", key=f"cat_sv_{cat['id']}"):
                supabase.table("categorias").update({"nome": novo_val}).eq("id", cat['id']).execute()
                st.rerun()
            if c_ed3.button("🗑️", key=f"cat_del_{cat['id']}"):
                supabase.table("categorias").delete().eq("id", cat['id']).execute()
                st.rerun()

    # --- SEÇÃO 2: CHAVES GROQ ---
    with st.expander("🔑 Gestão de Chaves Groq", expanded=True):
        col_k1, col_k2 = st.columns([3, 1])
        n_key = col_k1.text_input("Nova Chave (gsk_...):", type="password")
        if col_k2.button("➕ Adicionar", key="add_key"):
            if n_key.startswith("gsk_"):
                supabase.table("config_chaves").insert({"chave": n_key.strip()}).execute()
                st.rerun()

        st.write("---")
        chaves_existentes = carregar_chaves_db()
        for k_obj in chaves_existentes:
            k_ed1, k_ed2, k_ed3 = st.columns([3, 1, 1])
            # Mascaramos a chave para não ficar exposta na tela de config
            chave_mask = f"{k_obj['chave'][:10]}...{k_obj['chave'][-4:]}"
            k_ed1.text(f"Chave: {chave_mask}")
            
            # Edição (Caso queira substituir uma chave antiga por uma nova na mesma linha)
            nova_val_k = k_ed1.text_input("Substituir por:", key=f"key_in_{k_obj['id']}", type="password", label_visibility="collapsed")
            
            if k_ed2.button("💾", key=f"key_sv_{k_obj['id']}"):
                if nova_val_k.startswith("gsk_"):
                    supabase.table("config_chaves").update({"chave": nova_val_k.strip()}).eq("id", k_obj['id']).execute()
                    st.rerun()
            
            if k_ed3.button("🗑️", key=f"key_del_{k_obj['id']}"):
                supabase.table("config_chaves").delete().eq("id", k_obj['id']).execute()
                st.rerun()

    st.info(f"📡 Total de chaves em rodízio (Secrets + Banco): {len(buscar_pool_chaves_total())}")
