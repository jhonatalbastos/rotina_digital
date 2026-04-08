import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import requests
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gêmeo Digital - Mapeamento", page_icon="🏗️", layout="wide")

# --- CONEXÃO MANUAL REFORÇADA ---
# Usamos o parâmetro 'spreadsheet' direto do segredo para evitar que ele tente adivinhar a URL
try:
    conn = st.connection("gsheets", type=GSheetsConnection, ttl=0)
except Exception as e:
    st.error(f"Erro crítico de conexão: {e}")

# --- FUNÇÕES DE SUPORTE ---

def carregar_categorias_nuvem():
    try:
        df_cat = conn.read(worksheet="Categorias", ttl=0)
        if not df_cat.empty and "Nome" in df_cat.columns:
            return [str(c).strip() for c in df_cat["Nome"].dropna().tolist() if str(c).strip()]
    except:
        pass
    # Se falhar a leitura, retorna os itens que vi na sua planilha
    return ["Rotina Contábil", "Auditoria", "Gestão", "Emergências", "Outros"]

def buscar_todas_as_chaves():
    pool = []
    if "GROQ_KEYS" in st.secrets:
        secret_keys = st.secrets["GROQ_KEYS"].split("\n")
        pool.extend([k.strip() for k in secret_keys if k.strip()])
    try:
        df_config = conn.read(worksheet="Config", ttl=0)
        if not df_config.empty and "Chaves" in df_config.columns:
            extras = df_config["Chaves"].dropna().astype(str).tolist()
            pool.extend([k.strip() for k in extras if k.strip()])
    except:
        pass
    return list(set(pool))

def analisar_processo_ia(texto, categoria, gatilho, complexidade, audio_file=None):
    chaves = buscar_todas_as_chaves()
    if not chaves: return "⚠️ Sem chaves Groq.", texto
    random.shuffle(chaves)
    url = "https://api.groq.com/openai/v1/chat/completions"
    url_transcreve = "https://api.groq.com/openai/v1/audio/transcriptions"
    texto_final = texto
    for chave in chaves:
        headers = {"Authorization": f"Bearer {chave}"}
        try:
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post(url_transcreve, headers=headers, files=files)
                if res_audio.status_code == 200:
                    texto_final = f"[Transcrição]: {res_audio.json()['text']}\n{texto}"
            payload = {
                "model": "llama-3.3-70b-specdec",
                "messages": [
                    {"role": "system", "content": "Você é um Engenheiro de Processos. Analise a rotina operacional de forma estruturada."},
                    {"role": "user", "content": f"Domínio: {categoria} | Gatilho: {gatilho} | Complexidade: {complexidade}\nDescrição: {texto_final}"}
                ],
                "temperature": 0.3
            }
            res = requests.post(url, headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, json=payload)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
        except:
            continue
    return "❌ Erro na IA.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Mapeamento de Inteligência")

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Atividade", "📊 Panorama", "⚙️ Configurações"])

with aba_reg:
    with st.form("form_mapping", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        cat_sel = c2.selectbox("Domínio:", carregar_categorias_nuvem())
        comp_sel = c3.select_slider("Complexidade:", options=["Baixa", "Média", "Alta", "Crítica"])
        gatilho = st.text_input("Gatilho:")
        audio_in = st.audio_input("Explicação por voz")
        descricao = st.text_area("Descrição do Processo:")
        
        if st.form_submit_button("Sincronizar com Nuvem"):
            with st.spinner("Analisando e salvando..."):
                analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, audio_file=audio_in)
                novo_dado = pd.DataFrame([{
                    "Data": data_sel.strftime("%d/%m/%Y"), "Dominio": cat_sel, 
                    "Gatilho": gatilho, "Complexidade": comp_sel, 
                    "Descricao": texto_full, "Mapeamento_IA": analise
                }])
                try:
                    # Lemos a planilha e anexamos o novo dado
                    df_antigo = conn.read(worksheet="Página1", ttl=0)
                    df_final = pd.concat([df_antigo, novo_dado], ignore_index=True)
                    # Forçamos o update
                    conn.update(worksheet="Página1", data=df_final)
                    st.success("✅ Processo salvo na planilha!")
                    st.markdown(f"### 🤖 Análise da IA:\n{analise}")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
                    st.info("Verifique se o e-mail da conta de serviço tem permissão de 'Editor' na planilha.")

with aba_dash:
    st.subheader("📊 Histórico de Processos")
    if st.button("🔄 Atualizar"): st.rerun()
    try:
        df_view = conn.read(worksheet="Página1", ttl=0)
        st.dataframe(df_view.iloc[::-1], use_container_width=True)
    except:
        st.info("Nenhum dado para exibir.")

with aba_conf:
    st.subheader("⚙️ Configurações")
    # Gerenciar Categorias
    st.markdown("### 📁 Domínios")
    cats_lista = carregar_categorias_nuvem()
    texto_area = st.text_area("Categorias (uma por linha):", value="\n".join(cats_lista), height=150)
    if st.button("Salvar Domínios"):
        try:
            novas = pd.DataFrame({"Nome": [c.strip() for c in texto_area.split("\n") if c.strip()]})
            conn.update(worksheet="Categorias", data=novas)
            st.success("Domínios atualizados!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro: {e}")
