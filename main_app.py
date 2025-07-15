# main_app.py
import streamlit as st
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_mic_recorder import mic_recorder

import database_utils
import openai_utils

# --- FUNÇÃO CENTRAL DE PROCESSAMENTO ---
def processar_gasto(prompt_text):
    """Função central para processar um texto de gasto, seja de texto ou áudio."""
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

# --- CONFIGURAÇÃO DA PÁGINA E INICIALIZAÇÃO DO BANCO ---
st.set_page_config(page_title="Agente Financeiro", layout="wide")
database_utils.init_db()
st.title("🤖 Seu Agente Financeiro Pessoal")
st.caption(f"Hoje é {datetime.now().strftime('%d/%m/%Y')}")

# --- CATEGORIAS GLOBAIS ---
CATEGORIES = ["Diversão", "Moradia", "Carro", "Supermercado", "Saúde", "Contas", "Educação", "Outros"]

# --- SIDEBAR (BARRA LATERAL) ---
with st.sidebar:
    st.header("Modo de Uso")
    app_mode = st.radio("Selecione o modo de uso:", ("Individual", "Casal"), horizontal=True, key="app_mode_selector")
    if app_mode == "Casal":
        st.subheader("Nomes do Casal")
        p1_name_saved = database_utils.load_setting('person1_name', 'Pessoa 1')
        p2_name_saved = database_utils.load_setting('person2_name', 'Pessoa 2')
        person1_name = st.text_input("Nome da Pessoa 1", value=p1_name_saved, key="person1_name_input")
        person2_name = st.text_input("Nome da Pessoa 2", value=p2_name_saved, key="person2_name_input")
        if st.button("Salvar Nomes", use_container_width=True):
            database_utils.save_setting('person1_name', person1_name)
            database_utils.save_setting('person2_name', person2_name)
            st.success("Nomes salvos com sucesso!")
    else:
        person1_name = "Eu"
        person2_name = ""

    st.divider()

    # --- NOVA SEÇÃO DE GRAVAÇÃO DE ÁUDIO NA SIDEBAR ---
    st.header("🎙️ Gravar Gasto por Áudio")
    audio_info = mic_recorder(
        start_prompt="▶️ Clique para Gravar",
        stop_prompt="⏹️ Clique para Parar",
        key='recorder'
    )
    if audio_info and audio_info['bytes']:
        audio_bytes = audio_info['bytes']
        with st.spinner("Transcrevendo áudio..."):
            transcribed_text = openai_utils.transcribe_audio(audio_bytes)
            if transcribed_text:
                st.info(f"Texto transcrito: \"{transcribed_text}\"")
                processar_gasto(transcribed_text)
            else:
                st.error("Não foi possível transcrever. Tente novamente.")
    
    st.divider()

    st.header("Configurações de Orçamento")
    budget = st.number_input("Defina seu orçamento mensal TOTAL (R$)", min_value=0.0, value=3000.0, step=100.0)
    with st.expander("Orçamento por Categoria", expanded=False): # Começa fechado para economizar espaço
        saved_budgets = database_utils.load_category_budgets(CATEGORIES)
        category_budgets = {}
        for category in CATEGORIES:
            category_budgets[category] = st.number_input(f"Limite para {category} (R$)", min_value=0.0, value=saved_budgets.get(category, 0.0), step=50.0, key=f"budget_{category}")
        if st.button("Salvar Limites", use_container_width=True, type="primary"):
            if database_utils.save_category_budgets(category_budgets):
                st.success("Limites salvos!")
                st.rerun()

# --- ESTRUTURA DE ABAS ---
tab1, tab2 = st.tabs(["💬 Registro e Histórico", "📊 Análise de Gastos"])

# --- ABA 1: REGISTRO E HISTÓRICO ---
with tab1:
    st.header("Registro de Despesas")
    if 'pending_expense' in st.session_state and st.session_state.pending_expense:
        exp = st.session_state.pending_expense
        st.info(f"Despesa detectada: **{exp['descricao']}** - **R${exp['valor']:.2f}**")
        if app_mode == "Casal":
            payer_options = [person1_name, person2_name, "Ambos"]
            payer = st.selectbox("Quem pagou?", options=payer_options, key="payer_select")
            split_p1, split_p2 = 0, 0
            if payer == person1_name: split_p1 = 100
            elif payer == person2_name: split_p2 = 100
            else:
                split_p1 = st.slider(f"Divisão para {person1_name} (%)", 0, 100, 50, key="split_slider")
                split_p2 = 100 - split_p1
                st.write(f"Divisão para {person2_name}: {split_p2}%")
        if st.button("Confirmar e Salvar Gasto", type="primary"):
            if app_mode == "Individual":
                success, msg = database_utils.add_expense(exp['descricao'], exp['valor'], exp['categoria'], pagador=person1_name)
            else:
                success, msg = database_utils.add_expense(exp['descricao'], exp['valor'], exp['categoria'], pagador=payer, split_p1=split_p1, split_p2=split_p2)
            if success:
                st.success(msg)
                del st.session_state.pending_expense
                st.rerun()
            else:
                st.error(msg)
    else:
        st.info("Use o gravador na barra lateral ou digite um gasto no chat abaixo.")

    st.divider()
    st.header("Histórico da Conversa")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# --- ABA 2: ANÁLISE DE GASTOS ---
with tab2:
    st.header("Análise Detalhada de Gastos")
    distinct_months = database_utils.get_distinct_months()
    if not distinct_months: st.info("Ainda não há dados para analisar.")
    else:
        selected_month = st.selectbox("Selecione o Mês para Análise", options=distinct_months)
        expenses_df, total_spent = database_utils.get_monthly_expenses(selected_month)
        if expenses_df.empty: st.write("Nenhuma despesa registrada para o mês selecionado.")
        else:
            st.metric(label=f"Gasto Total em {selected_month}", value=f"R$ {total_spent:.2f}")
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
                st.text("Gastos por Categoria"); category_spending_pie = expenses_df.groupby('Categoria')['Valor'].sum().reset_index(); fig_pie = px.pie(category_spending_pie, names='Categoria', values='Valor', hole=.3); fig_pie.update_traces(textposition='inside', textinfo='percent+label'); st.plotly_chart(fig_pie, use_container_width=True)
            with col2:
                st.text("Gasto vs. Orçamento por Categoria"); category_spending_bar = expenses_df.groupby('Categoria')['Valor'].sum(); budget_df = pd.DataFrame(list(category_budgets.items()), columns=['Categoria', 'Orçamento']); analysis_df = budget_df.set_index('Categoria'); analysis_df['Gasto'] = category_spending_bar; analysis_df = analysis_df.fillna(0).reset_index(); fig_bar = go.Figure(); fig_bar.add_trace(go.Bar(x=analysis_df['Categoria'], y=analysis_df['Gasto'], name='Gasto Real', marker_color='indianred')); fig_bar.add_trace(go.Scatter(x=analysis_df['Categoria'], y=analysis_df['Orçamento'], name='Orçamento Definido', mode='lines+markers', line=dict(color='royalblue', dash='dash'))); st.plotly_chart(fig_bar, use_container_width=True)
            
            st.divider()
            
            st.subheader("🗑️ Deletar uma Despesa"); expense_options = [f"ID: {row.id} | {row.Data} | {row.Descrição} ({row.Categoria}) - R${row.Valor:.2f}" for index, row in expenses_df.iterrows()]; selected_expense_str = st.selectbox("Selecione a despesa para deletar", options=expense_options)
            if st.button("Deletar Despesa Selecionada", type="primary"):
                if selected_expense_str:
                    expense_id_to_delete = int(selected_expense_str.split(' ')[1])
                    if database_utils.delete_expense(expense_id_to_delete): st.success(f"Despesa ID {expense_id_to_delete} deletada com sucesso!"); st.rerun()

# --- BLOCO DO CHAT INPUT (NO NÍVEL PRINCIPAL DO SCRIPT) ---
if 'pending_expense' not in st.session_state or not st.session_state.pending_expense:
    if prompt := st.chat_input("Ou digite o gasto aqui..."):
        processar_gasto(prompt)