import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader

# --- 1. CONFIGURAÇÕES INICIAIS DA PÁGINA ---
st.set_page_config(
    page_title="Minhas Atividades - FECD",
    page_icon="📝",
    layout="wide"
)

# --- 2. CONEXÃO COM O BANCO DE DADOS (SUPABASE) ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["connections"]["supabase"]["url"]
        key = st.secrets["connections"]["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None

supabase: Client = init_connection()

# --- 3. FUNÇÕES DE SUPORTE E CARREGAMENTO ---

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
    except: return []

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

# --- 4. MOTOR DE INTELIGÊNCIA ARTIFICIAL ---

def extrair_texto_pdf(file):
    try:
        reader = PdfReader(file)
        texto = ""
        for page in reader.pages:
            texto += page.extract_text()
        return texto
    except: return "Erro ao extrair texto do PDF."

def gerar_feedback_documento(texto_pdf):
    """Gera um resumo da IA para confirmar a leitura do documento técnico."""
    chaves = buscar_pool_chaves()
    if not chaves: return "Documento salvo. IA indisponível para resumo imediato."
    
    prompt = "Resuma este documento técnico da Fundação em 3 pontos chave para a gestão contábil. Seja direto."
    
    random.shuffle(chaves)
    for c in chaves:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {c}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": f"{prompt}\n\n{texto_pdf[:3000]}"}], "temperature": 0.1}, 
                timeout=15)
            if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        except: continue
    return "Documento integrado com sucesso."

def analisar_processo_ia(texto, categoria, origem, complexidade):
    chaves = buscar_pool_chaves()
    if not chaves: return "⚠️ Nenhuma chave Groq configurada."
    
    perfil = carregar_perfil_base()
    equipe = carregar_equipe()
    docs = carregar_documentos()
    
    ctx_equipe = "\n".join([f"- {m['nome']} ({m['cargo']}) | E-mail: {m['email']} | Posição: {m['posicao']}" for m in equipe])
    ctx_doc = "\n".join([f"- {d['titulo']}: {d['resumo_ia'][:800]}" for d in docs[:3]])
    
    prompt = f"""
    Você é o Assistente Estratégico de {perfil.get('nome_profissional', 'Jhonata Leal Bastos')}, {perfil.get('cargo', 'Gerente Financeiro e Contador')}.
    Metas: {perfil.get('metas_estrategicas', 'Trabalho híbrido')}.
    ESTRUTURA FECD: {ctx_equipe}
    CONHECIMENTO TÉCNICO: {ctx_doc}
    
    Missão: Analise a demanda, identifique o impacto e sugira a melhor conduta técnica e produtiva.
    Demanda: {texto}
    """
    
    random.shuffle(chaves)
    for c in chaves:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {c}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": texto}], "temperature": 0.1}, 
                timeout=15)
            if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        except: continue
    return "❌ Erro na IA."

# --- 5. INTERFACE DO USUÁRIO ---

if not supabase: st.stop()

tab_reg, tab_pan, tab_perf, tab_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama (CRUD)", "🏢 Perfil & Contexto", "⚙️ Configurações"])

# ABA 1: REGISTRO
with tab_reg:
    with st.form("form_registro", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        dt = col1.date_input("Data:", value=datetime.date.today())
        cat = col2.selectbox("Domínio:", [c['nome'] for c in carregar_categorias()] or ["Financeiro"])
        ori = col3.selectbox("Origem:", [o['nome'] for o in carregar_origens()] or ["E-mail"])
        cp = st.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        ds = st.text_area("Descreva a demanda profissional:")
        if st.form_submit_button("🚀 Sincronizar com Inteligência Cloud"):
            if ds:
                with st.spinner("IA analisando contexto..."):
                    ana = analisar_processo_ia(ds, cat, ori, cp)
                    supabase.table("registros").insert({"data": dt.strftime("%Y-%m-%d"), "dominio": cat, "origem": ori, "complexidade": cp, "descricao": ds, "mapeamento_ia": ana}).execute()
                    st.success("Atividade mapeada!"); st.rerun()

# ABA 2: PANORAMA (CRUD)
with tab_pan:
    st.subheader("📊 Gestão de Atividades Mapeadas")
    res_atv = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    if res_atv.data:
        df = pd.DataFrame(res_atv.data)
        st.write("---")
        h = st.columns([0.4, 0.6, 1.0, 1.2, 1.2, 0.8, 3.0, 0.6, 0.6])
        titulos = ["Sel.", "ID", "Data", "Domínio", "Origem", "Comp.", "Descrição", "Edit", "Ver"]
        for i, t in enumerate(titulos): h[i].write(f"**{t}**")
        selecionados = []
        for _, row in df.iterrows():
            c = st.columns([0.4, 0.6, 1.0, 1.2, 1.2, 0.8, 3.0, 0.6, 0.6])
            if c[0].checkbox("", key=f"s_{row['id']}"): selecionados.append(row['id'])
            c[1].write(row['id']); c[2].write(row['data']); c[3].write(row.get('dominio','')); c[4].write(row.get('origem','')); c[5].write(row['complexidade']); c[6].write(row['descricao'][:65]+"...")
            if c[7].button("📝", key=f"e_{row['id']}"): st.session_state[f"ed_{row['id']}"] = True
            if c[8].button("🔍", key=f"v_{row['id']}"): st.info(row['mapeamento_ia'])
            if st.session_state.get(f"ed_{row['id']}", False):
                with st.form(f"f_ed_{row['id']}"):
                    nd = st.text_area("Descrição:", value=row['descricao'])
                    if st.form_submit_button("Confirmar"):
                        supabase.table("registros").update({"descricao": nd}).eq("id", row['id']).execute()
                        st.session_state[f"ed_{row['id']}"] = False; st.rerun()
        if selecionados and st.button("🔴 Excluir Selecionados"):
            supabase.table("registros").delete().in_("id", selecionados).execute(); st.rerun()

# ABA 3: PERFIL & CONTEXTO (ESTRUTURA COMPLETA)
with tab_perf:
    sub_perf, sub_base = st.tabs(["🏢 Perfil & Equipe", "📄 Relatório de Conhecimento"])
    
    with sub_perf:
        perfil = carregar_perfil_base(); equipe = carregar_equipe()
        c_cad, c_vis = st.columns([1, 1.3])
        with c_cad:
            with st.expander("👤 Meu Perfil Profissional", expanded=True):
                with st.form("f_p"):
                    np = st.text_input("Nome Profissional:", value=perfil.get('nome_profissional', ''))
                    cg = st.text_input("Cargo:", value=perfil.get('cargo', ''))
                    mt = st.text_area("Metas Estratégicas:", value=perfil.get('metas_estrategicas', ''))
                    if st.form_submit_button("Atualizar Perfil"):
                        supabase.table("perfil_contexto").upsert({"id": 1, "nome_profissional": np, "cargo": cg, "metas_estrategicas": mt}).execute(); st.rerun()
            st.write("### 👥 Gestão de Equipe")
            with st.form("f_eq", clear_on_submit=True):
                en = st.text_input("Nome:"); ec = st.text_input("Cargo:"); ee = st.text_input("E-mail:")
                ep = st.selectbox("Posição:", ["Superior", "Mesmo Nível (Par)", "Subordinado", "Prestador de Serviço"])
                if st.form_submit_button("Adicionar"):
                    supabase.table("equipe_organograma").insert({"nome": en, "cargo": ec, "email": ee, "posicao": ep}).execute(); st.rerun()
        with c_vis:
            st.write("### 🌲 Organograma Dinâmico")
            def card(n, c, e, col, stl="solid"):
                st.markdown(f'<div style="border:1px {stl} #ddd; border-radius:10px; padding:12px; margin-bottom:8px; background:{col}; border-left:6px {stl} #ff4b4b;"><b>{n.upper()}</b><br><small>{c}</small><br><code>{e}</code></div>', unsafe_allow_html=True)
            for m in [x for x in equipe if x['posicao'] == "Superior"]: card(m['nome'], m['cargo'], m['email'], "#eef7fa")
            card(perfil.get('nome_profissional', 'Você'), perfil.get('cargo', 'Cargo'), "E-mail Principal", "#fff4f4")
            for m in [x for x in equipe if x['posicao'] == "Subordinado"]: card(m['nome'], m['cargo'], m['email'], "#f1fff1")
            for m in [x for x in equipe if x['posicao'] == "Prestador de Serviço"]: card(m['nome'], m['cargo'], m['email'], "#f8f9fa", "dashed")

    with sub_base:
        st.subheader("📚 Database de Conhecimento Catalogado")
        docs = carregar_documentos()
        
        # Área de Upload
        with st.expander("🆕 Integrar Novo Documento Técnico"):
            up_f = st.file_uploader("Selecione o PDF (Estatutos, Normas, Atas):", type="pdf")
            if up_f and st.button("🚀 Processar e Absorver"):
                with st.spinner("IA extraindo entendimentos..."):
                    txt = extrair_texto_pdf(up_f)
                    feed = gerar_feedback_documento(txt)
                    supabase.table("documentos_conhecimento").insert({"titulo": up_f.name, "resumo_ia": feed, "conteudo_completo": txt[:5000]}).execute()
                    st.success("Documento absorvido!"); st.rerun()

        # Visualização da Database
        if docs:
            df_docs = pd.DataFrame(docs)
            st.write("---")
            st.caption(f"Total de documentos na base: {len(docs)}")
            
            for d in docs:
                with st.container():
                    c1, c2 = st.columns([3, 1])
                    c1.markdown(f"#### 📄 {d['titulo']}")
                    c1.markdown(f"**Entendimento da IA:**\n{d['resumo_ia']}")
                    
                    if c2.button("🗑️ Remover Conhecimento", key=f"del_doc_{d['id']}"):
                        supabase.table("documentos_conhecimento").delete().eq("id", d['id']).execute(); st.rerun()
                    st.write("---")
        else:
            st.info("A base de conhecimento está vazia. Suba um PDF para começar.")

# ABA 4: CONFIGURAÇÕES
with tab_conf:
    c1, c2, c3 = st.columns(3)
    with c1:
        nc = st.text_input("Nova Categoria:"); 
        if st.button("Salvar Cat") and nc: supabase.table("categorias").insert({"nome": nc}).execute(); st.rerun()
        for x in carregar_categorias(): st.caption(f"• {x['nome']}")
    with c2:
        no = st.text_input("Nova Origem:");
        if st.button("Salvar Ori") and no: supabase.table("origens").insert({"nome": no}).execute(); st.rerun()
        for x in carregar_origens(): st.caption(f"• {x['nome']}")
    with c3:
        nk = st.text_input("API Key Groq:", type="password")
        if st.button("Salvar Chave") and nk.startswith("gsk_"): supabase.table("config_chaves").insert({"chave": nk}).execute(); st.rerun()
