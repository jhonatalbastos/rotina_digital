import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader
import re

# --- 1. CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Minhas Atividades - FECD", page_icon="📝", layout="wide")

@st.cache_resource
def init_connection():
    try:
        url = st.secrets["connections"]["supabase"]["url"]
        key = st.secrets["connections"]["supabase"]["key"]
        return create_client(url, key)
    except: return None

supabase: Client = init_connection()

# --- 2. MOTOR DE TRATAMENTO DE TEXTO (CORREÇÃO PARA DOCUMENTOS ESCANEADOS) ---

def sanear_texto_ocr(texto):
    """Limpa o 'lixo' de cartório e caracteres especiais que travam a IA."""
    # Remove sequências de pontos, sublinhados e caracteres não alfanuméricos isolados
    texto = re.sub(r'\.{2,}', '', texto)
    texto = re.sub(r'_{2,}', '', texto)
    # Remove cabeçalhos de cartório repetitivos para focar no conteúdo
    texto = re.sub(r'OFÍCIO DE NOTAS.*?RJ', '', texto, flags=re.IGNORECASE | re.DOTALL)
    # Normaliza espaços
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def extrair_texto_pdf(file):
    try:
        reader = PdfReader(file)
        texto = ""
        # Processa até 10 páginas para garantir densidade de informação
        for page in reader.pages[:10]:
            content = page.extract_text()
            if content: texto += content + "\n"
        return sanear_texto_ocr(texto)
    except: return "Falha na extração física do PDF."

def analisar_documento_estrategico(texto_sanerado):
    """IA com lógica de auditoria para processar o estatuto limpo."""
    chaves = []
    if "GROQ_KEYS" in st.secrets:
        chaves.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if "gsk_" in k])
    
    # Busca chaves também no banco
    try:
        res_k = supabase.table("config_chaves").select("chave").execute()
        if res_k.data: chaves.extend([k['chave'] for k in res_k.data])
    except: pass
    
    if not chaves: return "Erro: Nenhuma API Key configurada."

    prompt = """
    Você é um Auditor e Consultor Jurídico da Fundação FECD. 
    O texto abaixo vem de um OCR de documento antigo. 
    Ignore erros de grafia e extraia APENAS o que for estrutural:
    1. RESUMO EXECUTIVO: Finalidade da entidade.
    2. REGRAS DE GESTÃO: Quem assina, limites de competência e prazos.
    3. OBSERVAÇÃO TÉCNICA: O que o Gerente Financeiro precisa saber de imediato.
    """
    
    random.shuffle(chaves)
    for c in chaves:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {c}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-specdec", # Modelo mais robusto para textos complexos
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": f"TEXTO DO DOCUMENTO:\n{texto_sanerado[:8000]}"}
                    ],
                    "temperature": 0.1
                }, 
                timeout=25
            )
            if r.status_code == 200: 
                return r.json()['choices'][0]['message']['content']
        except: continue
    return "A análise da IA falhou por timeout ou limite de tokens. Tente um arquivo menor ou verifique as chaves."

# --- 3. INTERFACE ---

if not supabase: st.stop()

tab_reg, tab_pan, tab_perf, tab_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama (CRUD)", "🏢 Perfil & Contexto", "⚙️ Configurações"])

# ABA 1: MAPEAMENTO
with tab_reg:
    with st.form("f_reg", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        dt = c1.date_input("Data:", value=datetime.date.today())
        cats = [x['nome'] for x in supabase.table("categorias").select("nome").execute().data]
        ct = c2.selectbox("Domínio:", cats or ["Geral"])
        oris = [x['nome'] for x in supabase.table("origens").select("nome").execute().data]
        og = c3.selectbox("Origem:", oris or ["E-mail"])
        cp = st.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        ds = st.text_area("Descreva a demanda:")
        if st.form_submit_button("Sincronizar"):
            if ds:
                supabase.table("registros").insert({"data": dt.strftime("%Y-%m-%d"), "dominio": ct, "origem": og, "complexidade": cp, "descricao": ds}).execute()
                st.success("Registrado!"); st.rerun()

# ABA 2: PANORAMA
with tab_pan:
    st.subheader("📊 Gestão de Atividades")
    res = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        for _, row in df.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([1, 4, 1])
                c1.caption(f"ID: {row['id']} | {row['data']}")
                c2.markdown(f"**{row.get('dominio', 'Geral')}** - {row['descricao'][:100]}...")
                if c3.button("Ver Detalhes", key=f"v_{row['id']}"): st.info(row.get('mapeamento_ia', 'Sem análise.'))
                st.divider()

# ABA 3: PERFIL E CONHECIMENTO (FOCO NA CORREÇÃO DO ERRO)
with tab_perf:
    sub_p, sub_c = st.tabs(["👤 Perfil & Equipe", "📚 Catálogo de Inteligência"])
    
    with sub_p:
        st.info("Configure seus dados profissionais e equipe aqui.")
        # Lógica de perfil aqui...

    with sub_c:
        st.subheader("Base de Conhecimento Catalogada")
        with st.expander("📥 Integrar Novo PDF Técnico", expanded=True):
            up = st.file_uploader("Arquivo (Estatutos/Atas):", type="pdf")
            if up and st.button("🚀 Processar com Inteligência"):
                with st.spinner("Sanenado texto e gerando auditoria IA..."):
                    texto_limpo = extrair_texto_pdf(up)
                    analise = analisar_documento_estrategico(texto_limpo)
                    
                    try:
                        supabase.table("documentos_conhecimento").insert({
                            "titulo": up.name,
                            "resumo_ia": analise,
                            "conteudo_completo": texto_limpo[:8000]
                        }).execute()
                        st.success("Documento analisado com sucesso!"); st.rerun()
                    except Exception as e:
                        st.error(f"Erro no banco: {e}")

        # Lista de documentos
        docs = supabase.table("documentos_conhecimento").select("*").order("created_at", desc=True).execute().data
        if docs:
            for d in docs:
                with st.expander(f"📄 {d['titulo']}"):
                    st.markdown("**Análise Técnica:**")
                    st.write(d['resumo_ia'])
                    if st.button("Excluir", key=f"del_{d['id']}"):
                        supabase.table("documentos_conhecimento").delete().eq("id", d['id']).execute(); st.rerun()

# ABA 4: CONFIGURAÇÕES
with tab_conf:
    st.subheader("Configurações FECD")
    c1, c2 = st.columns(2)
    with c1:
        nc = st.text_input("Nova Categoria:")
        if st.button("Salvar Cat"): supabase.table("categorias").insert({"nome": nc}).execute(); st.rerun()
    with c2:
        nk = st.text_input("API Key Groq:", type="password")
        if st.button("Salvar Chave"): supabase.table("config_chaves").insert({"chave": nk}).execute(); st.rerun()
