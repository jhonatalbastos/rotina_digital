import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Minhas Atividades - FECD", page_icon="📝", layout="wide")

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

def carregar_origens():
    try:
        res = supabase.table("origens").select("*").order("nome").execute()
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

def analisar_processo_ia(texto, categoria, origem, complexidade):
    chaves = buscar_pool_chaves_total()
    if not chaves: return "⚠️ Sem chaves no sistema.", texto
    
    # NOVO PROMPT FOCO EM CATALOGAÇÃO E MAPEAMENTO
    system_prompt = (
        "Você é um Analista de Processos Sênior especializado em Gestão Pública e Terceiro Setor. "
        "Sua tarefa NÃO é responder mensagens, mas sim ANALISAR E CATALOGAR a atividade descrita. "
        "Estruture sua resposta em: "
        "1. RESUMO EXECUTIVO: O que foi feito/solicitado. "
        "2. TAREFAS IDENTIFICADAS: Liste as subtarefas técnicas (contábeis, financeiras ou legais). "
        "3. IMPACTO NO PROCESSO: Como isso afeta o fluxo da fundação. "
        "4. SUGESTÃO DE PADRONIZAÇÃO: Se houver, sugira como automatizar ou otimizar essa demanda específica. "
        "Mantenha um tom técnico, profissional e focado em mapeamento de carga de trabalho."
    )
    
    random.shuffle(chaves)
    for chave in chaves:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {chave.strip()}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"ENTRADA PARA ANÁLISE:\nCategoria: {categoria}\nOrigem: {origem}\nTexto: {texto}"}
                    ],
                    "temperature": 0.1 # Menor criatividade para ser mais preciso
                }, timeout=20
            )
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'], texto
        except: continue
    return "❌ Falha na IA.", texto

# --- INTERFACE ---
st.title("📝 Minhas Atividades - FECD")

if not supabase: st.stop()

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama (CRUD)", "⚙️ Configurações"])

# --- ABA 1: MAPEAMENTO ---
with aba_reg:
    with st.form("form_create", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_f = c1.date_input("Data:", value=datetime.date.today())
        
        cats = carregar_categorias()
        nomes_cat = [c['nome'] for c in cats] if cats else ["Financeiro", "Auditoria"]
        cat_f = c2.selectbox("Categoria:", nomes_cat)
        
        origs = carregar_origens()
        nomes_orig = [o['nome'] for o in origs] if origs else ["E-mail", "WhatsApp", "Reunião"]
        origem_f = c3.selectbox("Origem:", nomes_orig)
        
        comp_f = st.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        desc_f = st.text_area("Descrição detalhada da Atividade (Copie e cole e-mails ou logs aqui):")
        
        if st.form_submit_button("Sincronizar com Nuvem"):
            if desc_f:
                with st.spinner("Mapeando Atividade via IA..."):
                    analise, texto_final = analisar_processo_ia(desc_f, cat_f, origem_f, comp_f)
                    supabase.table("registros").insert({
                        "data": data_f.strftime("%Y-%m-%d"), "dominio": cat_f, "origem": origem_f,
                        "complexidade": comp_f, "descricao": texto_final, "mapeamento_ia": analise
                    }).execute()
                    st.success("✅ Atividade catalogada com sucesso!")
                    st.rerun()

# --- ABA 2: PANORAMA (CRUD) ---
with aba_dash:
    st.subheader("📊 Gestão de Atividades")
    res = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        if st.button("🔄 Atualizar Dados"): st.rerun()
        
        st.write("---")
        h = st.columns([0.5, 0.8, 1.2, 1.5, 1.5, 1, 3, 0.8, 0.8])
        h[0].write("**Sel.**")
        h[1].write("**ID**")
        h[2].write("**Data**")
        h[3].write("**Categoria**")
        h[4].write("**Origem**")
        h[5].write("**Comp.**")
        h[6].write("**Descrição**")
        h[7].write("**Edit**")
        h[8].write("**Ver**")

        selecao_atual = []
        list_cats = [c['nome'] for c in carregar_categorias()]
        list_origs = [o['nome'] for o in carregar_origens()]

        for _, row in df.iterrows():
            c = st.columns([0.5, 0.8, 1.2, 1.5, 1.5, 1, 3, 0.8, 0.8])
            if c[0].checkbox("", key=f"sel_{row['id']}"): selecao_atual.append(row['id'])
            c[1].write(row['id'])
            c[2].write(row['data'])
            
            cat_val = row.get('dominio', 'N/A')
            c[3].write(cat_val)
            
            orig_val = row.get('origem', 'N/A')
            c[4].write(orig_val if orig_val else "⚠️ S/ Origem")
            
            c[5].write(row['complexidade'])
            c[6].write(row['descricao'][:70] + "...")
            
            if c[7].button("📝", key=f"edit_{row['id']}"): st.session_state[f"editing_{row['id']}"] = True
            ver_analise = c[8].button("🔍", key=f"view_{row['id']}")

            if st.session_state.get(f"editing_{row['id']}", False):
                with st.expander(f"✏️ Editar Atividade #{row['id']}", expanded=True):
                    with st.form(f"f_edit_{row['id']}"):
                        col_ed_top1, col_ed_top2 = st.columns(2)
                        idx_cat = list_cats.index(cat_val) if cat_val in list_cats else 0
                        ed_cat = col_ed_top1.selectbox("Nova Categoria", list_cats, index=idx_cat)
                        idx_orig = list_origs.index(orig_val) if orig_val in list_origs else 0
                        ed_orig = col_ed_top2.selectbox("Nova Origem", list_origs, index=idx_orig)
                        ed_desc = st.text_area("Descrição", value=row['descricao'])
                        
                        if st.form_submit_button("Atualizar Registro"):
                            supabase.table("registros").update({
                                "dominio": ed_cat, "origem": ed_orig, "descricao": ed_desc
                            }).eq("id", row['id']).execute()
                            st.session_state[f"editing_{row['id']}"] = False
                            st.rerun()
                        if st.form_submit_button("Cancelar"):
                            st.session_state[f"editing_{row['id']}"] = False
                            st.rerun()

            if ver_analise:
                with st.chat_message("assistant"):
                    st.markdown(f"**🔍 Análise Técnica da Atividade #{row['id']}:**")
                    st.write(row['mapeamento_ia'])
                    if st.button("Fechar", key=f"close_{row['id']}"): st.rerun()

        if selecao_atual:
            if st.button(f"🔴 Excluir {len(selecao_atual)} itens", type="primary"):
                supabase.table("registros").delete().in_("id", selecao_atual).execute()
                st.rerun()
    else:
        st.info("Nenhuma atividade registrada.")

# --- ABA 3: CONFIGURAÇÕES ---
with aba_conf:
    st.subheader("⚙️ Configurações FECD")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.write("### 📁 Categorias")
        n_c = st.text_input("Nova Categoria:")
        if st.button("Add Categoria"):
            if n_c: supabase.table("categorias").insert({"nome": n_c.strip()}).execute(); st.rerun()
        for cat in carregar_categorias():
            col1, col2 = st.columns([4, 1])
            col1.text(cat['nome'])
            if col2.button("🗑️", key=f"dc_{cat['id']}"): supabase.table("categorias").delete().eq("id", cat['id']).execute(); st.rerun()

    with c2:
        st.write("### 📍 Origens")
        n_o = st.text_input("Nova Origem:")
        if st.button("Add Origem"):
            if n_o: supabase.table("origens").insert({"nome": n_o.strip()}).execute(); st.rerun()
        for ori in carregar_origens():
            col1, col2 = st.columns([4, 1])
            col1.text(ori['nome'])
            if col2.button("🗑️", key=f"do_{ori['id']}"): supabase.table("origens").delete().eq("id", ori['id']).execute(); st.rerun()

    with c3:
        st.write("### 🔑 Chaves Groq")
        n_k = st.text_input("Nova Chave:", type="password")
        if st.button("Salvar Chave"):
            if n_k.startswith("gsk_"): supabase.table("config_chaves").insert({"chave": n_k.strip()}).execute(); st.rerun()
        for k in carregar_chaves_db():
            col1, col2 = st.columns([4, 1])
            col1.text(f"Key: {k['chave'][:12]}...")
            if col2.button("🗑️", key=f"dk_{k['id']}"): supabase.table("config_chaves").delete().eq("id", k['id']).execute(); st.rerun()
