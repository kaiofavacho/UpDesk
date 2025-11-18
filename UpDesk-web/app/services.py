"""
Arquivo de Serviços

Responsabilidade:
- Conter a lógica de negócio desacoplada das rotas (views).
- Lida com integrações de serviços externos, como a API do Google Gemini,
  envio de mensagens para Telegram e envio de e-mails.
- Mantém o código dos blueprints mais limpo e focado no fluxo da requisição.
"""

import os
import time
import re
import smtplib
from email.message import EmailMessage

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from flask import current_app
import markdown
import bleach
import requests
from .models import Interacao, Chamado

from .extensions import db

# Tenta importar todos os modelos; se ainda não existir TelegramMensagem
# (por exemplo, antes de rodar as migrations), o código continua funcionando.
try:
    from .models import TelegramMensagem, Chamado, Interacao, Usuario
except ImportError:
    from .models import Chamado, Interacao, Usuario  # type: ignore
    TelegramMensagem = None  # fallback para evitar crash em ambientes sem a tabela


# ====================================
#   IA - Google Gemini
# ====================================

def init_ia():
    """
    Inicializa o serviço de IA (Google Gemini) com a chave da API.
    Esta função é chamada uma vez na inicialização da aplicação (em app/__init__.py).
    """
    gemini_api_key = current_app.config.get("GEMINI_API_KEY")

    if not gemini_api_key:
        current_app.logger.error(
            "ERRO CRÍTICO: A variável de ambiente 'GEMINI_API_KEY' não foi encontrada."
        )
        return

    try:
        genai.configure(api_key=gemini_api_key)
        current_app.logger.info("Serviço de IA (Gemini) configurado com sucesso.")

        # Tenta auto-selecionar um modelo válido para generateContent
        try:
            models = genai.list_models()
            iterable = getattr(models, "models", None) or models
            prefs = ["flash", "pro", "2.5", "2.0"]
            candidates = []

            for m in iterable:
                # pega o nome do modelo
                if hasattr(m, "name"):
                    name = getattr(m, "name")
                elif isinstance(m, dict):
                    name = m.get("name")
                else:
                    name = None

                if not name:
                    continue

                # verifica se suporta generateContent
                supports = False
                try:
                    if hasattr(m, "supported_generation_methods"):
                        methods = getattr(m, "supported_generation_methods")
                        supports = "generateContent" in methods
                    elif isinstance(m, dict):
                        methods = m.get("supported_generation_methods")
                        supports = methods and "generateContent" in methods
                except Exception:
                    supports = False

                if supports:
                    candidates.append(name)

            def score(n: str) -> int:
                lower = n.lower()
                for i, p in enumerate(prefs):
                    if p in lower:
                        return i
                return len(prefs)

            if candidates:
                candidates.sort(key=score)
                chosen_full = candidates[0]
                if chosen_full.startswith("models/"):
                    chosen = chosen_full.split("/", 1)[1]
                else:
                    chosen = chosen_full
                current_app.config["GEMINI_MODEL"] = chosen
                current_app.logger.info(f"Modelo Gemini selecionado por init_ia: {chosen}")

        except Exception as me:
            current_app.logger.debug(
                f"Não foi possível auto-selecionar modelo Gemini: {me}"
            )

    except Exception as e:
        current_app.logger.error(f"Erro ao configurar a API do Gemini: {e}")


def buscar_solucao_com_ia(titulo: str, descricao: str):
    """
    Busca uma solução para um problema técnico e classifica a urgência usando a API do Google Gemini.

    Args:
        titulo (str): O título do chamado.
        descricao (str): A descrição do problema.

    Returns:
        tuple: (solucao_sugerida_str, prioridade_classificada_str)
               ou (mensagem_erro, 'Não Classificada')
    """
    prompt = f"""Aja como um especialista de suporte técnico de TI (Nível 1). Um usuário está relatando o seguinte problema:
- Título do Chamado: "{titulo}"
- Descrição do Problema: "{descricao}"

Primeiro, classifique a urgência deste chamado como 'Baixa', 'Média' ou 'Alta' com base na descrição.
Em seguida, forneça uma solução clara e em formato de passo a passo para um usuário final. 
A resposta deve ser direta e fácil de entender. Se não tiver certeza, sugira coletar mais informações que poderiam ajudar no diagnóstico.

Formato da resposta:
Urgência: [Classificação da Urgência]
Solução: [Solução detalhada em passos]
"""

    max_attempts = 2
    backoff_seconds = 1
    model_id = current_app.config.get("GEMINI_MODEL", "gemini-pro")

    for attempt in range(1, max_attempts + 1):
        try:
            model = genai.GenerativeModel(model_id)
            response = model.generate_content(prompt)
            response_text = response.text

            # Extrair urgência e solução
            urgencia_match = re.search(
                r"Urgência:\s*(Baixa|Média|Alta)", response_text, re.IGNORECASE
            )
            solucao_match = re.search(
                r"Solução:\s*(.*)", response_text, re.IGNORECASE | re.DOTALL
            )

            prioridade_classificada = (
                urgencia_match.group(1).strip() if urgencia_match else "Não Classificada"
            )
            if solucao_match:
                solucao_sugerida = solucao_match.group(1).strip()
            else:
                solucao_sugerida = response_text.replace(
                    f"Urgência: {prioridade_classificada}", ""
                ).strip()

            return solucao_sugerida, prioridade_classificada

        except Exception as e:
            current_app.logger.exception(
                f"Tentativa {attempt} - erro ao contatar a API do Gemini com modelo '{model_id}': {e}"
            )

            # quota / billing
            try:
                if isinstance(e, google_exceptions.ResourceExhausted):
                    current_app.logger.error(
                        "Erro de quota detectado (ResourceExhausted). "
                        "Verifique quotas da API 'generativelanguage.googleapis.com' no Console do GCP e se o billing está habilitado."
                    )
                    return (
                        "Não foi possível obter uma sugestão da IA no momento (limite de uso/quota). "
                        "Por favor, prossiga com a abertura do chamado.",
                        "Não Classificada",
                    )
            except Exception:
                current_app.logger.debug("Falha ao verificar tipo de exceção de quota.")

            # modelo não encontrado -> tentar escolher outro
            try:
                if isinstance(e, google_exceptions.NotFound):
                    current_app.logger.info(
                        "Modelo configurado não encontrado — consultando modelos disponíveis para selecionar um compatível."
                    )
                    try:
                        models = genai.list_models()
                        iterable = getattr(models, "models", None) or models
                        prefs = ["pro", "flash", "flash-lite", "2.5", "2.0"]
                        candidates = []

                        for m in iterable:
                            if hasattr(m, "name"):
                                name = getattr(m, "name")
                            elif isinstance(m, dict):
                                name = m.get("name")
                            else:
                                name = None

                            if not name:
                                continue

                            supports = False
                            try:
                                if hasattr(m, "supported_generation_methods"):
                                    methods = getattr(
                                        m, "supported_generation_methods"
                                    )
                                    supports = "generateContent" in methods
                                elif isinstance(m, dict):
                                    methods = m.get("supported_generation_methods")
                                    supports = methods and "generateContent" in methods
                            except Exception:
                                supports = False

                            if supports:
                                candidates.append(name)

                        def score(n: str) -> int:
                            lower = n.lower()
                            for i, p in enumerate(prefs):
                                if p in lower:
                                    return i
                            return len(prefs)

                        if candidates:
                            candidates.sort(key=score)
                            chosen_full = candidates[0]
                            if chosen_full.startswith("models/"):
                                chosen = chosen_full.split("/", 1)[1]
                            else:
                                chosen = chosen_full

                            current_app.config["GEMINI_MODEL"] = chosen
                            current_app.logger.info(
                                f"Modelo escolhido automaticamente: {chosen}"
                            )
                            model_id = chosen
                            time.sleep(0.5)
                            continue  # tenta de novo com o modelo novo
                    except Exception as le:
                        current_app.logger.exception(
                            f"Erro ao listar/selecionar modelos: {le}"
                        )
            except Exception:
                current_app.logger.debug(
                    "Falha ao verificar tipo de exceção NotFound para modelos."
                )

            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)

    current_app.logger.error(
        "Todas as tentativas para consultar a IA falharam. Usando fallback textual."
    )
    fallback_message = (
        "Não foi possível obter uma sugestão da IA no momento. "
        "Por favor, prossiga com a abertura do chamado."
    )
    return fallback_message, "Não Classificada"


def format_solucao(solucao_texto: str) -> str:
    """
    Formata a solução retornada pela IA em HTML seguro.

    - Converte Markdown (ou texto com **negritos**, listas, etc.) para HTML.
    - Sanitiza o HTML resultante com bleach para evitar XSS.

    Retorna uma string HTML segura pronta para ser inserida no template com |safe.
    """
    if not solucao_texto:
        return ""

    # Normalizar quebras de linha
    text = solucao_texto.replace("\r\n", "\n").replace("\r", "\n")

    # Substitui três ou mais asteriscos por dois (Markdown ainda trata como ênfase)
    text = re.sub(r"\*{3,}", "**", text)

    # Converter Markdown para HTML
    try:
        html = markdown.markdown(text, extensions=["extra", "sane_lists"])
    except Exception:
        html = "<p>" + bleach.clean(text) + "</p>"

    allowed_tags = [
        "a",
        "abbr",
        "acronym",
        "b",
        "blockquote",
        "code",
        "em",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "strong",
        "ul",
        "br",
        "hr",
        "h1",
        "h2",
        "h3",
        "h4",
        "table",
        "thead",
        "tbody",
        "tr",
        "td",
        "th",
    ]
    allowed_attrs = {
        "*": ["class"],
        "a": ["href", "title", "rel", "target"],
        "img": ["src", "alt", "title"],
    }

    clean_html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs)
    clean_html = bleach.linkify(clean_html)

    return clean_html


# ====================================
#   Telegram + E-mail
# ====================================

def enviar_telegram(mensagem: str, chamado_id: int | None = None) -> None:
    """
    Envia uma mensagem de texto para o chat configurado no Telegram.

    Se 'chamado_id' for informado e o modelo TelegramMensagem existir,
    armazena o vínculo telegram_message_id <-> chamado_id para suportar
    resposta do Telegram de volta ao sistema.
    """
    token = current_app.config.get("TELEGRAM_BOT_TOKEN")
    chat_id = current_app.config.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        current_app.logger.warning(
            "Telegram não configurado (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID ausentes)."
        )
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": mensagem,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            current_app.logger.error(
                f"Falha ao enviar mensagem para Telegram: {resp.status_code} - {resp.text}"
            )
            return

        data = resp.json()

        # Se vier OK, tivermos um chamado_id e o modelo existir, salva o vínculo
        if (
            TelegramMensagem is not None
            and chamado_id is not None
            and data.get("ok")
            and data.get("result")
        ):
            try:
                message_id = data["result"]["message_id"]
                tm = TelegramMensagem(
                    chamado_id=chamado_id,
                    telegram_message_id=message_id,
                )
                db.session.add(tm)
                db.session.commit()
                current_app.logger.info(
                    f"Vínculo TelegramMensagem criado: chamado={chamado_id}, msg={message_id}"
                )
            except Exception as e:
                current_app.logger.exception(
                    f"Erro ao salvar vínculo TelegramMensagem: {e}"
                )

    except Exception as e:
        current_app.logger.exception(f"Erro ao enviar mensagem para Telegram: {e}")


def enviar_email(destinatario: str, assunto: str, corpo: str) -> None:
    """
    Envia um e-mail simples em texto usando SMTP configurado na aplicação.
    """
    smtp_server = current_app.config.get("SMTP_SERVER")
    smtp_port = current_app.config.get("SMTP_PORT", 587)
    smtp_username = current_app.config.get("SMTP_USERNAME")
    smtp_password = current_app.config.get("SMTP_PASSWORD")
    remetente = current_app.config.get("SMTP_FROM") or smtp_username

    if not (smtp_server and smtp_username and smtp_password):
        current_app.logger.warning(
            "SMTP não configurado corretamente (SMTP_SERVER/SMTP_USERNAME/SMTP_PASSWORD). E-mail não enviado."
        )
        return

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["To"] = destinatario
    msg.set_content(corpo)

    try:
        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
    except Exception as e:
        current_app.logger.exception(f"Erro ao enviar e-mail: {e}")


def notificar_suporte(
    mensagem: str,
    email_usuario: str,
    nome_usuario: str | None = None,
    chamado_id: int | None = None,
) -> None:
    """
    Dispara notificação de suporte:
    - envia a mensagem para o Telegram (para o time/suporte),
    - envia um e-mail de confirmação para o usuário.

    'chamado_id' é opcional; se informado, o vínculo com a mensagem do Telegram é salvo.
    """
    texto_telegram = (
        "Nova mensagem de suporte (UpDesk)\n\n"
        f"Usuário: {nome_usuario or 'N/D'}\n"
        f"E-mail: {email_usuario}\n\n"
        f"Mensagem:\n{mensagem}"
    )

    # Envia para o Telegram
    enviar_telegram(texto_telegram, chamado_id=chamado_id)

    # Monta e envia e-mail para o usuário
    assunto = "Recebemos sua mensagem - UpDesk"
    corpo = (
        f"Olá {nome_usuario or ''},\n\n"
        "Recebemos a sua mensagem de suporte no UpDesk:\n\n"
        f"{mensagem}\n\n"
        "Nossa equipe entrará em contato em breve.\n\n"
        "Atenciosamente,\nEquipe UpDesk"
    )

    enviar_email(email_usuario, assunto, corpo)

def _extrair_chamado_id_de_mensagem_telegram(message: dict) -> int | None:
    """
    Tenta extrair o ID do chamado de:
    - texto da mensagem atual
    - texto da mensagem respondida (reply_to_message)
    no padrão '#<numero>' ou '[Chamado #<numero>]'.
    """
    textos = []

    texto_atual = message.get("text")
    if texto_atual:
        textos.append(texto_atual)

    reply = message.get("reply_to_message")
    if reply and reply.get("text"):
        textos.append(reply["text"])

    for txt in textos:
        m = re.search(r"#(\d+)", txt)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass

    return None

def processar_update_telegram(update: dict) -> None:
    """
    Processa o webhook do Telegram e registra a resposta como Interacao do Chamado.
    """
    current_app.logger.info("Update Telegram recebido: %s", update)

    # Pode vir em 'message' ou 'edited_message'
    message = update.get("message") or update.get("edited_message")
    if not message:
        current_app.logger.info("Update sem campo 'message' ou 'edited_message'. Ignorando.")
        return

    texto = message.get("text")
    if not texto:
        current_app.logger.info("Mensagem Telegram sem texto. Ignorando.")
        return

    chamado_id = _extrair_chamado_id_de_mensagem_telegram(message)
    if not chamado_id:
        current_app.logger.warning(
            "Não foi possível extrair ID de chamado da mensagem Telegram: %s", texto
        )
        return

    chamado = Chamado.query.get(chamado_id)
    if not chamado:
        current_app.logger.warning(
            "Chamado %s não encontrado para mensagem Telegram.", chamado_id
        )
        return

    # Aqui você escolhe **quem** será o usuário dessa interação vinda do Telegram
    # Opção 1: usar um usuário fixo de suporte (ajuste esse ID)
    usuario_id = 1  # <<< AJUSTA AQUI para o ID do usuário "Suporte" no seu sistema

    # Se no seu modelo Chamado tiver um campo tipo 'responsavel_id', você pode preferir usar:
    # if hasattr(chamado, "responsavel_id") and chamado.responsavel_id:
    #     usuario_id = chamado.responsavel_id

    interacao = Interacao(
        chamado_id=chamado_id,
        usuario_id=usuario_id,
        mensagem=texto,
    )

    db.session.add(interacao)
    db.session.commit()

    current_app.logger.info(
        "Interação do Telegram registrada: chamado_id=%s, usuario_id=%s",
        chamado_id,
        usuario_id,
    )
