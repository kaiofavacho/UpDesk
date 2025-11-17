"""
Ponto de Entrada da Aplicação (Entry Point)

Responsabilidade:
- Ser o script principal que é executado para iniciar a aplicação.
- Importar a função de fábrica `create_app` de dentro do pacote `app`.
- Criar a instância da aplicação.
- Iniciar o servidor de desenvolvimento do Flask quando o script é executado diretamente.
"""
import logging
from app import create_app

# Configuração básica de logging (imprime no terminal)
logging.basicConfig(
    level=logging.INFO,  # pode trocar para DEBUG se quiser mais verbosidade
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Reforça o logger do werkzeug (aquele que mostra: 127.0.0.1 - - [...] "GET /..." 200)
werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.setLevel(logging.INFO)
werkzeug_logger.disabled = False

# Chama a função de fábrica para criar e configurar a instância da aplicação Flask.
app = create_app()

if __name__ == '__main__':
    # Inicia o servidor de desenvolvimento web do Flask.
    # Coloquei debug=True pra garantir mais logs e stacktrace se der erro.
    app.run(port=5001, debug=True)
