import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader # Necessário para ler seus documentos técnicos

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

def carregar_perfil():
    try:
        res = supabase.table("perfil_contexto").select("*").limit(1).execute()
        return res.data[0] if res.data else {}
    except: return {}

def carregar_documentos():
    try:
        res = supabase.table("documentos_conhecimento").select("*").order("created_at", desc=True).execute()
        return res.data if res.data else []
    except: return []

def buscar_pool_chaves_total():
    pool = []
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if "gsk_" in k])
    res = supabase.table("config_chaves").select("chave").execute()
    if res.data:
        pool.extend([item['chave'].strip() for item in res.data])
    return list(set(pool))

def extrair_texto_pdf(file):
    reader = PdfReader(file)
    texto = ""
    for page in reader.pages:
        texto += page.extract_text()
    return texto

def analisar_processo_ia(texto_atividade, categoria, origem, complexidade):
    chaves = buscar_pool_chaves_total()
    perfil = carregar_perfil()
    docs = carregar_documentos()
    
    # Monta o contexto institucional para a IA
    contexto_doc = "\n".join([f"- {d['tipo']}: {d['resumo_ia']}" for d in docs[:3]])
    
    system_prompt = f"""
    Você é o Gêmeo Digital de {perfil.get('nome_profissional', 'Jhonata')}, {perfil.get('cargo', 'Gerente Financeiro')}.
    Contexto Profissional: {perfil.get('certificacoes', 'Contador/Auditor')}.
    Empresa: {perfil.get('empresa_nome', 'FECD')}.
    Hierarquia: Reporta a {perfil.get('hierarquia_superior', 'Diretoria')}.
    
    Base de Conhecimento (Resumos de Documentos):
    {contexto_doc}

    Sua tarefa é ANALISAR E CATALOGAR a atividade descrita pelo usuário para fins de mapeamento de carga de trabalho e automação.
    NÃO responda como um assistente (ex: 'Prezado Fulano'), responda como um Analista de Processos.
    
    Estrutura:
    1. RESUMO TÉCNICO
    2. TAREFAS IDENTIFICADAS (FOCO EM AUDITORIA/FINANÇAS)
    3. ALINHAMENTO HIERÁRQUICO/RISCO
    4. RECOMENDAÇÃO DE AUTOMAÇÃO/OTIMIZAÇÃO
    """
    
    random.shuffle(chaves)
    for chave in chaves:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Atividade: {texto_atividade}\nCategoria: {categoria}\nOrigem: {origem}"}
                    ],
                    "temperature": 0.1
                }, timeout=20
            )
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
        except: continue
    return "❌ Falha técnica na IA."

# --- INTERFACE ---
st.title("📝 Minhas Atividades - FECD")

if not supabase: st.stop()

aba_reg, aba_dash, aba_perfil, aba_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama (CRUD)", "🏢 Perfil & Contexto", "⚙️ Configurações"])

# --- ABA: MAPEAMENTO ---
with aba_reg:
    with st.form("form_create", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_f = c1.date_input("Data:", value=datetime.date.today())
        cats = [c['nome'] for c in carregar_categorias()]
        cat_f = c2.selectbox("Categoria:", cats if cats else ["Financeiro"])
        origs = [o['nome'] for o in carregar_origens()]
        origem_f = c3.selectbox("Origem:", origs if origs else ["E-mail"])
        comp_f = st.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        desc_f = st.text_area("Descrição detalhada da Atividade:")
        
        if st.form_submit_button("Sincronizar com Nuvem"):
            if desc_f:
                with st.spinner("IA Analisando com contexto institucional..."):
                    analise = analisar_processo_ia(desc_f, cat_f, origem_f, comp_f)
                    supabase.table("registros").insert({
                        "data": data_f.strftime("%Y-%m-%d"), "dominio": cat_f, "origem": origem_f,
                        "complexidade": comp_f, "descricao": desc_f, "mapeamento_ia": analise
                    }).execute()
                    st.success("✅ Atividade registrada e analisada!")
                    st.rerun()

# --- ABA: PANORAMA (CRUD) ---
with aba_dash:
    st.subheader("📊 Gestão de Atividades")
    res = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        h = st.columns([0.5, 0.8, 1.2, 1.5, 1.5, 1, 3, 0.8, 0.8])
        h[3].write("**Categoria**")
        h[4].write("**Origem**")
        # Loop de exibição simplificado aqui para brevidade, mas funcional
        for _, row in df.iterrows():
            c = st.columns([0.5, 0.8, 1.2, 1.5, 1.5, 1, 3, 0.8, 0.8])
            c[1].write(row['id'])
            c[3].write(row['dominio'])
            c[4].write(row['origem'])
            c[6].write(row['descricao'][:50] + "...")
            if c[8].button("🔍", key=f"v_{row['id']}"):
                st.info(row['mapeamento_ia'])
    else: st.info("Nada registrado.")

# --- ABA: NOVO PERFIL & CONTEXTO ---
with aba_perfil:
    st.subheader("🏢 Meu Perfil & Inteligência Institucional")
    perfil = carregar_perfil()
    
    with st.expander("👤 Dados Profissionais & Organograma", expanded=True):
        with st.form("form_perfil"):
            col1, col2 = st.columns(2)
            nome_p = col1.text_input("Nome Profissional:", value=perfil.get('nome_profissional', ''))
            cargo_p = col2.text_input("Cargo Atual:", value=perfil.get('cargo', ''))
            cert_p = col1.text_area("Certificações (ex: Contador, QTG):", value=perfil.get('certificacoes', ''))
            sup_p = col2.text_input("Superior Imediato:", value=perfil.get('hierarquia_superior', ''))
            metas_p = st.text_area("Metas Estratégicas (ex: Trabalho Híbrido 2026):", value=perfil.get('metas_estrategicas', ''))
            
            if st.form_submit_button("Atualizar Perfil"):
                data_update = {
                    "nome_profissional": nome_p, "cargo": cargo_p, "certificacoes": cert_p,
                    "hierarquia_superior": sup_p, "metas_estrategicas": metas_p
                }
                if perfil.get('id'):
                    supabase.table("perfil_contexto").update(data_update).eq("id", perfil['id']).execute()
                else:
                    supabase.table("perfil_contexto").insert(data_update).execute()
                st.success("Perfil atualizado!")
                st.rerun()

    with st.expander("📄 Base de Conhecimento (Upload de PDFs)"):
        st.write("Envie Estatutos, Normas Contábeis ou Material GTD para a IA aprender.")
        uploaded_file = st.file_uploader("Escolher PDF", type="pdf")
        tipo_doc = st.selectbox("Tipo de Documento", ["Estatuto", "Norma Contábil", "Ata de Reunião", "Material GTD", "Outros"])
        
        if st.button("Analisar e Salvar Documento") and uploaded_file:
            with st.spinner("IA lendo e resumindo o documento..."):
                texto_pdf = extra_text_pdf(uploaded_file)
                # IA resume o documento para não estourar o limite de tokens depois
                chaves = buscar_pool_chaves_total()
                resumo_ia = "Falha ao resumir."
                if chaves:
                    prompt_doc = f"Resuma os pontos principais deste {tipo_doc} focado em processos financeiros e regras da fundação FECD: {texto_pdf[:8000]}"
                    res = requests.post("https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {chaves[0]}"},
                        json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": prompt_doc}]})
                    if res.status_code == 200: resumo_ia = res.json()['choices'][0]['message']['content']
                
                supabase.table("documentos_conhecimento").insert({
                    "titulo": uploaded_file.name, "tipo": tipo_doc, "resumo_ia": resumo_ia
                }).execute()
                st.success(f"Documento '{uploaded_file.name}' catalogado!")
                st.rerun()
        
        st.write("---")
        docs = carregar_documentos()
        for d in docs:
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"**{d['titulo']}** ({d['tipo']})")
            if c3.button("🗑️", key=f"del_doc_{d['id']}"):
                supabase.table("documentos_conhecimento").delete().eq("id", d['id']).execute()
                st.rerun()

# --- ABA: CONFIGURAÇÕES ---
with aba_conf:
    st.subheader("⚙️ Configurações FECD")
    # ... (mesmo código anterior de categorias e origens)
