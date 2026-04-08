import streamlit as st
import pandas as pd
import datetime
import os
import requests
import random
import base64

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gêmeo Digital - Mapeamento de Processos", page_icon="🏗️", layout="wide")

# --- GERENCIAMENTO DE ARQUIVOS ---
NOME_ARQUIVO = "historico_processos.csv"
ARQUIVO_CATEGORIAS = "config_categorias.txt"
ARQUIVO_CHAVES = "config_keys.txt"

def carregar_lista(arquivo, default_list):
    if os.path.exists(arquivo):
        with open(arquivo, "r", encoding="utf-8") as f:
            return [linha.strip() for linha in f.readlines() if linha.strip()]
    return default_list

def salvar_lista(arquivo, lista):
    with open(arquivo, "w", encoding="utf-8") as f:
        for item in lista:
            f.write(item + "\n")

def encode_image(image_file):
    return base64.b64encode(image_file.read()).decode('utf-8')

# --- LÓGICA DE MAPEAMENTO DE PROCESSOS ---
def analisar_processo_ia(texto, categoria, gatilho, complexidade, imagem=None, audio_file=None):
    chaves = carregar_lista(ARQUIVO_CHAVES, ["SUA_CHAVE_AQUI"])
    if not chaves: return "Erro: Configure as chaves API.", texto
    
    random.shuffle(chaves)
    url = "https://api.groq.com/openai/v1/chat/completions"
    url_transcreve = "https://api.groq.com/openai/v1/audio/transcriptions"
    
    texto_final = texto

    for chave in chaves:
        headers = {"Authorization": f"Bearer {chave}"}
        try:
            # 1. Transcrição se houver áudio
            if audio_file:
                files = {"file": ("audio.wav", audio_file, "audio/wav"), "model": (None, "whisper-large-v3")}
                res_audio = requests.post(url_transcreve, headers=headers, files=files)
                if res_audio.status_code == 200:
                    texto_final = f"[Transcrição]: {res_audio.json()['text']}\n{texto}"

            # 2. Análise de Processo
            model = "llama-3.2-11b-vision-preview" if imagem else "llama-3.3-70b-specdec"
            
            prompt_sistema = (
                "Você é um Engenheiro de Processos e Auditor de Sistemas. Sua função é mapear a inteligência operacional do Jhonata na FECD. "
                "Para cada log, você deve: 1. Identificar a posição desta tarefa no fluxo de trabalho (Início, Meio ou Fim). "
                "2. Extrair a 'Regra de Ouro' (a lógica contábil/gestora usada). "
                "3. Avaliar o impacto sistêmico na fundação se essa tarefa falhar. "
                "Seja analítico e estruturado."
            )

            content = [{"type": "text", "text": f"CATEGORIA: {categoria}\nGATILHO: {gatilho}\nCOMPLEXIDADE: {complexidade}\nDETALHES: {texto_final}"}]
            if imagem:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_image(imagem)}"}})

            payload = {
                "model": model,
                "messages": [{"role": "system", "content": prompt_sistema}, {"role": "user", "content": content}],
                "temperature": 0.3
            }

            res = requests.post(url, headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}, json=payload)
            if res.status_code == 200:
                return res.json()['choices'][0]['message']['content'], texto_final
            elif res.status_code == 429: continue
        except: continue
    return "Falha na análise.", texto_final

# --- INTERFACE ---
st.title("🏗️ Gêmeo Digital: Mapeamento de Inteligência")

aba_reg, aba_dash, aba_conf = st.tabs(["📝 Mapear Atividade", "📊 Panorama de Processos", "⚙️ Configurações"])

with aba_reg:
    with st.form("form_processo"):
        c1, c2, c3 = st.columns([1,1,1])
        data_sel = c1.date_input("Data:", value=datetime.date.today())
        cat_sel = c2.selectbox("Domínio:", carregar_lista(ARQUIVO_CATEGORIAS, ["Financeiro", "Auditoria", "Fiscal", "RH"]))
        comp_sel = c3.select_slider("Complexidade Cognitiva:", options=["Baixa", "Média", "Alta", "Crítica"])
        
        gatilho = st.text_input("Gatilho (O que iniciou essa demanda?):", placeholder="Ex: E-mail da BDO, Pendência no DARM, Reunião de Diretoria...")
        
        st.write("🎤 **Entrada por Voz**")
        audio_in = st.audio_input("Explique a lógica da sua decisão")
        
        foto = st.file_uploader("📸 Evidência Visual (Opcional)", type=["jpg", "png"])
        descricao = st.text_area("✍️ Descrição do Fluxo de Trabalho:", height=100)
        
        submit = st.form_submit_button("Registrar no Mapa de Inteligência")

    if submit:
        with st.spinner("Mapeando processo..."):
            analise, texto_full = analisar_processo_ia(descricao, cat_sel, gatilho, comp_sel, imagem=foto, audio_file=audio_in)
            
            novo_log = pd.DataFrame({
                "Data": [data_sel.strftime("%d/%m/%Y")],
                "Dominio": [cat_sel],
                "Gatilho": [gatilho],
                "Complexidade": [comp_sel],
                "Descricao": [texto_full],
                "Mapeamento_IA": [analise]
            })
            novo_log.to_csv(NOME_ARQUIVO, mode='a', header=not os.path.exists(NOME_ARQUIVO), index=False)
            st.success("Inteligência Mapeada!")
            st.markdown(f"### 🧬 DNA do Processo:\n{analise}")

with aba_dash:
    if os.path.exists(NOME_ARQUIVO):
        df = pd.read_csv(NOME_ARQUIVO)
        st.subheader("📚 Memória Operacional Corrente")
        
        # Mini métricas de compreensão
        total_logs = len(df)
        complexos = len(df[df['Complexidade'].isin(['Alta', 'Crítica'])])
        st.write(f"O sistema já compreende **{total_logs} etapas** do seu trabalho, sendo **{complexos} de alta complexidade**.")
        
        st.dataframe(df.iloc[::-1], use_container_width=True)
    else:
        st.info("Aguardando registros para gerar o panorama.")

with aba_conf:
    st.subheader("Configurações do Analista")
    
    # Categorias
    cats = "\n".join(carregar_lista(ARQUIVO_CATEGORIAS, []))
    new_cats = st.text_area("Domínios de Trabalho:", value=cats, height=100)
    if st.button("Salvar Domínios"):
        salvar_lista(ARQUIVO_CATEGORIAS, [c.strip() for c in new_cats.split("\n") if c.strip()])
        st.rerun()
        
    # Chaves
    keys = "\n".join(carregar_lista(ARQUIVO_CHAVES, []))
    new_keys = st.text_area("Pool de Chaves API:", value=keys, height=100)
    if st.button("Atualizar Chaves"):
        salvar_lista(ARQUIVO_CHAVES, [k.strip() for k in new_keys.split("\n") if k.strip()])
        st.rerun()
