import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader
import re

# --- 1. CONFIGURAÇÕES INICIAIS ---
st.set_page_config(
    page_title="Minhas Atividades - FECD",
    page_icon="📝",
    layout="wide"
)

# --- 2. CONEXÃO COM O SUPABASE ---
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

# --- 3. FUNÇÕES DE SUPORTE (DATABASE) ---

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

def buscar_pool_chaves():
    pool = []
    # Busca chaves tanto do secrets quanto do banco de dados para redundância
    if "GROQ_KEYS" in st.secrets:
        pool.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if "gsk_" in k])
    try:
        res = supabase.table("config_chaves").select("*").execute()
        if res.data:
            pool.extend([k['chave'].strip() for k in res.data if "gsk_" in k['chave']])
    except: pass
    return list(set(pool))

# --- 4. MOTOR DE OCR E IA (INTELIGÊNCIA INSTITUCIONAL) ---

def limpar_texto_ocr(texto):
    """Remove ruídos comuns de documentos escaneados mal lidos."""
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'[^\w\s\d.,;:\-\(\)@/]', '', texto)
    return texto.strip()

def extrair_texto_pdf(file):
    try:
        reader = PdfReader(file)
        texto = ""
        # Limita o processamento às primeiras 15 páginas para evitar erro de timeout
        for page in reader.pages[:15]:
            content = page.extract_text()
            if content: texto += content + "\n"
        return limpar_texto_ocr(texto)
    except: return "Falha crítica na extração do PDF."

def analisar_documento_estrategico(texto_pdf):
    """Usa a IA para criar o entendimento que será catalogado."""
    chaves = buscar_pool_chaves()
    if not chaves: return "Documento processado, mas IA indisponível para análise."
    
    prompt = """
    Você é um Auditor Sênior e Gestor da Fundação FECD. 
    Analise o conteúdo deste documento (que pode conter erros de OCR) e extraia:
    1. RESUMO EXECUTIVO: O que é e qual o objetivo do documento.
    2. PONTOS DE CONTROLE: Datas, valores, obrigações ou cláusulas críticas.
    3. ORIENTAÇÃO TÉCNICA: Como o gestor deve aplicar isso no dia a dia.
    Responda em tópicos limpos.
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
    return "A análise da IA falhou, mas o texto bruto foi salvo."

def analisar_processo_ia(texto_demanda):
    """Analisa e-mails ou tarefas baseando-se no contexto da equipe e documentos salvos."""
    chaves = buscar_pool_chaves()
    perfil = carregar_perfil_base()
    equipe = carregar_equipe()
    docs = carregar_documentos()
    
    ctx_equipe = "\n".join([f"- {m['nome']} ({m['cargo']}) | E-mail: {m['email']}" for m in equipe])
    ctx_doc = "\n".join([f"DOC: {d['titulo']} | ANÁLISE: {d['resumo_ia'][:500]}" for d in docs[:2]])
    
    prompt = f"""
    Você é o Assistente Estratégico do {perfil.get('nome_profissional', 'Jhonata')}, {perfil.get('cargo', 'Gerente Financeiro')}.
    EQUIPE CADASTRADA: {ctx_equipe}
    CONHECIMENTO TÉCNICO DISPONÍVEL: {ctx_doc}
    
    Analise a demanda abaixo e sugira a melhor conduta técnica e resposta profissional.
    Identifique se o remetente é da equipe e qual sua hierarquia.
    Demanda: {texto_demanda}
    """
    
    random.shuffle(chaves)
    for c in chaves:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {c}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}, 
                timeout=15)
            if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        except: continue
    return "A IA não conseguiu gerar uma análise agora."

# --- 5. INTERFACE DO USUÁRIO ---

if not supabase: st.stop()

tab_reg, tab_pan, tab_perf, tab_conf = st.tabs(["📝 Mapear Processo", "📊 Panorama (CRUD)", "🏢 Perfil & Contexto", "⚙️ Configurações"])

# --- ABA 1: REGISTRO DE ATIVIDADES ---
with tab_reg:
    with st.form("form_novo_registro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_f = c1.date_input("Data:", value=datetime.date.today())
        cat_f = c2.selectbox("Domínio:", [c['nome'] for c in carregar_categorias()] or ["Geral"])
        ori_f = c3.selectbox("Origem:", [o['nome'] for o in carregar_origens()] or ["E-mail"])
        
        comp_f = st.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        desc_f = st.text_area("Descreva a atividade ou cole o corpo do e-mail:")
        
        if st.form_submit_button("🚀 Sincronizar com IA"):
            if desc_f:
                with st.spinner("IA processando contexto..."):
                    analise = analisar_processo_ia(desc_f)
                    supabase.table("registros").insert({
                        "data": data_f.strftime("%Y-%m-%d"), 
                        "dominio": cat_f, 
                        "origem": ori_f,
                        "complexidade": comp_f, 
                        "descricao": desc_f, 
                        "mapeamento_ia": analise
                    }).execute()
                    st.success("Atividade sincronizada com o banco de dados!")
                    st.rerun()

# --- ABA 2: PANORAMA (GERENCIAMENTO/CRUD) ---
with tab_pan:
    st.subheader("📊 Gestão de Atividades Mapeadas")
    res_atv = supabase.table("registros").select("*").order("created_at", desc=True).execute()
    
    if res_atv.data:
        df = pd.DataFrame(res_atv.data)
        st.write("---")
        
        # Cabeçalho customizado para o CRUD
        cols = st.columns([0.4, 0.6, 1.0, 1.2, 1.2, 0.8, 3.0, 0.6, 0.6])
        titulos = ["Sel.", "ID", "Data", "Domínio", "Origem", "Comp.", "Descrição", "Edit", "Ver"]
        for i, t in enumerate(titulos): cols[i].write(f"**{t}**")

        selecionados = []
        for _, row in df.iterrows():
            c = st.columns([0.4, 0.6, 1.0, 1.2, 1.2, 0.8, 3.0, 0.6, 0.6])
            if c[0].checkbox("", key=f"sel_{row['id']}"): selecionados.append(row['id'])
            c[1].write(row['id'])
            c[2].write(row['data'])
            c[3].write(row.get('dominio', ''))
            c[4].write(row.get('origem', ''))
            c[5].write(row['complexidade'])
            c[6].write(row['descricao'][:65] + "...")
            
            if c[7].button("📝", key=f"ed_{row['id']}"): st.session_state[f"modo_ed_{row['id']}"] = True
            if c[8].button("🔍", key=f"vw_{row['id']}"): st.info(row['mapeamento_ia'])

            # Formulário de edição rápida
            if st.session_state.get(f"modo_ed_{row['id']}", False):
                with st.form(f"f_edit_{row['id']}"):
                    n_desc = st.text_area("Editar Descrição:", value=row['descricao'])
                    if st.form_submit_button("Salvar"):
                        supabase.table("registros").update({"descricao": n_desc}).eq("id", row['id']).execute()
                        st.session_state[f"modo_ed_{row['id']}"] = False
                        st.rerun()
        
        if selecionados and st.button("🔴 Excluir Itens Selecionados"):
            supabase.table("registros").delete().in_("id", selecionados).execute()
            st.rerun()
    else:
        st.info("Nenhuma atividade registrada ainda.")

# --- ABA 3: PERFIL E CATÁLOGO DE CONHECIMENTO ---
with tab_perf:
    sub_perf, sub_cat = st.tabs(["👤 Perfil & Equipe", "📚 Catálogo de Inteligência"])
    
    with sub_perf:
        perfil = carregar_perfil_base()
        equipe = carregar_equipe()
        c_cad, c_vis = st.columns([1, 1.3])
        
        with c_cad:
            with st.expander("👤 Meu Perfil Profissional", expanded=True):
                with st.form("f_perfil"):
                    n_p = st.text_input("Nome:", value=perfil.get('nome_profissional', ''))
                    c_p = st.text_input("Cargo:", value=perfil.get('cargo', ''))
                    m_p = st.text_area("Metas Estratégicas:", value=perfil.get('metas_estrategicas', ''))
                    if st.form_submit_button("Atualizar Perfil"):
                        supabase.table("perfil_contexto").upsert({"id": 1, "nome_profissional": n_p, "cargo": c_p, "metas_estrategicas": m_p}).execute()
                        st.rerun()
            
            st.write("### 👥 Gestão de Equipe")
            with st.form("f_add_eq", clear_on_submit=True):
                en = st.text_input("Nome:"); ec = st.text_input("Cargo:"); ee = st.text_input("E-mail:")
                ep = st.selectbox("Posição:", ["Superior", "Mesmo Nível (Par)", "Subordinado", "Prestador de Serviço"])
                if st.form_submit_button("Adicionar à Equipe"):
                    supabase.table("equipe_organograma").insert({"nome": en, "cargo": ec, "email": ee, "posicao": ep}).execute()
                    st.rerun()

        with c_vis:
            st.write("### 🌲 Organograma Dinâmico")
            def card(n, c, e, color, stl="solid"):
                st.markdown(f'<div style="border:1px {stl} #ddd; border-radius:10px; padding:12px; margin-bottom:8px; background:{color}; border-left:6px {stl} #ff4b4b;"><b>{n.upper()}</b><br><small>{c}</small><br><code>{e}</code></div>', unsafe_allow_html=True)
            
            for m in [x for x in equipe if x['posicao'] == "Superior"]: card(m['nome'], m['cargo'], m['email'], "#eef7fa")
            card(perfil.get('nome_profissional', 'Você'), perfil.get('cargo', 'Seu Cargo'), "E-mail Principal", "#fff4f4")
            for m in [x for x in equipe if x['posicao'] == "Subordinado"]: card(m['nome'], m['cargo'], m['email'], "#f1fff1")
            for m in [x for x in equipe if x['posicao'] == "Prestador de Serviço"]: card(m['nome'], m['cargo'], m['email'], "#f8f9fa", "dashed")

    with sub_cat:
        st.subheader("📚 Base de Conhecimento Catalogada")
        with st.expander("🆕 Integrar Novo PDF Técnico (Estatutos, Normas, Atas)"):
            up_f = st.file_uploader("Selecione o arquivo:", type="pdf")
            if up_f and st.button("🚀 Processar com Inteligência"):
                with st.spinner("Limpando OCR e gerando entendimento..."):
                    txt_bruto = extrair_texto_pdf(up_f)
                    entendimento = analisar_documento_estrategico(txt_bruto)
                    try:
                        supabase.table("documentos_conhecimento").insert({
                            "titulo": up_f.name,
                            "resumo_ia": entendimento,
                            "conteudo_completo": txt_bruto[:10000]
                        }).execute()
                        st.success("Documento absorvido!"); st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: Verifique as colunas do banco. {e}")

        docs = carregar_documentos()
        if docs:
            for d in docs:
                with st.container():
                    c_info, c_del = st.columns([5, 1])
                    c_info.markdown(f"**📄 {d['titulo']}**")
                    with c_info.expander("🔍 Ver Entendimento da IA"):
                        st.info(d['resumo_ia'])
                    if c_del.button("🗑️", key=f"del_doc_{d['id']}"):
                        supabase.table("documentos_conhecimento").delete().eq("id", d['id']).execute()
                        st.rerun()
                    st.divider()

# --- ABA 4: CONFIGURAÇÕES DO SISTEMA ---
with tab_conf:
    st.subheader("⚙️ Configurações FECD")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("### Categorias")
        n_c = st.text_input("Nova Cat:")
        if st.button("Add Cat") and n_c: 
            supabase.table("categorias").insert({"nome": n_c}).execute(); st.rerun()
        for x in carregar_categorias(): st.caption(f"• {x['nome']}")
    with c2:
        st.write("### Origens")
        n_o = st.text_input("Nova Ori:")
        if st.button("Add Ori") and n_o: 
            supabase.table("origens").insert({"nome": n_o}).execute(); st.rerun()
        for x in carregar_origens(): st.caption(f"• {x['nome']}")
    with c3:
        st.write("### Chaves Groq")
        n_k = st.text_input("Nova API Key:", type="password")
        if st.button("Salvar Chave") and n_k.startswith("gsk_"): 
            supabase.table("config_chaves").insert({"chave": n_k}).execute(); st.rerun()
