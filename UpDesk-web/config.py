"""
Arquivo de Configuração da Aplicação

Responsabilidade:
- Centralizar todas as configurações da aplicação Flask.
- Carregar informações sensíveis (como senhas de banco e chaves de API) a partir de variáveis de ambiente
  para não deixá-las expostas no código-fonte (prática de segurança).
- Utiliza a biblioteca `python-dotenv` para carregar um arquivo `.env` localmente durante o desenvolvimento.
"""
import os
import urllib.parse
from dotenv import load_dotenv

# Carrega as variáveis de ambiente definidas no arquivo .env para o ambiente atual.
load_dotenv()

# Pasta base do projeto (onde está este arquivo)
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Define as configurações da aplicação em uma classe para melhor organização."""

    # Chave secreta usada pelo Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'uma-chave-secreta-padrao-super-segura')

    # ------------------------------------------------------------------
    # ESCOLHA DO BANCO
    # ------------------------------------------------------------------
    # Por padrão, VAMOS USAR SQLITE LOCAL (updesk.db).
    # Se um dia você quiser voltar para SQL Server, é só colocar
    # USE_SQLSERVER=true no .env.
    USE_SQLSERVER = os.getenv("USE_SQLSERVER", "false").lower() == "true"

    if USE_SQLSERVER:
        # ---------------------- MODO SQL SERVER ------------------------
        DB_DRIVER = os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server')
        DB_SERVER = os.getenv('DB_SERVER')
        DB_DATABASE = os.getenv('DB_DATABASE')
        DB_UID = os.getenv('DB_UID')
        DB_PWD = os.getenv('DB_PWD')

        # Monta a connection string para o pyodbc
        connection_str = (
            f"DRIVER={{{DB_DRIVER}}};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_DATABASE};"
        )

        if DB_UID and DB_PWD:
            # Autenticação SQL
            connection_str += f"UID={DB_UID};PWD={DB_PWD};"
        else:
            # (No Mac isso não funciona bem, é mais pra Windows)
            connection_str += "Trusted_Connection=yes;"

        params = urllib.parse.quote_plus(connection_str)
        SQLALCHEMY_DATABASE_URI = f"mssql+pyodbc:///?odbc_connect={params}"

    else:
        # ---------------------- MODO SQLITE (PADRÃO) -------------------
        # Arquivo updesk.db na pasta do projeto
        SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or \
            "sqlite:///" + os.path.join(basedir, "updesk.db")

    # Desativa um recurso do SQLAlchemy para melhorar performance
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Chave da API do Google Gemini
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # --- Configurações de Upload de Arquivos ---
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}
