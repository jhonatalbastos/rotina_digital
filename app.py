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
        st.error(f"Erro nas credenciais: {e}")
        return None

supabase: Client = init_connection()

# --- FUNÇÕES DE SUPORTE ---

def carregar_categorias():
    try:
        res = supabase.table("categorias").select("*").order("nome").execute()
        return res.data if res.data else []
    except: return []

def carregar_chaves_db():
    try:
        res = supabase.table("config_chaves").select("*").execute()
        return res.data if res.data else []
    except: return []

def buscar_pool_chaves_total():
    pool = []
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if "gsk_" in k])
    chaves_db = carregar_chaves_db()
    if chaves_db:
        pool.extend([item['chave'].strip() for item in chaves_db if "gsk_" in item['chave']])
    return list(set(pool))

def analisar_processo_ia(texto, categoria, gatilho, complexidade):
    chaves = buscar_pool_chaves_total()
    if not chaves: return "⚠️ Sem chaves no sistema.", texto
    
    random.shuffle(chaves)
    
    # Payload minimalista para evitar erro 400
    for chave in chaves:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {chave.strip()}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant", # Modelo mais leve e estável para teste
                    "messages": [
                        {"role": "user", "content": f"Analise tecnicamente este processo de {categoria}: {texto}"}
                    ]
                },
                timeout=20
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'], texto
            else:
                st.warning(f"Chave {chave[:8]}... negada (Erro {response.status_code})")
                continue
        except:
            continue

    return "❌ Falha na comunicação com a IA.", texto

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

if not supabase: st.stop()

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    with st.form("registro_simplificado", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_f = c1.date_input("Data:", value=datetime.date.today())
        
        cats = carregar_categorias()
        nomes = [c['nome'] for c in cats] if cats else ["Geral"]
        cat_f = c2.selectbox("Domínio:", nomes)
        comp_f = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho_f = st.text_input("Gatilho:")
        desc_f = st.text_area("Descrição do Processo (Obrigatório):")
        
        if st.form_submit_button("Sincronizar com Cloud"):
            if not desc_f:
                st.error("Preencha a descrição.")
            else:
                with st.spinner("IA Analisando..."):
                    analise, texto_final = analisar_processo_ia(desc_f, cat_f, gatilho_f, comp_f)
                    try:
                        supabase.table("registros").insert({
                            "data": data_f.strftime("%Y-%m-%d"),
                            "dominio": cat_f,
                            "gatilho": gatilho_f,
                            "complexidade": comp_f,
                            "descricao": texto_final,
                            "mapeamento_ia": analise
                        }).execute()
                        st.success("✅ Dados salvos com sucesso!")
                        st.markdown(f"**Análise:**\n{analise}")
                    except Exception as e:
                        st.error(f"Erro no banco: {e}")

with aba_dash:
    if st.button("🔄 Atualizar"): st.rerun()
    res = supabase.table("registros").select("*").order("id", desc=True).execute()
    if res.data: st.dataframe(pd.DataFrame(res.data), use_container_width=True)

with aba_conf:
    st.subheader("⚙️ Gestão")
    with st.expander("📁 Categorias"):
        new_c = st.text_input("Nova:")
        if st.button("Add"):
            supabase.table("categorias").insert({"nome": new_c}).execute()
            st.rerun()
        for c in carregar_categorias():
            col1, col2 = st.columns([4, 1])
            col1.text(c['nome'])
            if col2.button("🗑️", key=f"d_{c['id']}"):
                supabase.table("categorias").delete().eq("id", c['id']).execute()
                st.rerun()
                
    with st.expander("🔑 Chaves"):
        new_k = st.text_input("Nova GSK:", type="password")
        if st.button("Salvar"):
            if new_k.startswith("gsk_"):
                supabase.table("config_chaves").insert({"chave": new_k}).execute()
                st.rerun()
        for k in carregar_chaves_db():
            col1, col2 = st.columns([4, 1])
            col1.text(f"Ativa: {k['chave'][:12]}...")
            if col2.button("🗑️", key=f"dk_{k['id']}"):
                supabase.table("config_chaves").delete().eq("id", k['id']).execute()
                st.rerun()
