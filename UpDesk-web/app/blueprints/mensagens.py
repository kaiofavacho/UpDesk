from flask import Blueprint, request, jsonify, session, current_app
from ..services import notificar_suporte, enviar_telegram
from ..models import Chamado  # <- IMPORTANTE: para buscar o chamado no banco

bp = Blueprint("mensagens", __name__, url_prefix="/api")


@bp.route("/<int:chamado_id>/mensagens", methods=["POST"])
def receber_mensagem(chamado_id):
    """
    Recebe uma mensagem do chat de atendimento e:
    - Notifica o suporte via Telegram
    - (se possível) envia um e-mail de confirmação para o solicitante do chamado
    """
    data = request.get_json(silent=True) or {}

    # 1) Corpo da mensagem
    mensagem = (
        data.get("mensagem")
        or data.get("conteudo")
        or data.get("texto")
        or data.get("mensagem_usuario")
    )

    if not mensagem:
        return jsonify({"erro": "Campo de mensagem é obrigatório."}), 400

    # 2) Tenta e-mail e nome do usuário (JSON / sessão)
    email = data.get("email") or session.get("usuario_email")
    nome = data.get("nome") or session.get("usuario_nome")

    # 3) Se ainda não tiver e-mail, tenta buscar pelo chamado no banco
    if not email:
        try:
            chamado = Chamado.query.get(chamado_id)
        except Exception as e:
            chamado = None
            current_app.logger.exception(f"Erro ao buscar Chamado #{chamado_id}: {e}")

        if chamado:
            # Possíveis campos diretos no Chamado
            possiveis_emails = [
                "email",
                "email_solicitante",
                "email_usuario",
                "email_cliente",
            ]
            for attr in possiveis_emails:
                if hasattr(chamado, attr):
                    valor = getattr(chamado, attr)
                    if valor:
                        email = valor
                        break

            # Possíveis relações (chamado.solicitante, chamado.usuario, etc.)
            if not email:
                possiveis_relacoes = ["solicitante", "usuario", "cliente"]
                for rel_name in possiveis_relacoes:
                    rel = getattr(chamado, rel_name, None)
                    if rel and hasattr(rel, "email") and rel.email:
                        email = rel.email
                        if not nome and hasattr(rel, "nome"):
                            nome = rel.nome
                        break

            # Nome direto no Chamado (se existir)
            if not nome:
                for attr in ["nome_solicitante", "nome_usuario", "nome_cliente"]:
                    if hasattr(chamado, attr):
                        valor = getattr(chamado, attr)
                        if valor:
                            nome = valor
                            break

    # 4) Texto para o suporte (sempre)
    texto_base = f"[Chamado #{chamado_id}]\n{mensagem}"

    # 5) Se ainda não tiver e-mail -> não bloqueia, manda só pro Telegram
    if not email:
        current_app.logger.warning(
            "Chamada a /api/%s/mensagens sem e-mail (nem no JSON, sessão ou Chamado). "
            "Enviando apenas para o Telegram.",
            chamado_id,
        )
        try:
            enviar_telegram(texto_base + "\n\n(⚠️ E-mail do solicitante não disponível)")
        except Exception as e:
            current_app.logger.exception(
                f"Erro ao enviar mensagem para Telegram no chamado {chamado_id}: {e}"
            )
            return jsonify({"erro": "Falha ao enviar a mensagem para o suporte."}), 500

        return jsonify({
            "status": "ok",
            "mensagem": "Mensagem enviada ao suporte (sem e-mail de confirmação)."
        }), 200

    # 6) Com e-mail -> fluxo completo (Telegram + e-mail)
    try:
        notificar_suporte(texto_base, email, nome, chamado_id=chamado_id)

    except Exception as e:
        current_app.logger.exception(f"Erro ao notificar suporte no chamado {chamado_id}: {e}")
        return jsonify({"erro": "Falha ao enviar a mensagem para o suporte."}), 500

    return jsonify({
        "status": "ok",
        "mensagem": "Mensagem enviada ao suporte."
    }), 200
