# openai_utils.py
import streamlit as st
import openai
import json
import io # Necessário para tratar os bytes de áudio

# Configura a chave da API da OpenAI
openai.api_key = st.secrets["OPENAI_API_KEY"]

# --- NOVA FUNÇÃO DE TRANSCRIÇÃO ---
def transcribe_audio(audio_bytes):
    """
    Usa a API Whisper da OpenAI para transcrever um áudio.
    """
    try:
        # O Whisper precisa de um objeto 'file-like' com um nome.
        # Usamos io.BytesIO para tratar os bytes em memória como um arquivo.
        audio_file = io.BytesIO(audio_bytes)
        
        # Enviamos para a API de transcrição
        transcript = openai.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.wav", audio_file) # Passamos como uma tupla (nome, objeto_arquivo)
        )
        return transcript.text
    except Exception as e:
        print(f"Erro na transcrição do áudio: {e}")
        return None


# --- Funções existentes (sem alterações) ---

def analyze_expense_text(user_input, categories):
    category_list_str = ", ".join(categories)
    prompt = f"""
    Você é um assistente de finanças. Analise o texto do usuário para identificar uma despesa.
    O usuário irá descrever um gasto. Sua tarefa é extrair as seguintes informações:
    1. 'descricao': Um breve resumo do que foi o gasto.
    2. 'valor': O valor numérico do gasto.
    3. 'categoria': Classifique o gasto em uma das seguintes categorias: {category_list_str}.

    Se o texto não parecer ser um registro de despesa, responda com um JSON contendo "not_expense": true.
    Se for uma despesa, responda APENAS com um objeto JSON válido no seguinte formato:
    {{
      "descricao": "exemplo",
      "valor": 123.45,
      "categoria": "Uma das categorias válidas"
    }}

    Texto do usuário: "{user_input}"
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
            response_format={"type": "json_object"}
        )
        analysis = json.loads(response.choices[0].message.content)
        return analysis
    except Exception as e:
        return {"error": str(e)}

def get_financial_advice(monthly_total, budget, expenses_df):
    prompt = f"""
    Você é um consultor financeiro. Um usuário tem um orçamento mensal de R${budget:.2f}
    e já gastou R${monthly_total:.2f} este mês.

    Aqui está um resumo das despesas dele:
    {expenses_df.to_string()}

    Com base nisso, forneça 2-3 dicas práticas e amigáveis para ele gerenciar melhor seus gastos.
    Seja conciso.
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um consultor financeiro prestativo."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Desculpe, não consegui gerar as dicas no momento. Erro: {e}"