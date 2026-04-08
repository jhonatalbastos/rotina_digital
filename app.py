import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader
import re

# --- 1. CONFIGURAÇÕES DE PÁGINA E ESTILO ---
st.set_page_config(
    page_title="Gestão FECD - Jhonata Bastos",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilo para os cards do Organograma
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 5px 5px 0px 0px;
        gap: 1px;
        padding-top: 10px;
    }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXÃO COM O BANCO DE DADOS (SUPABASE) ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["connections"]["supabase"]["url"]
        key = st.secrets["connections"]["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Erro ao conectar ao Supabase: {e}")
        return None

supabase: Client = init_connection()

# --- 3. FUNÇÕES DE BUSCA DE DADOS (READ) ---

def get_categorias():
    res = supabase.table("categorias").select("*").order("nome").execute()
    return res.data if res.data else []

def get_origens():
    res = supabase.table("origens").select("*").order("nome").execute()
    return res.data if res.data else []

def get_perfil():
    res = supabase.table("perfil_contexto").select("*").eq("id", 1).execute()
    return res.data[0] if res.data else {"nome_profissional": "Jhonata", "cargo": "Gestor"}

def get_equipe():
    res = supabase.table("equipe_organograma").select("*").execute()
    return res.data if res.data else []

def get_documentos():
    res = supabase.table("documentos_conhecimento").select("*").order("created_at", desc=True).execute()
    return res.data if res.data else []

def get_chaves_api():
    pool = []
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if "gsk_" in k])
    try:
        res = supabase.table("config_chaves").select("chave").execute()
        if res.data: pool.extend([k['chave'] for k in res.data])
    except: pass
    return list(set(pool))

# --- 4. MOTOR DE INTELIGÊNCIA E OCR (SANEAMENTO DE DADOS) ---

def sanear_ocr(texto):
    """Limpa ruídos de documentos escaneados"""
    texto = re.sub(r'OFÍCIO DE NOTAS.*?RJ', '', texto, flags=re.IGNORECASE | re.DOTALL)
    texto = re.sub(r'\.{3,}', ' ', texto)
    texto = re.sub(r'_{3,}', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def processar_pdf(file):
    try:
        reader = PdfReader(file)
        texto_acumulado = ""
        for page in reader.pages[:12]: # Processa as 12 primeiras páginas (ideal para estatutos)
            content = page.extract_text()
            if content: texto_acumulado += content + "\n"
        return sanear_ocr(texto_acumulado)
    except Exception as e:
        return f"Erro no PDF: {e}"

def analisar_com_ia(texto, tipo="documento"):
    chaves = get_chaves_api()
    if not chaves: return "Erro: Configure uma chave de API nas Configurações."
    
    # Prompt de Auditoria para Jhonata
    if tipo == "documento":
        system_prompt = "Você é um Auditor e Gestor Financeiro. Analise o estatuto/documento e extraia: 1. Objeto Social, 2. Responsabilidades de Assinatura, 3. Prazos e Vigências."
    else:
        system_prompt = "Você é o Assistente Estratégico do Jhonata. Analise a demanda e sugira a conduta técnica baseada nas normas da fundação."

    random.shuffle(chaves)
    for chave in chaves:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-specdec",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": texto[:9000]} # Proteção de limite de tokens
                    ],
                    "temperature": 0.1
                },
                timeout=25
            )
            if r.status_code == 200:
                return r.json()['choices'][0]['message']['content']
        except: continue
    return "A análise da IA falhou. Verifique sua conexão ou chaves de API."

# --- 5. INTERFACE PRINCIPAL (TABS) ---

st.title("📂 Sistema de Gestão Estratégica FECD")
if not supabase: st.stop()

tab1, tab2, tab3, tab4 = st.tabs([
    "📝 Mapear Processo", 
    "📊 Panorama (CRUD)", 
    "🏢 Perfil & Inteligência", 
    "⚙️ Configurações"
])

# --- ABA 1: MAPEAMENTO DE DEMANDAS ---
with tab1:
    with st.form("form_registro", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        data_reg = col1.date_input("Data da Demanda:", value=datetime.date.today())
        cat_reg = col2.selectbox("Domínio/Categoria:", [c['nome'] for c in get_categorias()] or ["Geral"])
        ori_reg = col3.selectbox("Origem:", [o['nome'] for o in get_origens()] or ["E-mail"])
        
        comp_reg = st.select_slider("Complexidade Técnica:", options=["Baixa", "Média", "Alta", "Crítica"])
        desc_reg = st.text_area("Descrição da Tarefa ou Conteúdo do E-mail:", height=150)
        
        if st.form_submit_button("🚀 Sincronizar e Analisar"):
            if desc_reg:
                with st.spinner("IA analisando contexto..."):
                    analise_ia = analisar_com_ia(desc_reg, tipo="processo")
                    supabase.table("registros").insert({
                        "data": data_reg.strftime("%Y-%m-%d"),
                        "dominio": cat_reg,
                        "origem": ori_reg,
                        "complexidade": comp_reg,
                        "descricao": desc_reg,
                        "mapeamento_ia": analise_ia
                    }).execute()
                    st.success("Demanda mapeada com sucesso!")
                    st.rerun()

# --- ABA 2: PANORAMA E GESTÃO (CRUD) ---
with tab2:
    st.subheader("Gestão de Atividades")
    registros = supabase.table("registros").select("*").order("created_at", desc=True).execute().data
    
    if registros:
        df = pd.DataFrame(registros)
        st.write("---")
        # Layout de tabela customizado
        h = st.columns([0.4, 0.8, 1.2, 1.5, 3.5, 0.6, 0.6])
        titulos = ["Sel.", "Data", "Domínio", "Origem", "Descrição", "Edit", "IA"]
        for i, t in enumerate(titulos): h[i].write(f"**{t}**")
        
        selecionados = []
        for _, row in df.iterrows():
            c = st.columns([0.4, 0.8, 1.2, 1.5, 3.5, 0.6, 0.6])
            if c[0].checkbox("", key=f"sel_{row['id']}"): selecionados.append(row['id'])
            c[1].write(row['data'])
            c[2].write(row.get('dominio', ''))
            c[3].write(row.get('origem', ''))
            c[4].write(row['descricao'][:80] + "...")
            
            if c[5].button("📝", key=f"ed_{row['id']}"):
                st.session_state[f"edit_mode_{row['id']}"] = True
            
            if c[6].button("🔍", key=f"ia_{row['id']}"):
                st.info(row.get('mapeamento_ia', 'Sem análise disponível.'))
            
            # Modal de Edição
            if st.session_state.get(f"edit_mode_{row['id']}", False):
                with st.form(f"form_ed_{row['id']}"):
                    nova_desc = st.text_area("Editar descrição:", value=row['descricao'])
                    if st.form_submit_button("Salvar"):
                        supabase.table("registros").update({"descricao": nova_desc}).eq("id", row['id']).execute()
                        st.session_state[f"edit_mode_{row['id']}"] = False
                        st.rerun()

        if selecionados and st.button("🗑️ Excluir Selecionados"):
            supabase.table("registros").delete().in_("id", selecionados).execute()
            st.rerun()
    else:
        st.info("Nenhum registro encontrado.")

# --- ABA 3: PERFIL & INTELIGÊNCIA INSTITUCIONAL ---
with tab3:
    col_perfil, col_conhecimento = st.columns([1, 1])
    
    with col_perfil:
        st.subheader("👤 Perfil e Equipe")
        perfil_atual = get_perfil()
        with st.expander("Dados Profissionais", expanded=True):
            with st.form("f_p"):
                n_prof = st.text_input("Nome Profissional:", value=perfil_atual.get('nome_profissional', ''))
                c_prof = st.text_input("Cargo Atual:", value=perfil_atual.get('cargo', ''))
                metas = st.text_area("Metas Estratégicas:", value=perfil_atual.get('metas_estrategicas', ''))
                if st.form_submit_button("Atualizar Perfil"):
                    supabase.table("perfil_contexto").upsert({"id": 1, "nome_profissional": n_prof, "cargo": c_prof, "metas_estrategicas": metas}).execute()
                    st.rerun()

        st.write("---")
        st.write("### 👥 Gestão de Equipe")
        with st.form("f_equipe", clear_on_submit=True):
            en = st.text_input("Nome:"); ec = st.text_input("Cargo:"); ee = st.text_input("E-mail:")
            ep = st.selectbox("Posição:", ["Superior", "Par", "Subordinado", "Consultor"])
            if st.form_submit_button("Adicionar à Equipe"):
                supabase.table("equipe_organograma").insert({"nome": en, "cargo": ec, "email": ee, "posicao": ep}).execute()
                st.rerun()
        
        # Visualização de Organograma
        equipe_lista = get_equipe()
        for m in equipe_lista:
            st.markdown(f"**{m['nome']}** - {m['cargo']} ({m['posicao']})")

    with col_conhecimento:
        st.subheader("📄 Base de Conhecimento (PDFs)")
        with st.expander("Integrar Novo PDF Técnico", expanded=True):
            arq_pdf = st.file_uploader("Selecione o Estatuto ou Ata:", type="pdf")
            if arq_pdf and st.button("Processar Inteligência 🚀"):
                with st.spinner("Extraindo e analisando com IA..."):
                    texto_limpo = processar_pdf(arq_pdf)
                    resumo_ia = analisar_com_ia(texto_limpo, tipo="documento")
                    
                    try:
                        supabase.table("documentos_conhecimento").insert({
                            "titulo": arq_pdf.name,
                            "resumo_ia": resumo_ia,
                            "conteudo_completo": texto_limpo[:8000]
                        }).execute()
                        st.success("Documento integrado à inteligência!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

        # Listagem de Conhecimento
        docs_salvos = get_documentos()
        for doc in docs_salvos:
            with st.expander(f"📄 {doc['titulo']}"):
                st.info(doc['resumo_ia'])
                if st.button("Remover", key=f"del_doc_{doc['id']}"):
                    supabase.table("documentos_conhecimento").delete().eq("id", doc['id']).execute()
                    st.rerun()

# --- ABA 4: CONFIGURAÇÕES FECD ---
with tab4:
    st.subheader("Configurações do Sistema")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.write("### Categorias")
        nova_cat = st.text_input("Nova Categoria:")
        if st.button("Adicionar Cat") and nova_cat:
            supabase.table("categorias").insert({"nome": nova_cat}).execute()
            st.rerun()
        for cat in get_categorias(): st.caption(f"• {cat['nome']}")

    with c2:
        st.write("### Origens")
        nova_ori = st.text_input("Nova Origem:")
        if st.button("Adicionar Ori") and nova_ori:
            supabase.table("origens").insert({"nome": nova_ori}).execute()
            st.rerun()
        for ori in get_origens(): st.caption(f"• {ori['nome']}")

    with c3:
        st.write("### Chaves de API")
        nova_key = st.text_input("Groq API Key:", type="password")
        if st.button("Salvar Chave") and nova_key:
            supabase.table("config_chaves").insert({"chave": nova_key}).execute()
            st.rerun()
