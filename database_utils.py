# database_utils.py
import streamlit as st
import psycopg2
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, text

# --- GERENCIAMENTO DE CONEXÃO COM CACHE ---

@st.cache_resource
def get_engine():
    """
    Cria e retorna uma conexão engine do SQLAlchemy usando cache.
    Isso evita criar novas conexões a cada interação no app.
    """
    try:
        connection_string = st.secrets['database']['connection_string']
        # SQLAlchemy prefere o dialeto 'postgresql+psycopg2'
        if connection_string.startswith("postgresql://"):
            connection_string = connection_string.replace("postgresql://", "postgresql+psycopg2://", 1)
        return create_engine(connection_string)
    except Exception as e:
        st.error(f"Erro ao criar engine de conexão: {e}")
        return None

# --- INICIALIZAÇÃO DO BANCO DE DADOS ---
def init_db():
    """Cria todas as tabelas no banco de dados se elas não existirem."""
    engine = get_engine()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    username VARCHAR(255) PRIMARY KEY, name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE, hashed_password TEXT NOT NULL
                )"""))
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS despesas (
                    id SERIAL PRIMARY KEY, username VARCHAR(255) NOT NULL, descricao TEXT NOT NULL,
                    valor REAL NOT NULL, categoria VARCHAR(255) NOT NULL, data DATE NOT NULL,
                    pagador VARCHAR(255), split_pessoa1 REAL, split_pessoa2 REAL
                )"""))
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS orcamentos_categoria (
                    username VARCHAR(255) NOT NULL, categoria VARCHAR(255) NOT NULL,
                    limite REAL NOT NULL, PRIMARY KEY (username, categoria)
                )"""))
                conn.execute(text("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    username VARCHAR(255) NOT NULL, key VARCHAR(255) NOT NULL,
                    value TEXT NOT NULL, PRIMARY KEY (username, key)
                )"""))
                conn.commit()
        except Exception as e:
            st.error(f"Erro ao inicializar tabelas: {e}")

# --- FUNÇÕES DE LEITURA COM CACHE ---

@st.cache_data
def fetch_all_users():
    """Busca todos os usuários do banco (executa apenas uma vez por sessão)."""
    engine = get_engine()
    if engine:
        with engine.connect() as conn:
            users = conn.execute(text("SELECT username, name, email, hashed_password FROM users")).fetchall()
            return [{'username': r[0], 'name': r[1], 'email': r[2], 'hashed_password': r[3]} for r in users]
    return []

@st.cache_data
def get_monthly_expenses(username, year_month):
    """Busca despesas mensais (resultado cacheado)."""
    engine = get_engine()
    if engine:
        sql = text("SELECT * FROM despesas WHERE username = :user AND TO_CHAR(data, 'YYYY-MM') = :month ORDER BY data DESC")
        df = pd.read_sql(sql, engine, params={'user': username, 'month': year_month})
        df.columns = ['id', 'username', 'Descrição', 'Valor', 'Categoria', 'Data', 'Pagador', 'Split Pessoa 1', 'Split Pessoa 2']
        return df, df['Valor'].sum()
    empty_df = pd.DataFrame(columns=['id', 'username', 'Descrição', 'Valor', 'Categoria', 'Data', 'Pagador', 'Split Pessoa 1', 'Split Pessoa 2'])
    return empty_df, 0.0

@st.cache_data
def load_category_budgets(username, categories):
    """Carrega orçamentos por categoria (resultado cacheado)."""
    engine = get_engine()
    if engine:
        sql = text("SELECT categoria, limite FROM orcamentos_categoria WHERE username = :user")
        with engine.connect() as conn:
            result = conn.execute(sql, {'user': username}).fetchall()
            budgets = {r[0]: r[1] for r in result}
            for cat in categories:
                if cat not in budgets: budgets[cat] = 0.0
            return budgets
    return {cat: 0.0 for cat in categories}

@st.cache_data
def load_setting(username, key, default_value=None):
    """Carrega uma configuração específica (resultado cacheado)."""
    engine = get_engine()
    if engine:
        sql = text("SELECT value FROM app_settings WHERE username = :user AND key = :key")
        with engine.connect() as conn:
            result = conn.execute(sql, {'user': username, 'key': key}).fetchone()
            return result[0] if result else default_value
    return default_value

# --- FUNÇÕES DE ESCRITA (NÃO USAM CACHE) ---

def add_user(username, name, email, hashed_password):
    """Adiciona um novo usuário ao banco."""
    engine = get_engine()
    sql = text("INSERT INTO users (username, name, email, hashed_password) VALUES (:user, :name, :email, :pass)")
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(sql, {'user': username, 'name': name, 'email': email, 'pass': hashed_password})
                conn.commit()
            return True, "Usuário registrado com sucesso!"
        except Exception as e:
            # Captura erros de integridade (ex: username já existe)
            return False, f"Username ou email já podem existir."
    return False, "Falha na conexão com o banco."

def add_expense(username, descricao, valor, categoria, pagador=None, split_p1=None, split_p2=None):
    """Adiciona uma nova despesa."""
    data_str = datetime.now().strftime("%Y-%m-%d")
    sql = text("INSERT INTO despesas (username, descricao, valor, categoria, data, pagador, split_pessoa1, split_pessoa2) VALUES (:user, :desc, :val, :cat, :date, :payer, :s1, :s2)")
    engine = get_engine()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(sql, {'user': username, 'desc': descricao, 'val': float(valor), 'cat': categoria, 'date': data_str, 'payer': pagador, 's1': split_p1, 's2': split_p2})
                conn.commit()
            return True, f"Despesa '{descricao}' adicionada."
        except Exception as e:
            return False, f"Erro ao adicionar despesa: {e}"
    return False, "Falha na conexão."

def delete_expense(username, expense_id):
    """Deleta uma despesa específica do usuário."""
    sql = text("DELETE FROM despesas WHERE id = :id AND username = :user")
    engine = get_engine()
    if engine:
        with engine.connect() as conn:
            result = conn.execute(sql, {'id': expense_id, 'user': username})
            conn.commit()
            return result.rowcount > 0
    return False

def save_setting(username, key, value):
    """Salva/Atualiza uma configuração usando ON CONFLICT."""
    sql = text("INSERT INTO app_settings (username, key, value) VALUES (:user, :key, :val) ON CONFLICT (username, key) DO UPDATE SET value = EXCLUDED.value")
    engine = get_engine()
    if engine:
        with engine.connect() as conn:
            conn.execute(sql, {'user': username, 'key': key, 'val': str(value)})
            conn.commit()
        return True
    return False

def save_category_budgets(username, budgets_dict):
    """Salva/Atualiza múltiplos orçamentos usando ON CONFLICT."""
    engine = get_engine()
    sql = text("INSERT INTO orcamentos_categoria (username, categoria, limite) VALUES (:user, :cat, :lim) ON CONFLICT (username, categoria) DO UPDATE SET limite = EXCLUDED.limite")
    if engine:
        with engine.connect() as conn:
            for categoria, limite in budgets_dict.items():
                conn.execute(sql, {'user': username, 'cat': categoria, 'lim': limite})
            conn.commit()
        return True
    return False