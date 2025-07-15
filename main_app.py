# main_app.py
import streamlit as st
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities.hasher import Hasher

# Utilitários locais
import database_utils
import openai_utils

# --- CONFIGURAÇÃO DA PÁGINA E INICIALIZAÇÃO DO BANCO ---
st.set_page_config(page_title="Agente Financeiro", layout="wide")
CATEGORIES = ["Diversão", "Moradia", "Carro", "Supermercado", "Saúde", "Contas", "Educação", "Outros"]
database_utils.init_db() 

# --- FUNÇÃO OTIMIZADA PARA CARREGAR CREDENCIAIS COM CACHE ---
@st.cache_data
def load_credentials():
    """
    Busca todos os usuários do banco. O decorator @st.cache_data garante que o banco
    seja consultado apenas uma vez, ou quando o cache for limpo.
    """
    users = database_utils.fetch_all_users()
    credentials = {
        "usernames": {
            user['username']: { "name": user['name'], "email": user['email'], "password": user['hashed_password'] }
            for user in users
        }
    }
    return credentials

# Carrega as credenciais usando a função cacheada
credentials = load_credentials()

# --- LÓGICA DE AUTENTICAÇÃO (FORA DO CACHE) ---
authenticator = stauth.Authenticate(
    credentials,
    st.secrets.get("cookie", {}).get("name", "some_cookie_name"),
    st.secrets.get("cookie", {}).get("key", "some_random_key"),
    st.secrets.get("cookie", {}).get("expiry_days", 30)
)

# --- TELA DE LOGIN / REGISTRO ---
if not st.session_state.get("authentication_status"):
    col1, col2 = st.columns([1, 1.2])
    with col1:
        authenticator.login()

    with col2:
        st.subheader("Não tem uma conta?")
        with st.form("Registration Form"):
            name = st.text_input("Nome Completo", key="reg_name")
            email = st.text_input("Email", key="reg_email")
            username_reg = st.text_input("Username (para login)", key="reg_username")
            password = st.text_input("Senha", type="password", key="reg_pass")
            confirm_password = st.text_input("Confirmar Senha", type="password", key="reg_pass_confirm")
            
            if st.form_submit_button("Registrar"):
                if password == confirm_password:
                    if not all([name, email, username_reg, password]):
                        st.error("Por favor, preencha todos os campos.")
                    else:
                        hashed_password = Hasher([password]).generate()[0]
                        success, message = database_utils.add_user(username_reg, name, email, hashed_password)
                        if success:
                            st.cache_data.clear()
                            st.success(message)
                            st.info("Por favor, faça o login com suas novas credenciais.")
                        else:
                            st.error(message)
                else:
                    st.error("As senhas não coincidem.")

# --- FEEDBACK DE LOGIN ---
if st.session_state["authentication_status"] is False:
    st.error('Username/senha incorreto')

# --- CONTEÚDO PRINCIPAL DO APP (APENAS PARA USUÁRIOS LOGADOS) ---
if st.session_state["authentication_status"]:
    
    username = st.session_state["username"]

    st.title(f"🤖 Bem-vindo(a), {st.session_state['name']}!")
    
    def processar_gasto(prompt_text, user):
        if "messages" not in st.session_state: st.session_state.messages = []
        st.session_state.messages.append({"role": "user", "content": prompt_text})
        with st.spinner("Analisando..."):
            analysis = openai_utils.analyze_expense_text(prompt_text, CATEGORIES)
            if "descricao" in analysis and "valor" in analysis:
                st.session_state.pending_expense = {"descricao": analysis['descricao'], "valor": float(analysis['valor']), "categoria": analysis.get('categoria', 'Outros')}
                st.session_state.messages.append({"role": "assistant", "content": "Ótimo! Preencha os detalhes do pagamento ao lado."})
            else:
                st.session_state.messages.append({"role": "assistant", "content": "Não consegui processar. Tente de novo."})
        st.rerun()

    with st.sidebar:
        authenticator.logout('Logout', 'main')
        st.divider()
        st.header("Modo de Uso")
        saved_app_mode = database_utils.load_setting(username, 'app_mode', 'Individual')
        app_mode_index = 0 if saved_app_mode == 'Individual' else 1
        app_mode = st.radio("Selecione:", ("Individual", "Casal"), index=app_mode_index, horizontal=True)
        if app_mode != saved_app_mode:
            database_utils.save_setting(username, 'app_mode', app_mode)
            st.cache_data.clear()
            st.rerun()
        if app_mode == "Casal":
            st.subheader("Nomes do Casal")
            p1 = database_utils.load_setting(username, 'person1_name', 'Pessoa 1')
            p2 = database_utils.load_setting(username, 'person2_name', 'Pessoa 2')
            person1_name = st.text_input("Pessoa 1", value=p1)
            person2_name = st.text_input("Pessoa 2", value=p2)
            if st.button("Salvar Nomes", use_container_width=True):
                database_utils.save_setting(username, 'person1_name', person1_name)
                database_utils.save_setting(username, 'person2_name', person2_name)
                st.cache_data.clear(); st.success("Nomes salvos!"); st.rerun()
        else:
            person1_name, person2_name = "Eu", ""
        
        st.divider()
        st.header("Orçamentos")
        with st.expander("Definir por Categoria", expanded=False):
            saved_budgets = database_utils.load_category_budgets(username, CATEGORIES)
            category_budgets = {}
            for category in CATEGORIES:
                category_budgets[category] = st.number_input(f"{category}", value=saved_budgets.get(category, 0.0), key=f"budget_{category}")
            if st.button("Salvar Limites", use_container_width=True, type="primary"):
                database_utils.save_category_budgets(username, category_budgets)
                st.cache_data.clear(); st.success("Limites salvos!")

    # --- ESTRUTURA DE ABAS ---
    tab1, tab2 = st.tabs(["💬 Registro", "📊 Análise"])

    with tab1:
        col_action, col_chat = st.columns([1, 1.5]) 
        with col_chat:
            st.subheader("Histórico da Conversa")
            with st.container():
                if "messages" not in st.session_state:
                    st.session_state.messages = []
                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
        with col_action:
            st.subheader("Ação Necessária")
            if 'pending_expense' in st.session_state and st.session_state.pending_expense:
                exp = st.session_state.pending_expense
                with st.container(border=True):
                    st.info(f"Despesa: **{exp['descricao']}** - **R${exp['valor']:.2f}**")
                    if app_mode == "Casal":
                        payer = st.selectbox("Quem pagou?", [person1_name, person2_name, "Ambos"])
                        split_p1, split_p2 = (100, 0) if payer == person1_name else (0, 100) if payer == person2_name else (st.slider(f"{person1_name} (%)", 0, 100, 50), 0)
                        if payer == "Ambos": split_p2 = 100 - split_p1; st.write(f"{person2_name}: {split_p2}%")
                    if st.button("Confirmar e Salvar", type="primary", use_container_width=True):
                        pagador_to_save = person1_name if app_mode == 'Individual' else payer
                        split_p1_to_save = split_p1 if app_mode == 'Casal' else None
                        split_p2_to_save = split_p2 if app_mode == 'Casal' else None
                        success, msg = database_utils.add_expense(username, exp['descricao'], exp['valor'], exp['categoria'], pagador=pagador_to_save, split_p1=split_p1_to_save, split_p2=split_p2_to_save)
                        if success:
                            st.cache_data.clear()
                            st.success(msg)
                            del st.session_state.pending_expense
                            # A LINHA QUE APAGAVA O HISTÓRICO FOI REMOVIDA DAQUI
                            st.rerun()
                        else: st.error(msg)
            else:
                st.info("Digite um gasto no chat abaixo para que ele seja registrado e apareça aqui para confirmação.")

    with tab2:
        st.header("Análise Detalhada")
        current_month_str = datetime.now().strftime("%Y-%m")
        selected_month = st.text_input("Mês (AAAA-MM)", value=current_month_str)
        if selected_month:
            expenses_df, total_spent = database_utils.get_monthly_expenses(username, selected_month)
            if expenses_df.empty:
                st.info("Nenhuma despesa registrada para o mês selecionado.")
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
                col_graph1, col_graph2 = st.columns(2)
                with col_graph1:
                    st.text("Gastos por Categoria"); category_spending_pie = expenses_df.groupby('Categoria')['Valor'].sum().reset_index(); fig_pie = px.pie(category_spending_pie, names='Categoria', values='Valor', hole=.3); fig_pie.update_traces(textposition='inside', textinfo='percent+label'); st.plotly_chart(fig_pie, use_container_width=True)
                with col_graph2:
                    st.text("Gasto vs. Orçamento por Categoria"); category_spending_bar = expenses_df.groupby('Categoria')['Valor'].sum(); budget_df = pd.DataFrame(list(category_budgets.items()), columns=['Categoria', 'Orçamento']); analysis_df = budget_df.set_index('Categoria'); analysis_df['Gasto'] = category_spending_bar; analysis_df = analysis_df.fillna(0).reset_index(); fig_bar = go.Figure(); fig_bar.add_trace(go.Bar(x=analysis_df['Categoria'], y=analysis_df['Gasto'], name='Gasto Real', marker_color='indianred')); fig_bar.add_trace(go.Scatter(x=analysis_df['Categoria'], y=analysis_df['Orçamento'], name='Orçamento Definido', mode='lines+markers', line=dict(color='royalblue', dash='dash'))); st.plotly_chart(fig_bar, use_container_width=True)
                
                st.divider()
                st.subheader("🗑️ Deletar uma Despesa")
                expense_options = [f"ID: {row.id} | {row.Data} | {row.Descrição} ({row.Categoria}) - R${row.Valor:.2f}" for index, row in expenses_df.iterrows()]
                selected_expense_str = st.selectbox("Selecione a despesa para deletar", options=expense_options)
                if st.button("Deletar Despesa Selecionada", type="primary"):
                    if selected_expense_str:
                        expense_id_to_delete = int(selected_expense_str.split(' ')[1])
                        if database_utils.delete_expense(username, expense_id_to_delete):
                            st.cache_data.clear()
                            st.success(f"Despesa ID {expense_id_to_delete} deletada com sucesso!")
                            st.rerun()
                        else: st.error("Erro ao deletar a despesa.")
                    else: st.warning("Nenhuma despesa selecionada para deletar.")

    if 'pending_expense' not in st.session_state or not st.session_state.pending_expense:
        if prompt := st.chat_input("Digite o gasto aqui..."):
            processar_gasto(prompt, username)