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

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama (CRUD)", "⚙️ Configurações"])

# --- ABA 1: CRIAÇÃO ---
with aba_reg:
    with st.form("form_create", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_f = c1.date_input("Data:", value=datetime.date.today())
        cats = carregar_categorias()
        nomes = [c['nome'] for c in cats] if cats else ["Financeiro", "Auditória"]
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
                    st.success("✅ Registro Criado!")
                    st.rerun()

# --- ABA 2: LEITURA, EDIÇÃO E EXCLUSÃO (CRUD OTIMIZADO) ---
with aba_dash:
    st.subheader("📊 Gestão de Processos")
    res = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        
        col_btn1, col_btn2, _ = st.columns([2, 2, 6])
        if col_btn1.button("🔄 Atualizar Panorama"): st.rerun()
        
        st.write("---")
        
        # Cabeçalho da Tabela
        h = st.columns([0.5, 0.8, 1.2, 1.5, 1, 3, 1, 1])
        h[0].write("**Sel.**")
        h[1].write("**ID**")
        h[2].write("**Data**")
        h[3].write("**Domínio**")
        h[4].write("**Comp.**")
        h[5].write("**Descrição**")
        h[6].write("**Editar**")
        h[7].write("**Análise**")

        selecao_atual = []

        for _, row in df.iterrows():
            # Ajustando o layout para incluir o botão de visualização
            c = st.columns([0.5, 0.8, 1.2, 1.5, 1, 3, 1, 1])
            
            if c[0].checkbox("", key=f"sel_{row['id']}"):
                selecao_atual.append(row['id'])
            
            c[1].write(row['id'])
            c[2].write(row['data'])
            c[3].write(row['dominio'])
            c[4].write(row['complexidade'])
            c[5].write(row['descricao'][:70] + "...")
            
            # Botão de Edição
            if c[6].button("📝", key=f"edit_{row['id']}"):
                st.session_state[f"editing_{row['id']}"] = True

            # Botão para Ver Análise da IA (O campo que estava faltando)
            ver_analise = c[7].button("🔍", key=f"view_{row['id']}")

            # 1. Área de Edição
            if st.session_state.get(f"editing_{row['id']}", False):
                with st.expander(f"✏️ Editando Registro #{row['id']}", expanded=True):
                    with st.form(f"f_edit_{row['id']}"):
                        ed_gatilho = st.text_input("Gatilho", value=row['gatilho'])
                        ed_desc = st.text_area("Descrição", value=row['descricao'])
                        if st.form_submit_button("Salvar Alterações"):
                            supabase.table("registros").update({
                                "gatilho": ed_gatilho, "descricao": ed_desc
                            }).eq("id", row['id']).execute()
                            st.session_state[f"editing_{row['id']}"] = False
                            st.rerun()
                        if st.form_submit_button("Cancelar"):
                            st.session_state[f"editing_{row['id']}"] = False
                            st.rerun()

            # 2. Área de Visualização da Análise IA
            if ver_analise:
                with st.chat_message("assistant"):
                    st.markdown(f"**Análise Técnica do Registro #{row['id']}:**")
                    st.write(row['mapeamento_ia'])
                    if st.button("Fechar Análise", key=f"close_{row['id']}"):
                        st.rerun()

        st.write("---")
        
        # Ação em Massa
        if selecao_atual:
            if st.button(f"🔴 Excluir {len(selecao_atual)} itens selecionados", type="primary"):
                supabase.table("registros").delete().in_("id", selecao_atual).execute()
                st.success("Limpeza concluída!")
                st.rerun()
    else:
        st.info("Nenhum dado encontrado no Supabase.")

# --- ABA 3: CONFIGURAÇÕES ---
with aba_conf:
    st.subheader("⚙️ Configurações de Sistema")
    c_l, c_r = st.columns(2)
    with c_l:
        st.write("### 📁 Domínios")
        n_c = st.text_input("Nova Categoria:")
        if st.button("Add"):
            if n_c: supabase.table("categorias").insert({"nome": n_c.strip()}).execute(); st.rerun()
        for cat in carregar_categorias():
            col1, col2 = st.columns([4, 1])
            col1.text(cat['nome'])
            if col2.button("🗑️", key=f"dc_{cat['id']}"):
                supabase.table("categorias").delete().eq("id", cat['id']).execute(); st.rerun()
    with c_r:
        st.write("### 🔑 Chaves")
        n_k = st.text_input("Nova Chave:", type="password")
        if st.button("Salvar Chave"):
            if n_k.startswith("gsk_"): supabase.table("config_chaves").insert({"chave": n_k.strip()}).execute(); st.rerun()
        for k in carregar_chaves_db():
            col1, col2 = st.columns([4, 1])
            col1.text(f"Ativa: {k['chave'][:12]}...")
            if col2.button("🗑️", key=f"dk_{k['id']}"):
                supabase.table("config_chaves").delete().eq("id", k['id']).execute(); st.rerun()
