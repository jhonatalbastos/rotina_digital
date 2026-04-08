import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader
import re

# --- 1. CONFIGURAÇÃO DA PÁGINA E INTERFACE ---
st.set_page_config(
    page_title="Sistema de Gestão FECD",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilização de Abas
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #f0f2f6;
        border-radius: 5px 5px 0px 0px;
        padding: 10px 20px;
    }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXÃO COM O BANCO DE DADOS ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["connections"]["supabase"]["url"]
        key = st.secrets["connections"]["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Erro de conexão com o banco: {e}")
        return None

supabase: Client = init_connection()

# --- 3. FUNÇÕES DE SUPORTE (CRUD E BUSCA) ---

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

def carregar_perfil():
    try:
        res = supabase.table("perfil_contexto").select("*").eq("id", 1).execute()
        return res.data[0] if res.data else {"nome_profissional": "Jhonata", "cargo": "Gestor"}
    except: return {"nome_profissional": "Jhonata", "cargo": "Gestor"}

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

def buscar_chaves_api():
    pool = []
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if "gsk_" in k])
    try:
        res = supabase.table("config_chaves").select("chave").execute()
        if res.data: pool.extend([k['chave'] for k in res.data if "gsk_" in k['chave']])
    except: pass
    return list(set(pool))

# --- 4. MOTOR DE INTELIGÊNCIA E TRATAMENTO DE PDF ---

def sanear_texto_ocr(texto):
    """Limpa ruídos de documentos escaneados e cartórios"""
    texto = re.sub(r'OFÍCIO DE NOTAS.*?RJ', '', texto, flags=re.IGNORECASE | re.DOTALL)
    texto = re.sub(r'\.{2,}', ' ', texto)
    texto = re.sub(r'_{2,}', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def extrair_texto_pdf(file):
    try:
        reader = PdfReader(file)
        texto = ""
        for page in reader.pages[:12]:
            content = page.extract_text()
            if content: texto += content + "\n"
        return sanear_texto_ocr(texto)
    except Exception as e:
        return f"Falha no processamento: {e}"

def analisar_com_ia(texto, contexto="geral"):
    chaves = buscar_chaves_api()
    if not chaves: return "Erro: Nenhuma chave de API configurada."
    
    prompt_base = "Você é um Auditor e Gestor Financeiro da FECD."
    if contexto == "documento":
        prompt = f"{prompt_base} Resuma este estatuto em: 1. Objeto, 2. Competências de Assinatura, 3. Prazos Críticos."
    else:
        prompt = f"{prompt_base} Analise esta demanda e sugira a conduta técnica adequada."

    random.shuffle(chaves)
    for c in chaves:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {c}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-specdec",
                    "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": texto[:8000]}],
                    "temperature": 0.1
                }, 
                timeout=25
            )
            if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        except: continue
    return "Falha na análise da IA"

# --- 5. ESTRUTURA DA INTERFACE ---

if not supabase: st.stop()

tab_reg, tab_pan, tab_perf, tab_conf = st.tabs([
    "📝 Mapear Processo", "📊 Panorama (CRUD)", "🏢 Perfil & Contexto", "⚙️ Configurações"
])

# ABA 1: MAPEAMENTO DE DEMANDAS
with tab_reg:
    with st.form("f_registro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data:", value=datetime.date.today())
        ct = c2.selectbox("Domínio:", [x['nome'] for x in carregar_categorias()] or ["Geral"])
        og = c3.selectbox("Origem:", [x['nome'] for x in carregar_origens()] or ["E-mail"])
        cp = st.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        ds = st.text_area("Descrição da Demanda / E-mail:", height=200)
        if st.form_submit_button("🚀 Sincronizar com IA"):
            if ds:
                with st.spinner("IA Analisando..."):
                    ana = analisar_com_ia(ds)
                    supabase.table("registros").insert({
                        "data": dt.strftime("%Y-%m-%d"), "dominio": ct, "origem": og,
                        "complexidade": cp, "descricao": ds, "mapeamento_ia": ana
                    }).execute()
                    st.success("Demanda registrada!"); st.rerun()

# ABA 2: PANORAMA (CRUD)
with tab_pan:
    st.subheader("Gestão de Atividades")
    registros = supabase.table("registros").select("*").order("created_at", desc=True).execute().data
    if registros:
        df = pd.DataFrame(registros)
        h = st.columns([0.4, 0.8, 1.2, 1.5, 3.5, 0.6, 0.6])
        for i, t in enumerate(["Sel.", "Data", "Domínio", "Origem", "Descrição", "Edit", "IA"]): h[i].write(f"**{t}**")
        
        selecionados = []
        for _, row in df.iterrows():
            c = st.columns([0.4, 0.8, 1.2, 1.5, 3.5, 0.6, 0.6])
            if c[0].checkbox("", key=f"s_{row['id']}"): selecionados.append(row['id'])
            c[1].write(row['data']); c[2].write(row.get('dominio','')); c[3].write(row.get('origem',''))
            c[4].write(row['descricao'][:80] + "...")
            if c[5].button("📝", key=f"e_{row['id']}"): st.session_state[f"ed_{row['id']}"] = True
            if c[6].button("🔍", key=f"ia_{row['id']}"): st.info(row.get('mapeamento_ia', 'Sem análise.'))
            
            if st.session_state.get(f"ed_{row['id']}", False):
                with st.form(f"f_ed_{row['id']}"):
                    nd = st.text_area("Editar:", value=row['descricao'])
                    if st.form_submit_button("Salvar"):
                        supabase.table("registros").update({"descricao": nd}).eq("id", row['id']).execute()
                        st.session_state[f"ed_{row['id']}"] = False; st.rerun()
        if selecionados and st.button("🗑️ Excluir Selecionados"):
            supabase.table("registros").delete().in_("id", selecionados).execute(); st.rerun()

# ABA 3: PERFIL E INTELIGÊNCIA
with tab_perf:
    col_p, col_i = st.columns([1, 1.2])
    with col_p:
        st.subheader("👤 Perfil & Equipe")
        perf = carregar_perfil()
        with st.form("f_perf"):
            np = st.text_input("Nome:", value=perf.get('nome_profissional',''))
            cp = st.text_input("Cargo:", value=perf.get('cargo',''))
            mt = st.text_area("Metas:", value=perf.get('metas_estrategicas',''))
            if st.form_submit_button("Atualizar Perfil"):
                supabase.table("perfil_contexto").upsert({"id": 1, "nome_profissional": np, "cargo": cp, "metas_estrategicas": mt}).execute(); st.rerun()
        
        st.write("### 👥 Equipe")
        with st.form("f_eq", clear_on_submit=True):
            en = st.text_input("Nome:"); ec = st.text_input("Cargo:"); ee = st.text_input("E-mail:")
            ep = st.selectbox("Posição:", ["Superior", "Par", "Subordinado"])
            if st.form_submit_button("Adicionar"):
                supabase.table("equipe_organograma").insert({"nome": en, "cargo": ec, "email": ee, "posicao": ep}).execute(); st.rerun()
        
        for m in carregar_equipe(): st.markdown(f"**{m['nome']}** - {m['cargo']} ({m['posicao']})")

    with col_i:
        st.subheader("📚 Base de Conhecimento")
        up = st.file_uploader("Subir PDF Estrutural:", type="pdf")
        if up and st.button("Integrar PDF à Inteligência"):
            with st.spinner("Analisando..."):
                txt = extrair_texto_pdf(up)
                res = analisar_com_ia(txt, contexto="documento")
                try:
                    supabase.table("documentos_conhecimento").insert({"titulo": up.name, "resumo_ia": res, "conteudo_completo": txt[:8000]}).execute()
                    st.success("Documento Catalogado!"); st.rerun()
                except Exception as e: st.error(f"Erro ao salvar: {e}")
        
        for d in carregar_documentos():
            with st.expander(f"📄 {d['titulo']}"):
                st.write(d['resumo_ia'])
                if st.button("Remover", key=f"rd_{d['id']}"):
                    supabase.table("documentos_conhecimento").delete().eq("id", d['id']).execute(); st.rerun()

# ABA 4: CONFIGURAÇÕES
with tab_conf:
    st.subheader("⚙️ Configurações FECD")
    c1, c2, c3 = st.columns(3)
    with c1:
        nc = st.text_input("Nova Cat:")
        if st.button("Add Cat") and nc: supabase.table("categorias").insert({"nome": nc}).execute(); st.rerun()
        for x in carregar_categorias(): st.caption(f"• {x['nome']}")
    with c2:
        no = st.text_input("Nova Ori:")
        if st.button("Add Ori") and no: supabase.table("origens").insert({"nome": no}).execute(); st.rerun()
        for x in carregar_origens(): st.caption(f"• {x['nome']}")
    with c3:
        nk = st.text_input("Nova Chave Groq:", type="password")
        if st.button("Salvar Chave"):
            try:
                supabase.table("config_chaves").insert({"chave": nk}).execute()
                st.success("Chave salva!"); st.rerun()
            except Exception as e: st.error(f"Erro ao salvar: {e}")
