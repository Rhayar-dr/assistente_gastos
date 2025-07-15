# main_app.py
import streamlit as st
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

import database_utils
import openai_utils

# --- SETUP INICIAL E CATEGORIAS ---
st.set_page_config(page_title="Agente Financeiro", layout="wide")
CATEGORIES = ["Diversão", "Moradia", "Carro", "Supermercado", "Saúde", "Contas", "Educação", "Outros"]

# --- LÓGICA DE AUTENTICAÇÃO ---
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config['preauthorized']
)

# Renderiza o formulário de login na área principal
authenticator.login()

# --- CONTEÚDO PRINCIPAL DO APP (APENAS PARA USUÁRIOS LOGADOS) ---
if st.session_state["authentication_status"]:
    
    # --- INICIALIZAÇÃO PÓS-LOGIN ---
    username = st.session_state["username"]
    database_utils.init_db() # Garante que as tabelas existem no Azure

    st.title(f"🤖 Bem-vindo(a), {st.session_state['name']}!")
    st.caption(f"Hoje é {datetime.now().strftime('%d/%m/%Y')}, Porto Alegre.")

    # --- FUNÇÃO CENTRAL DE PROCESSAMENTO (agora precisa do username) ---
    def processar_gasto(prompt_text, user):
        if "messages" not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append({"role": "user", "content": prompt_text})
        
        with st.spinner("Analisando despesa..."):
            analysis = openai_utils.analyze_expense_text(prompt_text, CATEGORIES)
            if "descricao" in analysis and "valor" in analysis:
                st.session_state.pending_expense = {"descricao": analysis['descricao'], "valor": float(analysis['valor']), "categoria": analysis.get('categoria', 'Outros')}
                st.session_state.messages.append({"role": "assistant", "content": "Ótimo! Agora, por favor, preencha os detalhes do pagamento acima."})
            else:
                st.session_state.messages.append({"role": "assistant", "content": "Desculpe, não consegui processar. Tente de novo incluindo o item e o valor."})
        st.rerun()

    # --- SIDEBAR (agora usa o username em todas as chamadas de banco) ---
    with st.sidebar:
        authenticator.logout('Logout', 'main', key='logout_button')
        st.divider()

        st.header("Modo de Uso")
        # Carrega a última configuração salva para o modo de uso
        saved_app_mode = database_utils.load_setting(username, 'app_mode', 'Individual')
        app_mode_index = 0 if saved_app_mode == 'Individual' else 1
        app_mode = st.radio("Selecione o modo de uso:", ("Individual", "Casal"), index=app_mode_index, horizontal=True)
        # Salva a configuração sempre que ela muda
        database_utils.save_setting(username, 'app_mode', app_mode)

        if app_mode == "Casal":
            st.subheader("Nomes do Casal")
            p1_name_saved = database_utils.load_setting(username, 'person1_name', 'Pessoa 1')
            p2_name_saved = database_utils.load_setting(username, 'person2_name', 'Pessoa 2')
            person1_name = st.text_input("Nome da Pessoa 1", value=p1_name_saved)
            person2_name = st.text_input("Nome da Pessoa 2", value=p2_name_saved)
            if st.button("Salvar Nomes", use_container_width=True):
                database_utils.save_setting(username, 'person1_name', person1_name)
                database_utils.save_setting(username, 'person2_name', person2_name)
                st.success("Nomes salvos!")
                st.rerun()
        else:
            person1_name, person2_name = "Eu", ""

        st.divider()
        st.header("Configurações de Orçamento")
        budget = st.number_input("Orçamento mensal TOTAL (R$)", min_value=0.0, value=3000.0)
        with st.expander("Orçamento por Categoria", expanded=False):
            saved_budgets = database_utils.load_category_budgets(username, CATEGORIES)
            category_budgets = {}
            for category in CATEGORIES:
                category_budgets[category] = st.number_input(f"{category} (R$)", value=saved_budgets.get(category, 0.0), key=f"budget_{category}")
            if st.button("Salvar Limites", use_container_width=True, type="primary"):
                database_utils.save_category_budgets(username, category_budgets)
                st.success("Limites salvos!")

    # --- ESTRUTURA DE ABAS ---
    tab1, tab2 = st.tabs(["💬 Registro e Histórico", "📊 Análise de Gastos"])

    with tab1:
        st.header("Registro de Despesas")
        if 'pending_expense' in st.session_state and st.session_state.pending_expense:
            exp = st.session_state.pending_expense
            st.info(f"Despesa detectada: **{exp['descricao']}** - **R${exp['valor']:.2f}**")
            if app_mode == "Casal":
                payer_options = [person1_name, person2_name, "Ambos"]
                payer = st.selectbox("Quem pagou?", options=payer_options)
                split_p1, split_p2 = 0, 0
                if payer == person1_name: split_p1 = 100
                elif payer == person2_name: split_p2 = 100
                else:
                    split_p1 = st.slider(f"Divisão para {person1_name} (%)", 0, 100, 50)
                    split_p2 = 100 - split_p1
                    st.write(f"Divisão para {person2_name}: {split_p2}%")
            if st.button("Confirmar e Salvar Gasto", type="primary"):
                if app_mode == "Individual":
                    success, msg = database_utils.add_expense(username, exp['descricao'], exp['valor'], exp['categoria'], pagador=person1_name)
                else:
                    success, msg = database_utils.add_expense(username, exp['descricao'], exp['valor'], exp['categoria'], pagador=payer, split_p1=split_p1, split_p2=split_p2)
                if success:
                    st.success(msg)
                    del st.session_state.pending_expense
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.info("Digite um gasto no chat abaixo para começar.")
        st.divider()
        st.header("Histórico da Conversa")
        if "messages" not in st.session_state:
            st.session_state.messages = []
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    with tab2:
        st.header("Análise Detalhada de Gastos")
        # Nota: a função get_distinct_months também precisa ser adaptada para aceitar 'username'
        # Assumindo que foi feito, a lógica segue:
        distinct_months = ["2025-07"] # Placeholder
        selected_month = st.selectbox("Selecione o Mês para Análise", options=distinct_months)
        expenses_df, total_spent = database_utils.get_monthly_expenses(username, selected_month)
        if expenses_df.empty: st.write("Nenhuma despesa registrada para o mês selecionado.")
        else:
            # (Restante do código da aba de análise - adaptado para passar o username)
            st.metric(f"Gasto Total em {selected_month}", f"R$ {total_spent:.2f}")
            if app_mode == "Casal" and not expenses_df['Pagador'].isnull().all():
                # Lógica do gráfico de contribuição
                ...
            st.subheader("Planilha de Despesas")
            # ...
            st.subheader("🗑️ Deletar uma Despesa")
            # ...
            if st.button("Deletar Despesa Selecionada"):
                # ...
                database_utils.delete_expense(username, expense_id_to_delete)
                # ...
    
    # --- BLOCO DO CHAT INPUT ---
    if 'pending_expense' not in st.session_state or not st.session_state.pending_expense:
        if prompt := st.chat_input("Digite o gasto aqui..."):
            processar_gasto(prompt, username)

# --- LÓGICA PARA FEEDBACK DE LOGIN ---
elif st.session_state["authentication_status"] is False:
    st.error('Username/senha incorreto')
elif st.session_state["authentication_status"] is None:
    st.warning('Por favor, insira seu username e senha para continuar')