import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Minhas Atividades - FECD", page_icon="📝", layout="wide")

# --- CONEXÃO COM SUPABASE ---
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

# --- FUNÇÕES DE CARREGAMENTO DE DADOS ---

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

def carregar_perfil_base():
    try:
        res = supabase.table("perfil_contexto").select("*").limit(1).execute()
        return res.data[0] if res.data else {}
    except: return {}

def carregar_equipe():
    try:
        res = supabase.table("equipe_organograma").select("*").execute()
        return res.data if res.data else []
    except: return []

def carregar_documentos():
    try:
        res = supabase.table("documentos_conhecimento").select("*").order("created_at", desc=True).execute()
        return res.data if res.data else []
    except: return []

def carregar_chaves_db():
    try:
        res = supabase.table("config_chaves").select("*").execute()
        return res.data if res.data else []
    except: return []

def buscar_pool_chaves():
    pool = []
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if "gsk_" in k])
    db_keys = carregar_chaves_db()
    if db_keys:
        pool.extend([k['chave'].strip() for k in db_keys if "gsk_" in k['chave']])
    return list(set(pool))

# --- MOTOR DE INTELIGÊNCIA ---

def extrair_texto_pdf(file):
    try:
        reader = PdfReader(file)
        texto = ""
        for page in reader.pages:
            texto += page.extract_text()
        return texto
    except: return "Erro ao extrair texto do PDF."

def analisar_processo_ia(texto, categoria, origem, complexidade):
    chaves = buscar_pool_chaves()
    if not chaves: return "⚠️ Nenhuma chave Groq configurada."
    
    perfil = carregar_perfil_base()
    equipe = carregar_equipe()
    docs = carregar_documentos()
    
    # Contextualização avançada: Identifica quem enviou se o e-mail estiver na base
    ctx_equipe = "\n".join([f"- {m['nome']} ({m['cargo']}) | E-mail: {m['email']} | Papel: {m['posicao']}" for m in equipe])
    ctx_doc = "\n".join([f"- {d['titulo']}: {d['resumo_ia']}" for d in docs[:2]])
    
    prompt = f"""
    Você é o Assistente Estratégico de {perfil.get('nome_profissional', 'Jhonata Leal Bastos')}, {perfil.get('cargo', 'Gerente Financeiro e Contador')}.
    Contexto FECD: {perfil.get('certificacoes', 'Auditor QTG')}.
    Mapeamento de Equipe (Use para identificar remetentes): {ctx_equipe}.
    Base Técnica: {ctx_doc}.
    
    Sua missão: Analisar a atividade, identificar se o remetente é um superior ou parceiro e sugerir a melhor abordagem técnica e produtiva (GTD).
    Atividade: {texto}
    """
    
    random.shuffle(chaves)
    for c in chaves:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {c}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": texto}], "temperature": 0.1}, timeout=15)
            if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        except: continue
    return "❌ Falha na conexão com a IA."

# --- INTERFACE STREAMLIT ---

if not supabase:
    st.error("Erro: Conexão com Supabase não estabelecida.")
    st.stop()

tab_reg, tab_pan, tab_perf, tab_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama (CRUD)", "🏢 Perfil & Organograma", "⚙️ Configurações"])

# --- ABA 1: MAPEAMENTO ---
with tab_reg:
    with st.form("form_registro", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        data_f = col1.date_input("Data da Atividade:", value=datetime.date.today())
        
        lista_cats = [c['nome'] for c in carregar_categorias()]
        cat_f = col2.selectbox("Domínio/Categoria:", lista_cats if lista_cats else ["Financeiro"])
        
        lista_origs = [o['nome'] for o in carregar_origens()]
        orig_f = col3.selectbox("Origem da Demanda:", lista_origs if lista_origs else ["E-mail"])
        
        comp_f = st.select_slider("Nível de Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        desc_f = st.text_area("Descreva a atividade ou cole o e-mail recebido:")
        
        if st.form_submit_button("🚀 Sincronizar com Inteligência Cloud"):
            if desc_f:
                with st.spinner("IA processando seu contexto profissional..."):
                    analise = analisar_processo_ia(desc_f, cat_f, orig_f, comp_f)
                    supabase.table("registros").insert({
                        "data": data_f.strftime("%Y-%m-%d"), "dominio": cat_f, "origem": orig_f,
                        "complexidade": comp_f, "descricao": desc_f, "mapeamento_ia": analise
                    }).execute()
                    st.success("Atividade mapeada e salva com sucesso!")
                    st.rerun()

# --- ABA 2: PANORAMA (CRUD COMPLETO) ---
with tab_pan:
    st.subheader("📊 Gestão de Atividades Mapeadas")
    res_atividades = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    
    if res_atividades.data:
        df = pd.DataFrame(res_atividades.data)
        
        c_refresh, c_del = st.columns([1, 6])
        if c_refresh.button("🔄 Atualizar"): st.rerun()
        
        st.write("---")
        h = st.columns([0.4, 0.6, 1.0, 1.2, 1.2, 0.8, 3.0, 0.6, 0.6])
        titulos = ["Sel.", "ID", "Data", "Domínio", "Origem", "Comp.", "Descrição", "Edit", "Ver"]
        for i, t in enumerate(titulos): h[i].write(f"**{t}**")

        selecionados = []
        for _, row in df.iterrows():
            c = st.columns([0.4, 0.6, 1.0, 1.2, 1.2, 0.8, 3.0, 0.6, 0.6])
            if c[0].checkbox("", key=f"sel_{row['id']}"): selecionados.append(row['id'])
            c[1].write(row['id'])
            c[2].write(row['data'])
            c[3].write(row.get('dominio', 'N/A'))
            c[4].write(row.get('origem', 'N/A'))
            c[5].write(row['complexidade'])
            c[6].write(row['descricao'][:75] + "...")
            
            if c[7].button("📝", key=f"btn_ed_{row['id']}"): st.session_state[f"edit_mode_{row['id']}"] = True
            if c[8].button("🔍", key=f"btn_vw_{row['id']}"): st.info(row['mapeamento_ia'])

            if st.session_state.get(f"edit_mode_{row['id']}", False):
                with st.expander(f"Editar Atividade #{row['id']}", expanded=True):
                    with st.form(f"form_ed_{row['id']}"):
                        nova_desc = st.text_area("Descrição", value=row['descricao'])
                        col_bt1, col_bt2 = st.columns(2)
                        if col_bt1.form_submit_button("Confirmar Alteração"):
                            supabase.table("registros").update({"descricao": nova_desc}).eq("id", row['id']).execute()
                            st.session_state[f"edit_mode_{row['id']}"] = False
                            st.rerun()
                        if col_bt2.form_submit_button("Cancelar"):
                            st.session_state[f"edit_mode_{row['id']}"] = False
                            st.rerun()
        
        if selecionados:
            if st.button(f"🔴 Excluir {len(selecionados)} itens selecionados"):
                supabase.table("registros").delete().in_("id", selecionados).execute()
                st.rerun()
    else:
        st.info("Nenhuma atividade registrada ainda.")

# --- ABA 3: PERFIL & ORGANOGRAMA ---
with tab_perf:
    st.subheader("🏢 Perfil Institucional & Estrutura de Equipe")
    perfil = carregar_perfil_base()
    equipe = carregar_equipe()
    
    col_cad, col_vis = st.columns([1, 1.3])
    
    with col_cad:
        with st.expander("👤 Meu Perfil Profissional", expanded=True):
            with st.form("form_meu_perfil"):
                n_p = st.text_input("Nome Completo:", value=perfil.get('nome_profissional', ''))
                c_p = st.text_input("Cargo Atual:", value=perfil.get('cargo', ''))
                cert_p = st.text_area("Certificações Técnicas:", value=perfil.get('certificacoes', ''))
                meta_p = st.text_area("Metas Estratégicas:", value=perfil.get('metas_estrategicas', ''))
                if st.form_submit_button("Salvar Meu Perfil"):
                    supabase.table("perfil_contexto").upsert({
                        "id": 1, "nome_profissional": n_p, "cargo": c_p, 
                        "certificacoes": cert_p, "metas_estrategicas": meta_p
                    }).execute()
                    st.success("Perfil atualizado!"); st.rerun()

        st.write("### 👥 Adicionar Membro à Equipe")
        with st.form("form_add_equipe", clear_on_submit=True):
            nm = st.text_input("Nome:"); cg = st.text_input("Cargo:"); em = st.text_input("E-mail:")
            ps = st.selectbox("Posição Hierárquica:", ["Superior", "Mesmo Nível (Par)", "Subordinado", "Prestador de Serviço"])
            if st.form_submit_button("Adicionar Membro"):
                if nm and cg:
                    supabase.table("equipe_organograma").insert({"nome": nm, "cargo": cg, "email": em, "posicao": ps}).execute()
                    st.rerun()

        if equipe:
            with st.expander("🗑️ Gerenciar Equipe"):
                for m in equipe:
                    c1, c2 = st.columns([4, 1])
                    c1.write(f"**{m['nome']}** - {m['posicao']}")
                    if c2.button("Remover", key=f"del_mem_{m['id']}"):
                        supabase.table("equipe_organograma").delete().eq("id", m['id']).execute()
                        st.rerun()

    with col_vis:
        st.write("### 🌲 Organograma Dinâmico")
        def card(n, c, e, color, border_style="solid"):
            st.markdown(f'''
                <div style="border:1px {border_style} #ddd; border-radius:10px; padding:15px; margin-bottom:10px; background:{color}; border-left:6px {border_style} #ff4b4b;">
                    <b>{n.upper()}</b><br>
                    <small>{c}</small><br>
                    <code style="font-size:0.8em; color:#0068c9;">{e}</code>
                </div>
            ''', unsafe_allow_html=True)

        sups = [m for m in equipe if m['posicao'] == "Superior"]
        if sups:
            st.caption("⬆️ Liderança / Superior")
            for s in sups: card(s['nome'], s['cargo'], s['email'], "#eef7fa")
            st.write("↓")
        
        st.caption("📍 Posição Atual")
        card(perfil.get('nome_profissional', 'Você'), perfil.get('cargo', 'Seu Cargo'), "Seu E-mail", "#fff4f4")
        
        subs = [m for m in equipe if m['posicao'] == "Subordinado"]
        pares = [m for m in equipe if m['posicao'] == "Mesmo Nível (Par)"]
        
        if pares:
            st.caption("↔️ Colegas / Mesmo Nível")
            for p in pares: card(p['nome'], p['cargo'], p['email'], "#ffffff")

        if subs:
            st.write("↓"); st.caption("⬇️ Subordinados / Apoio")
            cols = st.columns(len(subs))
            for i, s in enumerate(subs):
                with cols[i]: card(s['nome'], s['cargo'], s['email'], "#f1fff1")

        prests = [m for m in equipe if m['posicao'] == "Prestador de Serviço"]
        if prests:
            st.write("---")
            st.caption("🤝 Parceiros / Prestadores de Serviço")
            for pr in prests: card(pr['nome'], pr['cargo'], pr['email'], "#f8f9fa", border_style="dashed")

    st.write("---")
    with st.expander("📄 Base de Conhecimento (Upload de PDFs)"):
        pdf_file = st.file_uploader("Subir PDF Técnico:", type="pdf")
        if pdf_file and st.button("Integrar PDF à Inteligência"):
            with st.spinner("Extraindo dados..."):
                texto = extrair_texto_pdf(pdf_file)
                supabase.table("documentos_conhecimento").insert({"titulo": pdf_file.name, "resumo_ia": texto[:3000], "tipo": "Normativo"}).execute()
                st.success("Documento integrado!"); st.rerun()

# --- ABA 4: CONFIGURAÇÕES ---
with tab_conf:
    st.subheader("⚙️ Painel de Controle FECD")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.write("### 📁 Categorias")
        nova_cat = st.text_input("Nova Categoria:")
        if st.button("Salvar Categoria") and nova_cat:
            supabase.table("categorias").insert({"nome": nova_cat.strip()}).execute(); st.rerun()
        for x in carregar_categorias():
            st.caption(f"• {x['nome']}")

    with c2:
        st.write("### 📍 Origens")
        nova_ori = st.text_input("Nova Origem:")
        if st.button("Salvar Origem") and nova_ori:
            supabase.table("origens").insert({"nome": nova_ori.strip()}).execute(); st.rerun()
        for x in carregar_origens():
            st.caption(f"• {x['nome']}")

    with c3:
        st.write("### 🔑 Chaves Groq")
        nova_key = st.text_input("Nova API Key:", type="password")
        if st.button("Salvar Chave") and nova_key.startswith("gsk_"):
            supabase.table("config_chaves").insert({"chave": nova_key.strip()}).execute(); st.rerun()
        for k in carregar_chaves_db():
            st.text(f"Ativa: {k['chave'][:12]}...")
