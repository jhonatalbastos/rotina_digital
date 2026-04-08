# --- FUNÇÃO PARA CARREGAR CATEGORIAS DA NUVEM ---
def carregar_categorias_nuvem():
    try:
        df_cat = conn.read(worksheet="Categorias")
        if not df_cat.empty:
            return df_cat["Nome"].tolist()
    except:
        pass
    return ["Rotina Contábil", "Auditoria", "Gestão", "Fiscal"] # Padrão caso falhe

# --- INTERFACE NA ABA DE CONFIGURAÇÕES ---
with aba_conf:
    st.subheader("⚙️ Configurações de Inteligência")
    
    # --- GERENCIAR CATEGORIAS (DOMÍNIOS) ---
    st.markdown("### 📁 Gerenciar Domínios de Trabalho")
    lista_atual = carregar_categorias_nuvem()
    texto_categorias = st.text_area("Categorias (uma por linha):", value="\n".join(lista_atual), height=150)
    
    if st.button("Atualizar Domínios na Nuvem"):
        novas_cats = [c.strip() for c in texto_categorias.split("\n") if c.strip()]
        df_new_cats = pd.DataFrame({"Nome": novas_cats})
        conn.update(worksheet="Categorias", data=df_new_cats)
        st.success("Domínios atualizados com sucesso!")
        st.rerun()

    st.divider()

    # --- GERENCIAR CHAVES ---
    st.markdown("### 🔑 Adicionar Chave Groq Extra")
    nova_key = st.text_input("Cole a nova chave gsk_...", type="password")
    
    if st.button("Salvar Chave na Planilha"):
        if nova_key.startswith("gsk_"):
            df_config = conn.read(worksheet="Config")
            novo_key_df = pd.DataFrame([{"Chaves": nova_key}])
            df_config_final = pd.concat([df_config, novo_key_df], ignore_index=True)
            conn.update(worksheet="Config", data=df_config_final)
            st.success("Chave salva com sucesso!")
            st.rerun()
        else:
            st.error("Formato inválido.")

    st.write(f"📡 Total de chaves em rodízio: **{len(buscar_todas_as_chaves())}**")
