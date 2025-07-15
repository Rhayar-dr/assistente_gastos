# database_utils.py
import streamlit as st
import pyodbc
from datetime import datetime
import pandas as pd

# --- FUNÇÃO DE CONEXÃO COM AZURE SQL ---
def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados Azure SQL."""
    try:
        conn = pyodbc.connect(st.secrets['database']['connection_string'])
        return conn
    except Exception as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")
        return None

# --- INICIALIZAÇÃO DO BANCO DE DADOS ---
def init_db():
    """Cria as tabelas no Azure SQL se elas não existirem."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Tabela de Despesas com a coluna 'username'
            cursor.execute("""
            IF OBJECT_ID('dbo.despesas', 'U') IS NULL
            CREATE TABLE despesas (
                id INT IDENTITY(1,1) PRIMARY KEY,
                username NVARCHAR(255) NOT NULL,
                descricao NVARCHAR(MAX) NOT NULL,
                valor FLOAT NOT NULL,
                categoria NVARCHAR(255) NOT NULL,
                data DATE NOT NULL,
                pagador NVARCHAR(255),
                split_pessoa1 FLOAT,
                split_pessoa2 FLOAT
            )
            """)
            # Tabela de Orçamentos com a coluna 'username'
            cursor.execute("""
            IF OBJECT_ID('dbo.orcamentos_categoria', 'U') IS NULL
            CREATE TABLE orcamentos_categoria (
                username NVARCHAR(255) NOT NULL,
                categoria NVARCHAR(255) NOT NULL,
                limite FLOAT NOT NULL,
                PRIMARY KEY (username, categoria)
            )
            """)
            # Tabela de Configurações com a coluna 'username'
            cursor.execute("""
            IF OBJECT_ID('dbo.app_settings', 'U') IS NULL
            CREATE TABLE app_settings (
                username NVARCHAR(255) NOT NULL,
                key NVARCHAR(255) NOT NULL,
                value NVARCHAR(MAX) NOT NULL,
                PRIMARY KEY (username, key)
            )
            """)
            conn.commit()
        except Exception as e:
            st.error(f"Erro ao inicializar tabelas: {e}")
        finally:
            conn.close()

# --- FUNÇÕES ATUALIZADAS PARA MULTIUSUÁRIO ---

def add_expense(username, descricao, valor, categoria, data_str=None, pagador=None, split_p1=None, split_p2=None):
    if data_str is None:
        data_str = datetime.now().strftime("%Y-%m-%d")
    sql = """
    INSERT INTO despesas (username, descricao, valor, categoria, data, pagador, split_pessoa1, split_pessoa2)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(sql, username, descricao, float(valor), categoria, data_str, pagador, split_p1, split_p2)
            conn.commit()
            return True, f"Despesa '{descricao}' adicionada."
        except Exception as e:
            return False, f"Erro ao adicionar despesa: {e}"
        finally:
            conn.close()
    return False, "Falha na conexão com o banco."

def get_monthly_expenses(username, year_month=None):
    if year_month is None:
        year_month = datetime.now().strftime("%Y-%m")
    
    # FORMAT(data, 'yyyy-MM') é a forma T-SQL de formatar a data
    sql = "SELECT * FROM despesas WHERE username = ? AND FORMAT(data, 'yyyy-MM') = ? ORDER BY data DESC"
    
    conn = get_db_connection()
    if conn:
        try:
            df = pd.read_sql(sql, conn, params=[username, year_month])
            df.columns = ['id', 'username', 'Descrição', 'Valor', 'Categoria', 'Data', 'Pagador', 'Split Pessoa 1', 'Split Pessoa 2']
            total = df['Valor'].sum()
            return df, total
        except Exception as e:
            st.error(f"Erro ao buscar despesas: {e}")
        finally:
            conn.close()
            
    empty_df = pd.DataFrame(columns=['id', 'username', 'Descrição', 'Valor', 'Categoria', 'Data', 'Pagador', 'Split Pessoa 1', 'Split Pessoa 2'])
    return empty_df, 0.0


def delete_expense(username, expense_id):
    """Deleta uma despesa apenas se o ID e o username corresponderem."""
    sql = "DELETE FROM despesas WHERE id = ? AND username = ?"
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(sql, expense_id, username)
            conn.commit()
            return cursor.rowcount > 0 # Retorna True se uma linha foi deletada
        finally:
            conn.close()
    return False

def save_category_budgets(username, budgets_dict):
    """Usa a declaração MERGE do SQL Server para fazer o 'UPSERT'."""
    sql = """
    MERGE orcamentos_categoria AS target
    USING (VALUES (?, ?, ?)) AS source (username, categoria, limite)
    ON (target.username = source.username AND target.categoria = source.categoria)
    WHEN MATCHED THEN
        UPDATE SET limite = source.limite
    WHEN NOT MATCHED THEN
        INSERT (username, categoria, limite) VALUES (source.username, source.categoria, source.limite);
    """
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            for categoria, limite in budgets_dict.items():
                cursor.execute(sql, username, categoria, limite)
            conn.commit()
            return True
        finally:
            conn.close()
    return False


def load_category_budgets(username, categories):
    sql = "SELECT categoria, limite FROM orcamentos_categoria WHERE username = ?"
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(sql, username)
            budgets = {row.categoria: row.limite for row in cursor.fetchall()}
            for cat in categories:
                if cat not in budgets:
                    budgets[cat] = 0.0
            return budgets
        finally:
            conn.close()
    return {cat: 0.0 for cat in categories}


def save_setting(username, key, value):
    sql = """
    MERGE app_settings AS target
    USING (VALUES (?, ?, ?)) AS source (username, key, value)
    ON (target.username = source.username AND target.key = source.key)
    WHEN MATCHED THEN
        UPDATE SET value = source.value
    WHEN NOT MATCHED THEN
        INSERT (username, key, value) VALUES (source.username, source.key, source.value);
    """
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(sql, username, key, str(value))
            conn.commit()
            return True
        finally:
            conn.close()
    return False

def load_setting(username, key, default_value=None):
    sql = "SELECT value FROM app_settings WHERE username = ? AND key = ?"
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(sql, username, key)
            result = cursor.fetchone()
            return result.value if result else default_value
        finally:
            conn.close()
    return default_value

# (A função get_distinct_months também precisaria ser atualizada com 'WHERE username = ?')