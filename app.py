import streamlit as st
from supabase import create_client, Client
import pandas as pd
import datetime
import requests
import random
from PyPDF2 import PdfReader
import re
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image

# --- 1. CONFIGURAÇÕES DE PÁGINA E ESTILO CSS ---
st.set_page_config(
    page_title="Gestão Estratégica FECD - Jhonata Bastos",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilização para Cards, Organograma e Abas
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #f0f2f6;
        border-radius: 5px 5px 0px 0px;
        padding: 10px 20px;
    }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b !important; color: white !important; }
    
    .card-equipe {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 12px;
        background-color: #ffffff;
        border-left: 5px solid #ff4b4b;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .status-ia-falha {
        background-color: #ffe5e5;
        color: #b71c1c;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #ffbaba;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONEXÃO COM SUPABASE ---
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

# --- 3. FUNÇÕES DE ACESSO A DADOS (CRUD COMPLETO) ---

def carregar_dados(tabela, ordem="nome"):
    try:
        res = supabase.table(tabela).select("*").order(ordem).execute()
        return res.data if res.data else []
    except: return []

def carregar_registros():
    try:
        res = supabase.table("registros").select("*").order("created_at", desc=True).execute()
        return res.data if res.data else []
    except: return []

def carregar_perfil():
    try:
        res = supabase.table("perfil_contexto").select("*").eq("id", 1).execute()
        return res.data[0] if res.data else {"nome_profissional": "Jhonata", "cargo": "Gestor Financeiro"}
    except: return {"nome_profissional": "Jhonata", "cargo": "Gestor Financeiro"}

# --- 4. MOTOR DE INTELIGÊNCIA E TRATAMENTO DE OCR ---

def sanear_texto_ocr(texto):
    """Limpa ruídos de documentos escaneados para evitar falha na IA"""
    # Remove cabeçalhos de cartório e sequências de símbolos
    texto = re.sub(r'OFÍCIO DE NOTAS.*?RJ', '', texto, flags=re.IGNORECASE | re.DOTALL)
    texto = re.sub(r'\.{2,}', ' ', texto)
    texto = re.sub(r'_{2,}', ' ', texto)
    texto = re.sub(r'[|\\/]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def extrair_texto_pdf(file):
    try:
        # 1. Tenta extração direta de texto (PDF Digital)
        file.seek(0)
        reader = PdfReader(file)
        texto_completo = ""
        for page in reader.pages[:15]: # Processa até 15 páginas
            content = page.extract_text()
            if content: texto_completo += content + "\n"

        texto_saneado = sanear_texto_ocr(texto_completo)

        # 2. Se o texto extraído for muito curto ou inexistente, tenta OCR (PDF Escaneado/Imagem)
        if len(texto_saneado.strip()) < 150:
            file.seek(0)
            pdf_bytes = file.read()
            # Converte PDF em imagens (uma por página)
            images = convert_from_bytes(pdf_bytes, first_page=1, last_page=10)
            texto_ocr = ""
            for i, image in enumerate(images):
                # Usa tesseract com idioma português
                page_text = pytesseract.image_to_string(image, lang='por')
                texto_ocr += f"\n--- Página {i+1} ---\n{page_text}"

            texto_saneado = sanear_texto_ocr(texto_ocr)

        return texto_saneado
    except Exception as e:
        return f"Erro técnico na extração: {str(e)}"

def analisar_com_ia(texto, tipo="geral"):
    if not texto or len(texto.strip()) < 20:
        return "Erro: O documento parece estar sem texto legível (mesmo após tentativa de OCR)."

    # Busca chaves tanto no Secrets quanto no Banco de Dados
    pool_chaves = []
    if "GROQ_KEYS" in st.secrets:
        pool_chaves.extend([k.strip() for k in st.secrets["GROQ_KEYS"].split("\n") if "gsk_" in k])
    
    chaves_db = carregar_dados("config_chaves", ordem="id")
    if chaves_db:
        pool_chaves.extend([k['chave'] for k in chaves_db if "gsk_" in k['chave']])
    
    pool_chaves = list(set(pool_chaves)) # Remove duplicatas
    
    if not pool_chaves:
        return "Erro: Nenhuma chave de API configurada no sistema. Vá em Configurações."

    # Configuração de prompt conforme o contexto da FECD
    if tipo == "documento":
        prompt = "Você é um Auditor Jurídico. Analise o documento fornecido e extraia: 1. Objeto, 2. Partes/Quem assina, 3. Vigência/Prazos importantes."
    else:
        prompt = "Você é o Assistente Estratégico do Jhonata. Analise a demanda técnica e sugira os próximos passos detalhados."

    random.shuffle(pool_chaves)
    erros = []

    for chave in pool_chaves:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-specdec",
                    "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": texto[:12000]}],
                    "temperature": 0.1
                },
                timeout=30
            )
            if r.status_code == 200:
                return r.json()['choices'][0]['message']['content']
            elif r.status_code == 429:
                erros.append(f"Limite de taxa (429) na chave {chave[:10]}...")
            else:
                erros.append(f"Erro {r.status_code} na chave {chave[:10]}...")
        except Exception as e:
            erros.append(f"Falha de conexão: {str(e)}")
            continue
    
    return f"A análise falhou após tentar {len(pool_chaves)} chaves. Detalhes: " + "; ".join(erros[:2])

# --- 5. INTERFACE PRINCIPAL ---

if not supabase: st.stop()

tab_map, tab_pan, tab_perf, tab_conf = st.tabs([
    "📝 Mapear Processo", "📊 Panorama (CRUD)", "🏢 Perfil & Contexto", "⚙️ Configurações"
])

# --- ABA 1: MAPEAMENTO DE DEMANDAS ---
with tab_map:
    with st.form("form_novo_registro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        f_data = c1.date_input("Data da Atividade:", value=datetime.date.today())
        cats = [c['nome'] for c in carregar_dados("categorias")]
        f_cat = c2.selectbox("Domínio Técnico:", cats or ["Geral"])
        oris = [o['nome'] for o in carregar_dados("origens")]
        f_ori = c3.selectbox("Origem da Demanda:", oris or ["E-mail"])
        
        f_comp = st.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        f_desc = st.text_area("Descreva a demanda ou cole o texto do e-mail:", height=200)
        
        if st.form_submit_button("🚀 Sincronizar e Gerar Inteligência"):
            if f_desc:
                with st.spinner("IA processando contexto..."):
                    ana_ia = analisar_com_ia(f_desc, tipo="processo")
                    supabase.table("registros").insert({
                        "data": f_data.strftime("%Y-%m-%d"),
                        "dominio": f_cat,
                        "origem": f_ori,
                        "complexidade": f_comp,
                        "descricao": f_desc,
                        "mapeamento_ia": ana_ia
                    }).execute()
                    st.success("Atividade registrada e analisada!"); st.rerun()

# --- ABA 2: PANORAMA E GESTÃO (CRUD DETALHADO) ---
with tab_pan:
    st.subheader("📊 Gestão Central de Atividades")
    dados_reg = carregar_registros()
    
    if dados_reg:
        df_reg = pd.DataFrame(dados_reg)
        
        # Filtros rápidos
        f_col1, f_col2 = st.columns([1, 3])
        busca = f_col1.text_input("Filtrar por texto:")
        if busca: df_reg = df_reg[df_reg['descricao'].str.contains(busca, case=False)]

        st.write("---")
        # Header da Tabela Customizada
        h = st.columns([0.5, 1, 1.2, 1.5, 3.5, 0.8, 0.8])
        titulos = ["ID", "Data", "Domínio", "Origem", "Descrição", "Ações", "IA"]
        for i, t in enumerate(titulos): h[i].write(f"**{t}**")
        
        for _, row in df_reg.iterrows():
            c = st.columns([0.5, 1, 1.2, 1.5, 3.5, 0.8, 0.8])
            c[0].write(row['id'])
            c[1].write(row['data'])
            c[2].write(row.get('dominio', ''))
            c[3].write(row.get('origem', ''))
            c[4].write(row['descricao'][:100] + "...")
            
            if c[5].button("📝", key=f"edit_{row['id']}"):
                st.session_state[f"editing_{row['id']}"] = True
            
            if c[6].button("🔍", key=f"view_ia_{row['id']}"):
                st.info(f"**Análise da IA:**\n\n{row.get('mapeamento_ia', 'Sem análise.')}")

            # Modal de Edição em linha
            if st.session_state.get(f"editing_{row['id']}", False):
                with st.form(f"f_edit_{row['id']}"):
                    nova_desc = st.text_area("Editar Descrição:", value=row['descricao'])
                    col_ed1, col_ed2 = st.columns(2)
                    if col_ed1.form_submit_button("✅ Salvar"):
                        supabase.table("registros").update({"descricao": nova_desc}).eq("id", row['id']).execute()
                        st.session_state[f"editing_{row['id']}"] = False; st.rerun()
                    if col_ed2.form_submit_button("🗑️ Excluir"):
                        supabase.table("registros").delete().eq("id", row['id']).execute()
                        st.rerun()
    else:
        st.info("Nenhuma atividade encontrada.")

# --- ABA 3: PERFIL, EQUIPE E BASE JURÍDICA ---
with tab_perf:
    col_l, col_r = st.columns([1, 1.3])
    
    with col_l:
        st.subheader("👤 Perfil & Organograma")
        p_data = carregar_perfil()
        with st.expander("Meus Dados Profissionais", expanded=False):
            with st.form("f_perfil"):
                n_p = st.text_input("Nome:", value=p_data.get('nome_profissional', ''))
                c_p = st.text_input("Cargo:", value=p_data.get('cargo', ''))
                if st.form_submit_button("Atualizar Perfil"):
                    supabase.table("perfil_contexto").upsert({"id": 1, "nome_profissional": n_p, "cargo": c_p}).execute(); st.rerun()

        st.write("### 👥 Gestão de Equipe")
        with st.form("f_equipe", clear_on_submit=True):
            e_n = st.text_input("Nome:"); e_c = st.text_input("Cargo:"); e_e = st.text_input("E-mail:")
            e_p = st.selectbox("Posição:", ["Superior", "Par", "Subordinado", "Prestador de Serviço"])
            if st.form_submit_button("Adicionar Membro"):
                supabase.table("equipe_organograma").insert({"nome": e_n, "cargo": e_c, "email": e_e, "posicao": e_p}).execute(); st.rerun()
        
        # Renderização do Organograma em Cards Profissionais
        membros = carregar_dados("equipe_organograma", ordem="posicao")
        for m in membros:
            st.markdown(f"""
            <div class="card-equipe">
                <div style="font-size: 1.1em; font-weight: bold; color: #333;">{m['nome']}</div>
                <div style="color: #666; font-size: 0.9em;">{m['cargo']} — <span style="color: #ff4b4b;">{m['posicao']}</span></div>
                <div style="color: #888; font-size: 0.85em; margin-top: 5px;">{m['email']}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Remover {m['nome'].split()[0]}", key=f"rem_eq_{m['id']}"):
                supabase.table("equipe_organograma").delete().eq("id", m['id']).execute(); st.rerun()

    with col_r:
        st.subheader("📚 Base de Conhecimento (PDFs)")
        with st.expander("📥 Integrar Novo Estatuto ou Ata", expanded=True):
            f_pdf = st.file_uploader("Selecione o arquivo PDF:", type="pdf")
            if f_pdf and st.button("Processar Inteligência 🚀"):
                with st.spinner("Extraindo e Saneando OCR..."):
                    texto_pdf = extrair_texto_pdf(f_pdf)
                    resumo = analisar_com_ia(texto_pdf, tipo="documento")
                    try:
                        supabase.table("documentos_conhecimento").insert({
                            "titulo": f_pdf.name,
                            "resumo_ia": resumo,
                            "conteudo_completo": texto_pdf[:8000]
                        }).execute()
                        st.success("Documento catalogado com sucesso!"); st.rerun()
                    except Exception as e: st.error(f"Erro ao salvar: {e}")

        # Listagem de Documentos com Estado de IA
        docs = carregar_dados("documentos_conhecimento", ordem="created_at")
        for d in docs:
            with st.expander(f"📄 {d['titulo']}"):
                if "falhou" in d['resumo_ia'].lower():
                    st.markdown(f'<div class="status-ia-falha">{d["resumo_ia"]}</div>', unsafe_allow_html=True)
                else:
                    st.info(d['resumo_ia'])
                
                if st.button("Remover Documento", key=f"del_doc_{d['id']}"):
                    supabase.table("documentos_conhecimento").delete().eq("id", d['id']).execute(); st.rerun()

# --- ABA 4: CONFIGURAÇÕES FECD ---
with tab_conf:
    st.subheader("⚙️ Configurações do Sistema")
    c_cat, c_ori, c_api = st.columns(3)
    
    with c_cat:
        st.write("### Categorias")
        n_c = st.text_input("Nova Categoria:", key="add_cat")
        if st.button("Adicionar Cat") and n_c:
            supabase.table("categorias").insert({"nome": n_c}).execute(); st.rerun()
        for x in carregar_dados("categorias"): st.caption(f"• {x['nome']}")

    with c_ori:
        st.write("### Origens")
        n_o = st.text_input("Nova Origem:", key="add_ori")
        if st.button("Adicionar Ori") and n_o:
            supabase.table("origens").insert({"nome": n_o}).execute(); st.rerun()
        for x in carregar_dados("origens"): st.caption(f"• {x['nome']}")

    with c_api:
        st.write("### Chaves Groq")
        n_k = st.text_input("Nova API Key:", type="password", help="Insira a chave gsk_...")
        if st.button("Salvar Chave"):
            if "gsk_" in n_k:
                try:
                    supabase.table("config_chaves").insert({"chave": n_k}).execute()
                    st.success("Chave armazenada com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao gravar chave: {e}")
            else:
                st.warning("Formato de chave inválido.")
        
        st.write("---")
        st.write("**Chaves Ativas no Banco:**")
        lista_k = carregar_dados("config_chaves", ordem="id")
        for k in lista_k:
            col_k1, col_k2 = st.columns([3, 1])
            col_k1.code(f"{k['chave'][:10]}***{k['chave'][-4:]}")
            if col_k2.button("🗑️", key=f"del_k_{k['id']}"):
                supabase.table("config_chaves").delete().eq("id", k['id']).execute(); st.rerun()
