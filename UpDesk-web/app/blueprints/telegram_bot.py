from flask import Blueprint, request, jsonify
from ..services import processar_update_telegram

telegram_bp = Blueprint("telegram_bot", __name__, url_prefix="/telegram")

@telegram_bp.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True) or {}
    processar_update_telegram(update)
    return jsonify(ok=True)
