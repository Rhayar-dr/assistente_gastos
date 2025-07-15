# database_utils.py
import sqlite3
from datetime import datetime
import pandas as pd

DB_FILE = "finance_database.db"

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa o banco de dados e cria TODAS as tabelas se não existirem."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Tabela de despesas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            categoria TEXT NOT NULL,
            data DATE NOT NULL,
            pagador TEXT,
            split_pessoa1 REAL,
            split_pessoa2 REAL
        )
    """)
    # Tabela de orçamentos por categoria
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos_categoria (
            categoria TEXT PRIMARY KEY,
            limite REAL NOT NULL
        )
    """)
    # NOVA TABELA: Configurações gerais do app
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# --- Funções para Configurações Gerais (NOVO) ---

def save_setting(key, value):
    """Salva ou atualiza uma configuração específica no banco."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao salvar configuração: {e}")
        return False

def load_setting(key, default_value=None):
    """Carrega uma configuração específica do banco."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        conn.close()
        return result['value'] if result else default_value
    except Exception as e:
        print(f"Erro ao carregar configuração: {e}")
        return default_value

# --- Funções para a tabela de despesas e orçamentos (sem alterações) ---

def add_expense(descricao, valor, categoria, data_str=None, pagador=None, split_p1=None, split_p2=None):
    if data_str is None:
        data_str = datetime.now().strftime("%Y-%m-%d")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO despesas (descricao, valor, categoria, data, pagador, split_pessoa1, split_pessoa2) VALUES (?, ?, ?, ?, ?, ?, ?)", (descricao, float(valor), categoria, data_str, pagador, split_p1, split_p2))
        conn.commit()
        conn.close()
        return True, f"Despesa '{descricao}' de R${valor} adicionada."
    except Exception as e:
        return False, f"Ocorreu um erro ao adicionar a despesa: {e}"

def get_monthly_expenses(year_month=None):
    if year_month is None:
        year_month = datetime.now().strftime("%Y-%m")
    try:
        conn = get_db_connection()
        query = "SELECT id, descricao, valor, categoria, data, pagador, split_pessoa1, split_pessoa2 FROM despesas WHERE strftime('%Y-%m', data) = ? ORDER BY data DESC"
        df = pd.read_sql_query(query, conn, params=(year_month,))
        conn.close()
        if df.empty:
            return pd.DataFrame(columns=['id', 'Descrição', 'Valor', 'Categoria', 'Data', 'Pagador', 'Split Pessoa 1', 'Split Pessoa 2']), 0.0
        df.columns = ['id', 'Descrição', 'Valor', 'Categoria', 'Data', 'Pagador', 'Split Pessoa 1', 'Split Pessoa 2']
        total = df['Valor'].sum()
        return df, total
    except Exception as e:
        return pd.DataFrame(), 0.0

def get_distinct_months():
    try:
        conn = get_db_connection()
        query = "SELECT DISTINCT strftime('%Y-%m', data) as month FROM despesas ORDER BY month DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df['month'].tolist()
    except Exception as e:
        return []

def delete_expense(expense_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM despesas WHERE id = ?", (expense_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        return False

def save_category_budgets(budgets_dict):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.executemany("INSERT INTO orcamentos_categoria (categoria, limite) VALUES (?, ?) ON CONFLICT(categoria) DO UPDATE SET limite = excluded.limite", budgets_dict.items())
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        return False

def load_category_budgets(categories):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT categoria, limite FROM orcamentos_categoria")
        budgets = {row['categoria']: row['limite'] for row in cursor.fetchall()}
        conn.close()
        for cat in categories:
            if cat not in budgets:
                budgets[cat] = 0.0
        return budgets
    except Exception as e:
        return {cat: 0.0 for cat in categories}