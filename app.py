import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import requests
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gêmeo Digital - Mapeamento", page_icon="🏗️", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
# O parâmetro ttl=0 força o app a buscar dados novos sem cache de permissão
conn = st.connection("gsheets", type=GSheetsConnection, ttl=0)

# --- FUNÇÕES DE SUPORTE ---

def carregar_categorias_nuvem():
    """Busca os domínios de trabalho na aba 'Categorias' da planilha."""
    try:
        df_cat = conn.read(worksheet="Categorias")
        if not df_cat.empty and "Nome" in df_cat.columns:
            return df_cat["Nome"].dropna().astype(str).tolist()
    except:
        pass
    # Categorias padrão caso a aba esteja vazia ou inacessível
    return ["Rotina Contábil", "Auditoria", "Gestão", "Fiscal"]

def buscar_todas_as_chaves():
    """Une as chaves fixas do Secrets com as chaves extras da aba 'Config'."""
    pool = []
    # 1. Chaves dos Secrets (Segurança Máxima)
    try:
        if "GROQ_KEYS" in st.secrets:
            secret_keys = st.secrets["GROQ_KEYS"].split("\n")
            pool.extend([k.strip() for k in secret_keys if k.strip()])
    except:
        pass
    
    # 2. Chaves extras da Planilha (Aba 'Config')
    try:
        df_config = conn.read(worksheet="Config")
        if not df_config.empty and "Chaves" in df_config.columns:
            extras = df_config["Chaves"].dropna().astype(str).tolist()
            pool.extend([k.strip() for k in extras if k.strip()])
    except:
        pass
    return list(set(pool)) # Remove duplicatas

def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    """Realiza a transcrição e análise técnica via IA com rodízio de chaves."""
    chaves = buscar_todas_as_chaves()
    if not chaves: 
        return "⚠️ Nenhuma chave Groq configurada.", texto
    
    random.shuffle(chaves)
    url = "https://api.groq.com/openai/v1/chat/completions"
    url_transcreve = "https://api.groq.com/openai/v1/audio/transcriptions"
    texto_final = texto

    for chave in chaves:
        headers = {"Authorization": f"Bearer {chave}"}
        try:
            # Processamento de Áudio (Whisper)
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post(url_transcreve, headers=headers, files=files)
                if res_audio.status_code == 200:
                    texto_final = f"[Transcrição]: {res_audio.json()['text']}\n{texto}"

            # Análise de Processo (Llama 3.3)
            payload = {
                "model": "llama-3.3-70b-specdec",
                "messages": [
                    {"role": "system", "content": "Você é um Engenheiro de Processos especialista. Analise a rotina do Jhonata na FECD e mapeie a lógica operacional de forma estruturada."},
                    {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Complexidade: {complexidade}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3
            }
            res = requests.post(url, headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, json=payload)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
        except:
            continue
    return "❌ Falha técnica: Verifique as chaves ou limites da API.", texto_final

# --- INTERFACE PRINCIPAL ---
st.title("🏗️ Gêmeo Digital: Mapeamento de Inteligência")

# Criação das abas de navegação
aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Atividade", "📊 Panorama de Processos", "⚙️ Configurações"])

with aba_reg:
    with st.form("form_mapping", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        
        # Selectbox alimentado dinamicamente pela aba 'Categorias'
        lista_cats = carregar_categorias_nuvem()
        cat_sel = c2.selectbox("Domínio de Trabalho:", lista_cats)
        
        comp_sel = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho = st.text_input("Gatilho (O que disparou esta ação?):")
        audio_in = st.audio_input("Grave sua explicação (opcional)")
        descricao = st.text_area("Descrição do Processo/Tarefa:")
        
        if st.form_submit_button("Sincronizar com Nuvem"):
            if not descricao and not audio_in:
                st.warning("Por favor, forneça uma descrição ou grave um áudio.")
            else:
                with st.spinner("Engenheiro de IA analisando o processo..."):
                    analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, audio_file=audio_in)
                    
                    # Preparação do dado para salvar na 'Página1'
                    novo_registro = pd.DataFrame([{
                        "Data": data_sel.strftime("%d/%m/%Y"), 
                        "Dominio": cat_sel, 
                        "Gatilho": gatilho, 
                        "Complexidade": comp_sel, 
                        "Descricao": texto_full, 
                        "Mapeamento_IA": analise
                    }])
                    
                    try:
                        df_atual = conn.read(worksheet="Página1")
                        df_final = pd.concat([df_atual, novo_registro], ignore_index=True)
                        conn.update(worksheet="Página1", data=df_final)
                        st.success("Processo mapeado e salvo na nuvem!")
                        st.markdown(f"### 🤖 Análise Gerada:\n{analise}")
                    except Exception as e:
                        st.error(f"Erro ao salvar na planilha: {e}")

with aba_dash:
    st.subheader("📊 Histórico de Mapeamentos")
    if st.button("🔄 Atualizar Panorama"):
        st.rerun()
        
    try:
        df_view = conn.read(worksheet="Página1")
        if not df_view.empty:
            # Exibe os mais recentes primeiro
            st.dataframe(df_view.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhum registro encontrado na Página1.")
    except:
        st.error("Não foi possível carregar os dados. Verifique a aba 'Página1'.")

with aba_conf:
    st.subheader("⚙️ Painel de Controle do Analista")
    
    # --- SEÇÃO: DOMÍNIOS ---
    st.markdown("### 📁 Gerenciar Domínios (Categorias)")
    cats_atuais = carregar_categorias_nuvem()
    texto_area = st.text_area("Edite os domínios (um por linha):", value="\n".join(cats_atuais), height=150)
    
    if st.button("Salvar Domínios"):
        novas_cats = [c.strip() for c in texto_area.split("\n") if c.strip()]
        df_cats_save = pd.DataFrame({"Nome": novas_cats})
        try:
            conn.update(worksheet="Categorias", data=df_cats_save)
            st.success("Domínios atualizados na planilha!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao atualizar categorias: {e}")

    st.divider()

    # --- SEÇÃO: CHAVES ---
    st.markdown("### 🔑 Adicionar Chave Groq Extra")
    nova_key = st.text_input("Cole aqui (gsk_...):", type="password")
    
    if st.button("Atualizar Chaves"):
        if nova_key.startswith("gsk_"):
            try:
                df_config = conn.read(worksheet="Config")
                nova_linha = pd.DataFrame([{"Chaves": nova_key}])
                df_config_final = pd.concat([df_config, nova_linha], ignore_index=True)
                conn.update(worksheet="Config", data=df_config_final)
                st.success("Chave adicionada ao pool de rodízio!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar chave: {e}")
        else:
            st.error("Formato de chave inválido.")

    # Status do Pool
    total_chaves = len(buscar_todas_as_chaves())
    st.write(f"📡 Sistema operando com **{total_chaves}** chaves em rodízio.")
