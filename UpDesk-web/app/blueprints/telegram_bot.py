# app/blueprints/telegram_bot.py
from flask import Blueprint, request, jsonify, current_app
from ..services import processar_update_telegram

# aqui usamos 'bp' para seguir o padrão dos outros blueprints
bp = Blueprint("telegram_bot", __name__, url_prefix="/api/telegram")


@bp.route("/webhook", methods=["POST"])
def webhook():
    # Log básico de segurança / debug
    current_app.logger.info("[TELEGRAM] Webhook chamado")

    update = request.get_json(silent=True) or {}
    current_app.logger.info("[TELEGRAM] Payload recebido: %s", update)

    processar_update_telegram(update)

    return jsonify(ok=True)
