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
    # 1. Tenta pegar do Secrets
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if k.strip() and "gsk_" in k])
    
    # 2. Tenta pegar do Banco
    chaves_db = carregar_chaves_db()
    if chaves_db:
        pool.extend([item['chave'].strip() for item in chaves_db if "gsk_" in item['chave']])
    
    return list(set(pool))

def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    chaves = buscar_pool_chaves_total()
    if not chaves: 
        return "⚠️ Sem chaves configuradas no sistema.", texto
    
    random.shuffle(chaves)
    url_chat = "https://api.groq.com/openai/v1/chat/completions"
    url_audio = "https://api.groq.com/openai/v1/audio/transcriptions"
    texto_final = texto

    for chave in chaves:
        headers = {"Authorization": f"Bearer {chave}"}
        try:
            # Transcrição se houver áudio
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post(url_audio, headers=headers, files=files, timeout=10)
                if res_audio.status_code == 200:
                    texto_final = f"[Transcrição]: {res_audio.json()['text']}\n{texto}"

            # Análise Llama 3
            payload = {
                "model": "llama-3.3-70b-specdec",
                "messages": [
                    {"role": "system", "content": "Você é um Engenheiro de Processos. Analise a rotina operacional de forma técnica."},
                    {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Complexidade: {complexidade}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3
            }
            res = requests.post(url_chat, headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, json=payload, timeout=15)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
        except:
            continue # Tenta a próxima chave se esta falhar
            
    return "❌ Falha técnica ao processar com IA (verifique as chaves).", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

if not supabase: st.stop()

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

# --- ABA REGISTRO ---
with aba_reg:
    with st.form("form_registro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        cats_db = carregar_categorias()
        nomes_cats = [c['nome'] for c in cats_db] if cats_db else ["Financeiro", "Fiscal", "Contábil"]
        cat_sel = c2.selectbox("Domínio:", nomes_cats)
        comp_sel = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho = st.text_input("Gatilho:")
        audio_in = st.audio_input("Explicação por voz")
        descricao = st.text_area("Descrição do Processo:")
        
        if st.form_submit_button("Sincronizar com Cloud"):
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
                    st.success("✅ Registro salvo com sucesso!")
                    st.markdown(f"**Análise Gerada:**\n{analise}")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

# --- ABA PANORAMA ---
with aba_dash:
    st.subheader("📊 Panorama de Processos")
    if st.button("🔄 Atualizar"): st.rerun()
    try:
        res_view = supabase.table("registros").select("*").order("id", desc=True).execute()
        if res_view.data:
            df = pd.DataFrame(res_view.data)
            # Botão para excluir registros individuais no dashboard (opcional, mas útil)
            st.dataframe(df, use_container_width=True)
    except:
        st.info("Aguardando novos dados.")

# --- ABA CONFIGURAÇÕES (EDIÇÃO COMPLETA) ---
with aba_conf:
    st.subheader("⚙️ Painel de Controle")

    # Gestão de Categorias
    with st.expander("📁 Domínios de Trabalho (Editar/Excluir)", expanded=True):
        c_add1, c_add2 = st.columns([3, 1])
        nova_c = c_add1.text_input("Novo Domínio:")
        if c_add2.button("➕ Adicionar", key="btn_add_cat"):
            if nova_c:
                supabase.table("categorias").insert({"nome": nova_c.strip()}).execute()
                st.rerun()
        
        st.write("---")
        for cat in carregar_categorias():
            col1, col2, col3 = st.columns([3, 1, 1])
            novo_n = col1.text_input(f"edit_{cat['id']}", value=cat['nome'], key=f"in_{cat['id']}", label_visibility="collapsed")
            if col2.button("💾", key=f"sv_{cat['id']}"):
                supabase.table("categorias").update({"nome": novo_n}).eq("id", cat['id']).execute()
                st.rerun()
            if col3.button("🗑️", key=f"del_{cat['id']}"):
                supabase.table("categorias").delete().eq("id", cat['id']).execute()
                st.rerun()

    # Gestão de Chaves
    with st.expander("🔑 Chaves Groq (Pool de Rodízio)", expanded=False):
        c_k1, c_k2 = st.columns([3, 1])
        n_k = c_k1.text_input("Nova Chave (gsk_...):", type="password")
        if c_k2.button("➕ Adicionar", key="btn_add_key"):
            if n_k.startswith("gsk_"):
                supabase.table("config_chaves").insert({"chave": n_k.strip()}).execute()
                st.rerun()
        
        st.write("---")
        for k_obj in carregar_chaves_db():
            colk1, colk2, colk3 = st.columns([3, 1, 1])
            # Mascarar chave para segurança
            mask = f"{k_obj['chave'][:10]}...{k_obj['chave'][-4:]}"
            colk1.text(mask)
            subst = colk1.text_input("Substituir:", key=f"kin_{k_obj['id']}", type="password", label_visibility="collapsed")
            if colk2.button("💾", key=f"ksv_{k_obj['id']}"):
                if subst.startswith("gsk_"):
                    supabase.table("config_chaves").update({"chave": subst.strip()}).eq("id", k_obj['id']).execute()
                    st.rerun()
            if colk3.button("🗑️", key=f"kdel_{k_obj['id']}"):
                supabase.table("config_chaves").delete().eq("id", k_obj['id']).execute()
                st.rerun()

    st.write(f"📡 Status: **{len(buscar_pool_chaves_total())}** chaves ativas no sistema.")
