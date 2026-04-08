import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader

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

def extrair_texto_pdf(file):
    try:
        reader = PdfReader(file)
        texto = ""
        for page in reader.pages:
            texto += page.extract_text()
        return texto
    except: return "Erro ao extrair texto do PDF."

def analisar_processo_ia(texto_atividade, categoria, origem, complexidade):
    chaves = buscar_pool_chaves_total()
    if not chaves: return "⚠️ Sem chaves configuradas."
    
    perfil = carregar_perfil()
    docs = carregar_documentos()
    
    # Consolida contexto dos documentos para a IA
    contexto_doc = "\n".join([f"- {d['tipo']}: {d['resumo_ia']}" for d in docs[:3]])
    
    system_prompt = f"""
    Você é o Gêmeo Digital de {perfil.get('nome_profissional', 'Jhonata')}, {perfil.get('cargo', 'Gerente Financeiro')}.
    Contexto Profissional: {perfil.get('certificacoes', 'Contador/Auditor')} na empresa {perfil.get('empresa_nome', 'FECD')}.
    Hierarquia: Reporta a {perfil.get('hierarquia_superior', 'Diretoria')}.
    Meta Estratégica: {perfil.get('metas_estrategicas', 'Automação para trabalho remoto')}.
    
    Base de Conhecimento Técnica:
    {contexto_doc}

    Analise a atividade para fins de mapeamento de carga de trabalho. Foque em aspectos técnicos e hierárquicos.
    """
    
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
                        {"role": "user", "content": f"Atividade: {texto_atividade}\nCategoria: {categoria}"}
                    ],
                    "temperature": 0.1
                }, timeout=20
            )
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
        except: continue
    return "❌ Erro na comunicação com a IA."

# --- INTERFACE PRINCIPAL ---
st.title("📝 Minhas Atividades - FECD")

if not supabase:
    st.error("Falha na conexão com o Banco de Dados.")
    st.stop()

tab_reg, tab_pan, tab_perf, tab_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama (CRUD)", "🏢 Perfil & Contexto", "⚙️ Configurações"])

# --- ABA 1: MAPEAMENTO ---
with tab_reg:
    with st.form("form_registro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_f = c1.date_input("Data:", value=datetime.date.today())
        cats = [c['nome'] for c in carregar_categorias()]
        cat_f = c2.selectbox("Categoria:", cats if cats else ["Financeiro"])
        origs = [o['nome'] for o in carregar_origens()]
        origem_f = c3.selectbox("Origem:", origs if origs else ["E-mail"])
        comp_f = st.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        desc_f = st.text_area("Descrição detalhada da Atividade (Obrigatório):")
        
        if st.form_submit_button("Sincronizar com Cloud"):
            if desc_f:
                with st.spinner("IA processando com contexto institucional..."):
                    analise = analisar_processo_ia(desc_f, cat_f, origem_f, comp_f)
                    supabase.table("registros").insert({
                        "data": data_f.strftime("%Y-%m-%d"), "dominio": cat_f, "origem": origem_f,
                        "complexidade": comp_f, "descricao": desc_f, "mapeamento_ia": analise
                    }).execute()
                    st.success("Dados salvos com sucesso!")
                    st.rerun()

# --- ABA 2: PANORAMA (CRUD COMPLETO) ---
with tab_pan:
    st.subheader("📊 Gestão de Processos")
    res = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        if st.button("🔄 Atualizar Dados"): st.rerun()
        
        st.write("---")
        h = st.columns([0.5, 0.8, 1.2, 1.5, 1.5, 1, 3, 0.8, 0.8])
        h[0].write("**Sel.**"); h[1].write("**ID**"); h[2].write("**Data**")
        h[3].write("**Domínio**"); h[4].write("**Origem**"); h[5].write("**Comp.**")
        h[6].write("**Descrição**"); h[7].write("**Edit**"); h[8].write("**Ver**")

        selecionados = []
        for _, row in df.iterrows():
            c = st.columns([0.5, 0.8, 1.2, 1.5, 1.5, 1, 3, 0.8, 0.8])
            if c[0].checkbox("", key=f"check_{row['id']}"): selecionados.append(row['id'])
            c[1].write(row['id'])
            c[2].write(row['data'])
            c[3].write(row.get('dominio', 'N/A'))
            c[4].write(row.get('origem', 'N/A'))
            c[5].write(row['complexidade'])
            c[6].write(row['descricao'][:60] + "...")
            
            if c[7].button("📝", key=f"ed_{row['id']}"): st.session_state[f"ed_mode_{row['id']}"] = True
            if c[8].button("🔍", key=f"vw_{row['id']}"): st.info(row['mapeamento_ia'])

            if st.session_state.get(f"ed_mode_{row['id']}", False):
                with st.expander(f"✏️ Editar Atividade #{row['id']}", expanded=True):
                    with st.form(f"form_ed_{row['id']}"):
                        ed_desc = st.text_area("Nova Descrição", value=row['descricao'])
                        if st.form_submit_button("Atualizar"):
                            supabase.table("registros").update({"descricao": ed_desc}).eq("id", row['id']).execute()
                            st.session_state[f"ed_mode_{row['id']}"] = False
                            st.rerun()
                        if st.form_submit_button("Cancelar"):
                            st.session_state[f"ed_mode_{row['id']}"] = False
                            st.rerun()
        
        if selecionados:
            if st.button(f"🔴 Excluir Selecionados ({len(selecionados)})"):
                supabase.table("registros").delete().in_("id", selecionados).execute()
                st.rerun()
    else:
        st.info("Nenhum registro encontrado.")

# --- ABA 3: PERFIL & CONTEXTO (ORGANOGRAMA) ---
with tab_perf:
    st.subheader("🏢 Meu Perfil & Inteligência Institucional")
    perfil = carregar_perfil()
    
    col_inf, col_vis = st.columns([1, 1.2])
    
    with col_inf:
        with st.expander("👤 Dados Profissionais", expanded=True):
            with st.form("form_perfil_contexto"):
                n_p = st.text_input("Nome Profissional:", value=perfil.get('nome_profissional', ''))
                c_p = st.text_input("Cargo Atual:", value=perfil.get('cargo', ''))
                cert_p = st.text_area("Certificações (QTG, CRC):", value=perfil.get('certificacoes', ''))
                sup_p = st.text_input("Superior(es):", value=perfil.get('hierarquia_superior', ''))
                sub_p = st.text_input("Equipe/Subordinados:", value=perfil.get('hierarquia_subordinados', ''))
                meta_p = st.text_area("Metas Estratégicas:", value=perfil.get('metas_estrategicas', ''))
                
                if st.form_submit_button("Salvar Perfil & Estrutura"):
                    payload = {
                        "id": perfil.get('id', 1), "nome_profissional": n_p, "cargo": c_p,
                        "certificacoes": cert_p, "hierarquia_superior": sup_p,
                        "hierarquia_subordinados": sub_p, "metas_estrategicas": meta_p
                    }
                    supabase.table("perfil_contexto").upsert(payload).execute()
                    st.success("Contexto profissional atualizado!")
                    st.rerun()

    with col_vis:
        st.write("### 🌲 Organograma Visual")
        if perfil.get('nome_profissional'):
            st.caption(f"**Hierarquia Superior:** {perfil.get('hierarquia_superior', 'Diretoria')}")
            st.markdown(f"""
                <div style="border: 2px solid #ff4b4b; border-radius: 15px; padding: 25px; text-align: center; background-color: #ffffff; box-shadow: 2px 2px 10px rgba(0,0,0,0.1);">
                    <h3 style="color: #31333F; margin-bottom: 5px;">{perfil.get('nome_profissional').upper()}</h3>
                    <p style="color: #555; font-weight: bold; margin: 0;">{perfil.get('cargo')}</p>
                    <p style="color: #888; font-size: 0.85em;">{perfil.get('certificacoes')}</p>
                </div>
            """, unsafe_allow_html=True)
            st.write("↓")
            st.success(f"**Gestão de Equipe:** {perfil.get('hierarquia_subordinados', 'Foco em Processos Individuais')}")
        else:
            st.warning("Preencha seu perfil para gerar o organograma.")

    st.write("---")
    with st.expander("📄 Base de Conhecimento (Upload de PDFs)"):
        pdf_file = st.file_uploader("Subir PDF (Estatuto, GTD, Normas):", type="pdf")
        if pdf_file and st.button("Processar e Integrar Conhecimento"):
            with st.spinner("IA extraindo inteligência do documento..."):
                texto = extrair_texto_pdf(pdf_file)
                supabase.table("documentos_conhecimento").insert({
                    "titulo": pdf_file.name, "resumo_ia": texto[:3000], "tipo": "Referência Técnica"
                }).execute()
                st.success(f"Documento '{pdf_file.name}' integrado ao seu Gêmeo Digital!")
                st.rerun()

# --- ABA 4: CONFIGURAÇÕES (RESTAURADA) ---
with tab_conf:
    st.subheader("⚙️ Configurações FECD")
    c_cat, c_ori, c_key = st.columns(3)
    
    with c_cat:
        st.write("**📁 Categorias**")
        add_cat = st.text_input("Nova Categoria:")
        if st.button("Adicionar"):
            if add_cat: supabase.table("categorias").insert({"nome": add_cat.strip()}).execute(); st.rerun()
        for cat in carregar_categorias():
            st.caption(f"• {cat['nome']}")
            
    with c_ori:
        st.write("**📍 Origens**")
        add_ori = st.text_input("Nova Origem:")
        if st.button("Adicionar Origem"):
            if add_ori: supabase.table("origens").insert({"nome": add_ori.strip()}).execute(); st.rerun()
        for ori in carregar_origens():
            st.caption(f"• {ori['nome']}")
            
    with c_key:
        st.write("**🔑 Chaves Groq**")
        add_k = st.text_input("Chave API:", type="password")
        if st.button("Salvar Key"):
            if add_k.startswith("gsk_"): supabase.table("config_chaves").insert({"chave": add_k.strip()}).execute(); st.rerun()
        for k in carregar_chaves_db():
            st.text(f"Ativa: {k['chave'][:12]}...")
