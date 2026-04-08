import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader
import re

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Minhas Atividades - FECD", page_icon="📝", layout="wide")

# --- 2. CONEXÃO SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["connections"]["supabase"]["url"]
        key = st.secrets["connections"]["supabase"]["key"]
        return create_client(url, key)
    except: return None

supabase: Client = init_connection()

# --- 3. FUNÇÕES DE SUPORTE ---
def carregar_categorias():
    res = supabase.table("categorias").select("*").order("nome").execute()
    return res.data if res.data else []

def carregar_origens():
    res = supabase.table("origens").select("*").order("nome").execute()
    return res.data if res.data else []

def carregar_perfil_base():
    res = supabase.table("perfil_contexto").select("*").limit(1).execute()
    return res.data[0] if res.data else {}

def carregar_equipe():
    res = supabase.table("equipe_organograma").select("*").execute()
    return res.data if res.data else []

def carregar_documentos():
    res = supabase.table("documentos_conhecimento").select("*").order("created_at", desc=True).execute()
    return res.data if res.data else []

def buscar_pool_chaves():
    pool = []
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if "gsk_" in k])
    res = supabase.table("config_chaves").select("*").execute()
    if res.data: pool.extend([k['chave'].strip() for k in res.data])
    return list(set(pool))

# --- 4. MOTOR DE INTELIGÊNCIA E OCR ---

def limpar_texto_ocr(texto):
    """Limpa o lixo de caracteres de PDFs escaneados."""
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'[^\w\s\d.,;:\-\(\)@]', '', texto)
    return texto.strip()

def extrair_texto_pdf(file):
    try:
        reader = PdfReader(file)
        texto = ""
        for page in reader.pages:
            content = page.extract_text()
            if content: texto += content + "\n"
        return limpar_texto_ocr(texto)
    except: return "Erro no processamento do arquivo."

def analisar_documento_estrategico(texto_pdf):
    """IA transforma a massa de texto em tópicos de gestão FECD."""
    chaves = buscar_pool_chaves()
    if not chaves: return "Documento processado. IA offline para análise."
    
    prompt = """
    Você é um Auditor e Gestor da Fundação FECD. Analise este texto (OCR) e resuma:
    1. OBJETO: O que é este documento.
    2. REGRAS: Prazos, valores ou obrigações citadas.
    3. CONDUTA: Como o Jhonata deve agir baseado nisso.
    Seja compacto e ignore erros de leitura do OCR.
    """
    
    random.shuffle(chaves)
    for c in chaves:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {c}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-70b-versatile", "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": texto_pdf[:7000]}], "temperature": 0.1}, 
                timeout=20)
            if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        except: continue
    return "Documento salvo, mas análise de IA falhou."

def analisar_processo_ia(texto, categoria, origem, complexidade):
    chaves = buscar_pool_chaves()
    perfil = carregar_perfil_base()
    equipe = carregar_equipe()
    docs = carregar_documentos()
    
    ctx_equipe = "\n".join([f"- {m['nome']} ({m['cargo']}) | E-mail: {m['email']}" for m in equipe])
    ctx_doc = "\n".join([f"DOC: {d['titulo']}\nIA: {d['resumo_ia']}" for d in docs[:2]])
    
    prompt = f"Assistente de {perfil.get('nome_profissional', 'Jhonata')}. CONTEXTO FECD:\n{ctx_equipe}\nBASE TÉCNICA:\n{ctx_doc}\nAnalise: {texto}"
    
    random.shuffle(chaves)
    for c in chaves:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {c}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}, timeout=15)
            if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        except: continue
    return "IA Offline."

# --- 5. INTERFACE ---
tab_reg, tab_pan, tab_perf, tab_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama (CRUD)", "🏢 Perfil & Contexto", "⚙️ Configurações"])

# ABA 1: MAPEAMENTO
with tab_reg:
    with st.form("f_reg", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data:", value=datetime.date.today())
        ct = c2.selectbox("Domínio:", [x['nome'] for x in carregar_categorias()] or ["Geral"])
        og = c3.selectbox("Origem:", [x['nome'] for x in carregar_origens()] or ["E-mail"])
        cp = st.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        ds = st.text_area("Descrição da Demanda:")
        if st.form_submit_button("🚀 Sincronizar"):
            if ds:
                with st.spinner("IA analisando..."):
                    ana = analisar_processo_ia(ds, ct, og, cp)
                    supabase.table("registros").insert({"data": dt.strftime("%Y-%m-%d"), "dominio": ct, "origem": og, "complexidade": cp, "descricao": ds, "mapeamento_ia": ana}).execute()
                    st.success("Sincronizado!"); st.rerun()

# ABA 2: PANORAMA (CRUD)
with tab_pan:
    st.subheader("📊 Gestão de Atividades")
    res = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        st.write("---")
        h = st.columns([0.4, 0.6, 1.0, 1.2, 1.2, 0.8, 3.0, 0.6, 0.6])
        for i, t in enumerate(["Sel.", "ID", "Data", "Domínio", "Origem", "Comp.", "Descrição", "Edit", "Ver"]): h[i].write(f"**{t}**")
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
                    if st.form_submit_button("Salvar"):
                        supabase.table("registros").update({"descricao": nd}).eq("id", row['id']).execute()
                        st.session_state[f"ed_{row['id']}"] = False; st.rerun()
        if selecionados and st.button("🔴 Excluir Itens"):
            supabase.table("registros").delete().in_("id", selecionados).execute(); st.rerun()

# ABA 3: PERFIL E CONHECIMENTO
with tab_perf:
    sub_p, sub_c = st.tabs(["🏢 Perfil & Equipe", "📄 Catálogo de Inteligência"])
    
    with sub_p:
        perfil = carregar_perfil_base(); equipe = carregar_equipe()
        cl, cr = st.columns([1, 1.3])
        with cl:
            with st.expander("👤 Perfil Profissional", expanded=True):
                with st.form("f_p"):
                    np = st.text_input("Nome:", value=perfil.get('nome_professional', ''))
                    cg = st.text_input("Cargo:", value=perfil.get('cargo', ''))
                    mt = st.text_area("Metas:", value=perfil.get('metas_estrategicas', ''))
                    if st.form_submit_button("Salvar Perfil"):
                        supabase.table("perfil_contexto").upsert({"id": 1, "nome_profissional": np, "cargo": cg, "metas_estrategicas": mt}).execute(); st.rerun()
            st.write("### 👥 Gestão de Equipe")
            with st.form("f_eq", clear_on_submit=True):
                en = st.text_input("Nome:"); ec = st.text_input("Cargo:"); ee = st.text_input("E-mail:")
                ep = st.selectbox("Posição:", ["Superior", "Mesmo Nível (Par)", "Subordinado", "Prestador de Serviço"])
                if st.form_submit_button("Adicionar"):
                    supabase.table("equipe_organograma").insert({"nome": en, "cargo": ec, "email": ee, "posicao": ep}).execute(); st.rerun()
        with cr:
            st.write("### 🌲 Organograma")
            def card(n, c, e, col, stl="solid"):
                st.markdown(f'<div style="border:1px {stl} #ddd; border-radius:10px; padding:10px; margin-bottom:5px; background:{col}; border-left:5px {stl} #ff4b4b;"><b>{n.upper()}</b><br><small>{c} - {e}</small></div>', unsafe_allow_html=True)
            for m in [x for x in equipe if x['posicao'] == "Superior"]: card(m['nome'], m['cargo'], m['email'], "#eef7fa")
            card(perfil.get('nome_profissional', 'Você'), perfil.get('cargo', 'Cargo'), "Seu E-mail", "#fff4f4")
            for m in [x for x in equipe if x['posicao'] == "Subordinado"]: card(m['nome'], m['cargo'], m['email'], "#f1fff1")
            for m in [x for x in equipe if x['posicao'] == "Prestador de Serviço"]: card(m['nome'], m['cargo'], m['email'], "#f8f9fa", "dashed")

    with sub_c:
        st.subheader("📚 Base de Conhecimento Técnica")
        with st.expander("➕ Integrar Novo Documento (Com OCR Inteligente)"):
            up = st.file_uploader("Subir PDF:", type="pdf")
            if up and st.button("Processar e Analisar com IA"):
                with st.spinner("Extraindo e Analisando conteúdo..."):
                    texto_bruto = extrair_texto_pdf(up)
                    analise_ia = analisar_documento_estrategico(texto_bruto)
                    try:
                        # CORREÇÃO DO ERRO DE API: Garante que as colunas existam no banco
                        supabase.table("documentos_conhecimento").insert({
                            "titulo": up.name, 
                            "resumo_ia": analise_ia, 
                            "conteudo_completo": texto_bruto[:10000] # Limite para evitar erro de payload
                        }).execute()
                        st.success("Documento absorvido pela IA!"); st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar no banco: Certifique-se de que as colunas 'resumo_ia' e 'conteudo_completo' existem na tabela. Detalhe: {e}")

        # DATABASE COMPACTA
        docs = carregar_documentos()
        if docs:
            st.write("---")
            for d in docs:
                with st.container():
                    col_info, col_del = st.columns([5, 1])
                    with col_info:
                        st.markdown(f"**📄 {d['titulo']}**")
                        with st.expander("🔍 Ver Entendimento da IA"):
                            st.info(d.get('resumo_ia', 'Sem análise disponível.'))
                    if col_del.button("🗑️", key=f"del_doc_{d['id']}"):
                        supabase.table("documentos_conhecimento").delete().eq("id", d['id']).execute(); st.rerun()
                    st.divider()

# ABA 4: CONFIGURAÇÕES
with tab_conf:
    c1, c2, c3 = st.columns(3)
    with c1:
        nc = st.text_input("Nova Cat:"); 
        if st.button("Add Cat") and nc: supabase.table("categorias").insert({"nome": nc}).execute(); st.rerun()
    with c2:
        no = st.text_input("Nova Ori:");
        if st.button("Add Ori") and no: supabase.table("origens").insert({"nome": no}).execute(); st.rerun()
    with c3:
        nk = st.text_input("Groq Key:", type="password")
        if st.button("Salvar Chave") and nk: supabase.table("config_chaves").insert({"chave": nk}).execute(); st.rerun()
