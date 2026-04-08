import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
import json

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
    
    for chave in chaves:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {chave.strip()}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "Você é um Engenheiro de Processos especialista. Analise a rotina operacional."},
                        {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Complexidade: {complexidade}\nProcesso: {texto}"}
                    ],
                    "temperature": 0.3
                },
                timeout=20
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'], texto
            else:
                continue
        except:
            continue

    return "❌ Falha na comunicação com a IA.", texto

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

if not supabase: st.stop()

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

# --- ABA 1: REGISTRO ---
with aba_reg:
    with st.form("registro_final", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_f = c1.date_input("Data:", value=datetime.date.today())
        
        cats = carregar_categorias()
        nomes = [c['nome'] for c in cats] if cats else ["Financeiro", "Auditória", "Gestão"]
        cat_f = c2.selectbox("Domínio:", nomes)
        comp_f = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho_f = st.text_input("Gatilho:")
        desc_f = st.text_area("Descrição do Processo (Obrigatório):")
        
        if st.form_submit_button("Sincronizar com Cloud"):
            if not desc_f:
                st.error("Preencha a descrição do processo.")
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
                        st.markdown(f"**Análise Gerada:**\n{analise}")
                    except Exception as e:
                        st.error(f"Erro no banco: {e}")

# --- ABA 2: PANORAMA (COM FUNÇÃO DE DELETAR) ---
with aba_dash:
    st.subheader("📊 Panorama de Processos")
    if st.button("🔄 Atualizar Histórico"): st.rerun()
    
    try:
        res = supabase.table("registros").select("*").order("created_at", desc=True).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            
            # Cabeçalho da tabela customizada
            cols = st.columns([1, 2, 2, 2, 1, 4, 1])
            cols[0].write("**ID**")
            cols[1].write("**Data**")
            cols[2].write("**Domínio**")
            cols[3].write("**Gatilho**")
            cols[4].write("**Comp.**")
            cols[5].write("**Descrição**")
            cols[6].write("**Ação**")

            st.write("---")

            for index, row in df.iterrows():
                c = st.columns([1, 2, 2, 2, 1, 4, 1])
                c[0].write(row['id'])
                c[1].write(row['data'])
                c[2].write(row['dominio'])
                c[3].write(row['gatilho'])
                c[4].write(row['complexidade'])
                c[5].write(row['descricao'][:100] + "...") # Preview do texto
                
                # Botão de deletar para cada linha
                if c[6].button("🗑️", key=f"del_reg_{row['id']}"):
                    supabase.table("registros").delete().eq("id", row['id']).execute()
                    st.success(f"Registro {row['id']} removido!")
                    st.rerun()
        else:
            st.info("Nenhum registro encontrado.")
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")

# --- ABA 3: CONFIGURAÇÕES ---
with aba_conf:
    st.subheader("⚙️ Painel Administrativo")
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.write("### 📁 Domínios")
        new_c = st.text_input("Novo Domínio:")
        if st.button("Adicionar Categoria"):
            if new_c:
                supabase.table("categorias").insert({"nome": new_c.strip()}).execute()
                st.rerun()
        
        st.write("---")
        for cat in carregar_categorias():
            c1, c2 = st.columns([4, 1])
            c1.text(cat['nome'])
            if c2.button("🗑️", key=f"d_cat_{cat['id']}"):
                supabase.table("categorias").delete().eq("id", cat['id']).execute()
                st.rerun()

    with col_right:
        st.write("### 🔑 Pool de Chaves")
        new_k = st.text_input("Adicionar Chave Groq:", type="password")
        if st.button("Salvar Chave"):
            if new_k.startswith("gsk_"):
                supabase.table("config_chaves").insert({"chave": new_k.strip()}).execute()
                st.rerun()
        
        st.write("---")
        for k in carregar_chaves_db():
            c1, c2 = st.columns([4, 1])
            c1.text(f"Ativa: {k['chave'][:12]}...")
            if c2.button("🗑️", key=f"d_key_{k['id']}"):
                supabase.table("config_chaves").delete().eq("id", k['id']).execute()
                st.rerun()
