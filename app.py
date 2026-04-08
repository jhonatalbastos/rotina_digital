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
        # Puxa as credenciais que você colou no Secrets
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
    # 1. Pega do Secrets (Streamlit Cloud)
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if k.strip() and "gsk_" in k])
    
    # 2. Pega as que você cadastrou no Banco
    chaves_db = carregar_chaves_db()
    if chaves_db:
        pool.extend([item['chave'].strip() for item in chaves_db if "gsk_" in item['chave']])
    
    return list(set(pool))

def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    chaves = buscar_pool_chaves_total()
    if not chaves: 
        return "⚠️ Sem chaves configuradas no sistema.", texto
    
    random.shuffle(chaves)
    texto_final = texto

    for chave in chaves:
        headers = {"Authorization": f"Bearer {chave.strip()}"}
        try:
            # Transcrição de Áudio (Se houver)
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, timeout=20)
                if res_audio.status_code == 200:
                    texto_final = f"[Transcrição]: {res_audio.json()['text']}\n{texto}"

            # Análise Técnica
            payload = {
                "model": "llama-3.3-70b-specdec",
                "messages": [
                    {"role": "system", "content": "Você é um Engenheiro de Processos. Analise a rotina operacional de forma técnica e estruturada."},
                    {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Complexidade: {complexidade}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3
            }
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Content-Type": "application/json", **headers}, json=payload, timeout=30)
            
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
            else:
                # Feedback visual para você saber que uma chave falhou
                st.warning(f"Chave {chave[:10]}... falhou (Erro {res.status_code}). Tentando próxima...")
                continue
        except Exception as e:
            st.warning(f"Erro na chave {chave[:10]}...: {str(e)}")
            continue
            
    return "❌ Todas as chaves do pool falharam. Verifique os limites na Groq.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

if not supabase: 
    st.warning("Aguardando configuração de conexão...")
    st.stop()

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

# --- ABA 1: REGISTRO ---
with aba_reg:
    with st.form("form_registro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        
        # Carrega categorias do banco dinamicamente
        cats_db = carregar_categorias()
        nomes_cats = [c['nome'] for c in cats_db] if cats_db else ["Rotina Financeira", "Rotina Contábil", "Auditoria", "Gestão", "Fiscal"]
        cat_sel = c2.selectbox("Domínio:", nomes_cats)
        
        comp_sel = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        gatilho = st.text_input("Gatilho (O que iniciou a tarefa?):")
        audio_in = st.audio_input("Explicação por voz")
        descricao = st.text_area("Descrição detalhada do Processo:")
        
        if st.form_submit_button("Sincronizar com Nuvem"):
            with st.spinner("IA Processando..."):
                analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, audio_file=audio_in)
                try:
                    # Inserção direta no Supabase
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
                    st.error(f"Erro ao salvar no banco: {e}")

# --- ABA 2: PANORAMA (HISTÓRICO) ---
with aba_dash:
    st.subheader("📊 Panorama de Processos")
    if st.button("🔄 Atualizar Visualização"): st.rerun()
    try:
        res_view = supabase.table("registros").select("*").order("id", desc=True).execute()
        if res_view.data:
            st.dataframe(pd.DataFrame(res_view.data), use_container_width=True)
        else:
            st.info("Nenhum registro encontrado no banco de dados.")
    except Exception as e:
        st.error(f"Erro ao carregar panorama: {e}")

# --- ABA 3: CONFIGURAÇÕES (GESTÃO TOTAL) ---
with aba_conf:
    st.subheader("⚙️ Painel de Controle Administrativo")

    # Gestão de Categorias
    with st.expander("📁 Domínios (Categorias)", expanded=True):
        col_c1, col_c2 = st.columns([3, 1])
        n_cat = col_c1.text_input("Novo Domínio:")
        if col_c2.button("➕ Adicionar", key="add_cat"):
            if n_cat:
                supabase.table("categorias").insert({"nome": n_cat.strip()}).execute()
                st.rerun()

        st.write("---")
        for cat in carregar_categorias():
            c_ed1, c_ed2, c_ed3 = st.columns([3, 1, 1])
            novo_val = c_ed1.text_input(f"edit_{cat['id']}", value=cat['nome'], key=f"cat_in_{cat['id']}", label_visibility="collapsed")
            if c_ed2.button("💾", key=f"cat_sv_{cat['id']}", help="Salvar Alteração"):
                supabase.table("categorias").update({"nome": novo_val}).eq("id", cat['id']).execute()
                st.rerun()
            if c_ed3.button("🗑️", key=f"cat_del_{cat['id']}", help="Excluir Categoria"):
                supabase.table("categorias").delete().eq("id", cat['id']).execute()
                st.rerun()

    # Gestão de Chaves Groq
    with st.expander("🔑 Pool de Chaves Groq", expanded=True):
        col_k1, col_k2 = st.columns([3, 1])
        n_key = col_k1.text_input("Nova Chave Extra:", type="password")
        if col_k2.button("➕ Adicionar", key="add_key"):
            if n_key.startswith("gsk_"):
                supabase.table("config_chaves").insert({"chave": n_key.strip()}).execute()
                st.rerun()

        st.write("---")
        chaves_existentes = carregar_chaves_db()
        for k_obj in chaves_existentes:
            k_ed1, k_ed2, k_ed3 = st.columns([3, 1, 1])
            mask = f"{k_obj['chave'][:10]}...{k_obj['chave'][-4:]}"
            k_ed1.text(f"Ativa: {mask}")
            substituir = k_ed1.text_input("Trocar por:", key=f"key_in_{k_obj['id']}", type="password", label_visibility="collapsed")
            
            if k_ed2.button("💾", key=f"key_sv_{k_obj['id']}"):
                if substituir.startswith("gsk_"):
                    supabase.table("config_chaves").update({"chave": substituir.strip()}).eq("id", k_obj['id']).execute()
                    st.rerun()
            if k_ed3.button("🗑️", key=f"key_del_{k_obj['id']}"):
                supabase.table("config_chaves").delete().eq("id", k_obj['id']).execute()
                st.rerun()

    st.write(f"📡 Total de chaves em rodízio (Secrets + Banco): **{len(buscar_pool_chaves_total())}**")
