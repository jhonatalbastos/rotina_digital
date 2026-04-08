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
    for chave in chaves:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {chave.strip()}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": "Você é um Engenheiro de Processos especialista."},
                        {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Processo: {texto}"}
                    ],
                    "temperature": 0.3
                }, timeout=20
            )
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'], texto
        except: continue
    return "❌ Falha na IA.", texto

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Inteligência Operacional")

if not supabase: st.stop()

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    with st.form("registro_vfinal", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_f = c1.date_input("Data:", value=datetime.date.today())
        cats = carregar_categorias()
        nomes = [c['nome'] for c in cats] if cats else ["Financeiro", "Auditória", "Gestão"]
        cat_f = c2.selectbox("Domínio:", nomes)
        comp_f = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        gatilho_f = st.text_input("Gatilho:")
        desc_f = st.text_area("Descrição do Processo:")
        if st.form_submit_button("Sincronizar com Cloud"):
            if desc_f:
                with st.spinner("IA Analisando..."):
                    analise, texto_final = analisar_processo_ia(desc_f, cat_f, gatilho_f, comp_f)
                    supabase.table("registros").insert({
                        "data": data_f.strftime("%Y-%m-%d"), "dominio": cat_f, "gatilho": gatilho_f,
                        "complexidade": comp_f, "descricao": texto_final, "mapeamento_ia": analise
                    }).execute()
                    st.success("✅ Salvo!")
                    st.markdown(f"**Análise:**\n{analise}")

with aba_dash:
    st.subheader("📊 Panorama de Processos")
    res = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        
        # --- SISTEMA DE DELEÇÃO EM MASSA OTIMIZADO ---
        with st.expander("🗑️ Limpeza de Registros", expanded=True):
            col_sel1, col_sel2 = st.columns([1, 4])
            
            # Checkbox para selecionar tudo
            selecionar_tudo = col_sel1.checkbox("Selecionar Todos")
            
            todos_ids = df['id'].tolist()
            default_selecao = todos_ids if selecionar_tudo else []
            
            ids_para_deletar = st.multiselect(
                "IDs para exclusão:",
                options=todos_ids,
                default=default_selecao,
                format_func=lambda x: f"ID {x} - {df[df['id']==x]['descricao'].iloc[0][:50]}..."
            )
            
            if st.button("🔴 Confirmar Exclusão em Massa", type="primary"):
                if ids_para_deletar:
                    with st.spinner(f"Excluindo {len(ids_para_deletar)} registros..."):
                        # Deleção eficiente usando o operador 'in' do Supabase
                        supabase.table("registros").delete().in_("id", ids_para_deletar).execute()
                    st.success(f"Sucesso: {len(ids_para_deletar)} registros removidos.")
                    st.rerun()
                else:
                    st.warning("Nenhum item selecionado.")

        # Tabela nativa do Streamlit
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum dado para exibir.")

with aba_conf:
    st.subheader("⚙️ Configurações")
    c_l, c_r = st.columns(2)
    with c_l:
        st.write("### 📁 Domínios")
        n_c = st.text_input("Nova Categoria:")
        if st.button("Add Cat"):
            if n_c: supabase.table("categorias").insert({"nome": n_c.strip()}).execute(); st.rerun()
        for c in carregar_categorias():
            col1, col2 = st.columns([4, 1])
            col1.text(c['nome'])
            if col2.button("🗑️", key=f"dc_{c['id']}"):
                supabase.table("categorias").delete().eq("id", c['id']).execute(); st.rerun()
    with c_r:
        st.write("### 🔑 Chaves")
        n_k = st.text_input("Nova Chave:", type="password")
        if st.button("Add Key"):
            if n_k.startswith("gsk_"): supabase.table("config_chaves").insert({"chave": n_k.strip()}).execute(); st.rerun()
        for k in carregar_chaves_db():
            col1, col2 = st.columns([4, 1])
            col1.text(f"Ativa: {k['chave'][:12]}...")
            if col2.button("🗑️", key=f"dk_{k['id']}"):
                supabase.table("config_chaves").delete().eq("id", k['id']).execute(); st.rerun()
