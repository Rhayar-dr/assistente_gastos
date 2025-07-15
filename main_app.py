# main_app.py
import streamlit as st
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

# Utilitários locais
import database_utils
import openai_utils

# --- SETUP INICIAL E CATEGORIAS ---
st.set_page_config(page_title="Agente Financeiro", layout="wide")
CATEGORIES = ["Diversão", "Moradia", "Carro", "Supermercado", "Saúde", "Contas", "Educação", "Outros"]

# --- LÓGICA DE AUTENTICAÇÃO ---
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("Erro: Arquivo 'config.yaml' não encontrado. Por favor, crie o arquivo de configuração antes de rodar o app.")
    st.stop()


authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
    config['preauthorized']
)

# Renderiza o formulário de login
authenticator.login()

# --- CONTEÚDO PRINCIPAL DO APP (APENAS PARA USUÁRIOS LOGADOS) ---
if st.session_state["authentication_status"]:
    
    # --- INICIALIZAÇÃO PÓS-LOGIN ---
    username = st.session_state["username"]
    database_utils.init_db() # Garante que as tabelas existem no Azure

    st.title(f"🤖 Bem-vindo(a), {st.session_state['name']}!")
    st.caption(f"Hoje é {datetime.now().strftime('%d/%m/%Y')}, Porto Alegre.")

    # --- FUNÇÃO CENTRAL DE PROCESSAMENTO ---
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

    # --- SIDEBAR ---
    with st.sidebar:
        authenticator.logout('Logout', 'main', key='logout_button')
        st.divider()

        st.header("Modo de Uso")
        saved_app_mode = database_utils.load_setting(username, 'app_mode', 'Individual')
        app_mode_index = 0 if saved_app_mode == 'Individual' else 1
        app_mode = st.radio("Selecione o modo de uso:", ("Individual", "Casal"), index=app_mode_index, horizontal=True)
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
        # Nota: A função get_distinct_months em database_utils também precisa ser adaptada para usar o 'username'
        # distinct_months = database_utils.get_distinct_months(username)
        # Por enquanto, usaremos uma data fixa para evitar erros caso não tenha sido implementado
        current_month_str = datetime.now().strftime("%Y-%m")
        selected_month = st.text_input("Mês para Análise (formato AAAA-MM)", value=current_month_str)
        
        if selected_month:
            expenses_df, total_spent = database_utils.get_monthly_expenses(username, selected_month)
            if expenses_df.empty:
                st.write("Nenhuma despesa registrada para o mês selecionado.")
            else:
                st.metric(f"Gasto Total em {selected_month}", f"R$ {total_spent:.2f}")
                if app_mode == "Casal" and not expenses_df['Pagador'].isnull().all():
                    st.subheader(f"Contribuições de {person1_name} vs {person2_name}")
                    def calculate_contribution(row, person_name_to_check, split_col):
                        if row['Pagador'] == person_name_to_check: return row['Valor']
                        elif row['Pagador'] == 'Ambos' and pd.notna(row[split_col]): return row['Valor'] * (row[split_col] / 100.0)
                        return 0
                    expenses_df['Valor ' + person1_name] = expenses_df.apply(calculate_contribution, args=(person1_name, 'Split Pessoa 1'), axis=1)
                    expenses_df['Valor ' + person2_name] = expenses_df.apply(calculate_contribution, args=(person2_name, 'Split Pessoa 2'), axis=1)
                    total_p1 = expenses_df['Valor ' + person1_name].sum()
                    total_p2 = expenses_df['Valor ' + person2_name].sum()
                    contribution_data = pd.DataFrame({'Pessoa': [person1_name, person2_name], 'Valor Pago': [total_p1, total_p2]})
                    fig_contrib = px.pie(contribution_data, names='Pessoa', values='Valor Pago', title='Quem Pagou Mais no Mês', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
                    st.plotly_chart(fig_contrib, use_container_width=True)
                
                st.subheader("Planilha de Despesas")
                if app_mode == "Casal":
                    display_cols = ['Data', 'Descrição', 'Categoria', 'Valor', 'Pagador', f'Valor {person1_name}', f'Valor {person2_name}']
                    st.dataframe(expenses_df.reindex(columns=display_cols).fillna(0), use_container_width=True)
                else:
                    st.dataframe(expenses_df[['Data', 'Descrição', 'Categoria', 'Valor']], use_container_width=True)
                
                st.subheader("Análise Gráfica")
                col1, col2 = st.columns(2)
                with col1:
                    st.text("Gastos por Categoria")
                    category_spending_pie = expenses_df.groupby('Categoria')['Valor'].sum().reset_index()
                    fig_pie = px.pie(category_spending_pie, names='Categoria', values='Valor', hole=.3)
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_pie, use_container_width=True)
                with col2:
                    st.text("Gasto vs. Orçamento por Categoria")
                    category_spending_bar = expenses_df.groupby('Categoria')['Valor'].sum()
                    budget_df = pd.DataFrame(list(category_budgets.items()), columns=['Categoria', 'Orçamento'])
                    analysis_df = budget_df.set_index('Categoria')
                    analysis_df['Gasto'] = category_spending_bar
                    analysis_df = analysis_df.fillna(0).reset_index()
                    fig_bar = go.Figure()
                    fig_bar.add_trace(go.Bar(x=analysis_df['Categoria'], y=analysis_df['Gasto'], name='Gasto Real', marker_color='indianred'))
                    fig_bar.add_trace(go.Scatter(x=analysis_df['Categoria'], y=analysis_df['Orçamento'], name='Orçamento Definido', mode='lines+markers', line=dict(color='royalblue', dash='dash')))
                    st.plotly_chart(fig_bar, use_container_width=True)
                
                st.divider()
                
                st.subheader("🗑️ Deletar uma Despesa")
                expense_options = [f"ID: {row.id} | {row.Data} | {row.Descrição} ({row.Categoria}) - R${row.Valor:.2f}" for index, row in expenses_df.iterrows()]
                selected_expense_str = st.selectbox("Selecione a despesa para deletar", options=expense_options)
                if st.button("Deletar Despesa Selecionada", type="primary"):
                    if selected_expense_str:
                        expense_id_to_delete = int(selected_expense_str.split(' ')[1])
                        # A função de deleção também precisa do username para segurança
                        if database_utils.delete_expense(username, expense_id_to_delete):
                            st.success(f"Despesa ID {expense_id_to_delete} deletada com sucesso!")
                            st.rerun()

    # --- BLOCO DO CHAT INPUT ---
    if 'pending_expense' not in st.session_state or not st.session_state.pending_expense:
        if prompt := st.chat_input("Digite o gasto aqui..."):
            processar_gasto(prompt, username)

# --- LÓGICA PARA FEEDBACK DE LOGIN ---
elif st.session_state["authentication_status"] is False:
    st.error('Username/senha incorreto')
elif st.session_state["authentication_status"] is None:
    st.warning('Por favor, insira seu username e senha para continuar')