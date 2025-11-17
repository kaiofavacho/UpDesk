"""
Blueprint para Gerenciamento de Chamados

Responsabilidade:
- Orquestrar todas as funcionalidades relacionadas a chamados (tickets) de suporte.
- Inclui rotas para abrir, visualizar, atender, transferir, encerrar e interagir com chamados.
- Fornece uma API para a funcionalidade de chat em tempo real.
"""
from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    make_response,
    current_app,
    flash,
)
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
from fpdf import FPDF

from ..extensions import db
from ..models import Chamado, Interacao, get_sao_paulo_time, Usuario
from ..forms import chamadoForm
from ..services import buscar_solucao_com_ia, notificar_suporte


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in current_app.config["ALLOWED_EXTENSIONS"]
    )


bp = Blueprint("chamados", __name__, url_prefix="/chamados")


# =============================================================================
# LOG DE REQUEST / RESPONSE PARA A API DE MENSAGENS
# =============================================================================
@bp.before_app_request
def log_before_request_api():
    """Loga entrada de qualquer requisição em /chamados/api/..."""
    path = request.path or ""
    if path.startswith("/chamados/api"):
        current_app.logger.info(
            f"[API IN] {request.method} {request.path}"
        )
        try:
            current_app.logger.info(
                f"[API IN DATA] args={dict(request.args)} "
                f"json={request.get_json(silent=True)} "
                f"form={dict(request.form)}"
            )
        except Exception as e:
            current_app.logger.warning(f"[API IN] Erro ao logar dados: {e}")


@bp.after_app_request
def log_after_request_api(response):
    """Loga saída de qualquer resposta da app, filtrando /chamados/api/..."""
    path = request.path or ""
    if path.startswith("/chamados/api"):
        current_app.logger.info(
            f"[API OUT] {request.method} {request.path} -> {response.status}"
        )
        try:
            body = response.get_data(as_text=True)
            # evita explodir o terminal com respostas grandes
            preview = body[:500] + ("..." if len(body) > 500 else "")
            current_app.logger.info(f"[API OUT BODY] {preview}")
        except Exception as e:
            current_app.logger.warning(f"[API OUT] Erro ao ler corpo: {e}")
    return response


# =============================================================================
# ABRIR CHAMADO
# =============================================================================
@bp.route("/abrir", methods=["GET", "POST"])
def abrir_chamado():
    """
    Rota para a página de abertura de chamado. Opera em duas etapas:
    1. GET: Exibe o formulário para o usuário preencher.
    2. POST: Recebe os dados, consulta a IA para uma solução sugerida e exibe essa solução
       ao usuário ANTES de criar o chamado no banco. Os dados do chamado são salvos
       temporariamente na sessão do usuário.
    """
    form = chamadoForm()
    form.status.data = "Aberto"
    current_app.logger.debug(f"abrir_chamado called, method={request.method}")

    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    if request.method == "POST" and form.validate_on_submit():
        solucao_sugerida, prioridade_ia = buscar_solucao_com_ia(
            form.titulo.data, form.descricao.data
        )
        current_app.logger.info(
            f"Solucao sugerida: {solucao_sugerida}, Prioridade IA: {prioridade_ia}"
        )

        chamado_data = {
            "titulo": form.titulo.data,
            "descricao": form.descricao.data,
            "afetado": form.afetado.data,
            "prioridade": prioridade_ia,
            "solucao_sugerida": solucao_sugerida,
            "anexo": None,
        }

        # Upload de arquivo (opcional)
        if "anexo" in request.files:
            file = request.files["anexo"]
            if file.filename == "":
                current_app.logger.warning("Nenhum arquivo selecionado para upload.")
            elif file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                upload_folder = current_app.config["UPLOAD_FOLDER"]
                os.makedirs(upload_folder, exist_ok=True)
                file_path = os.path.join(upload_folder, filename)

                file.save(file_path)

                try:
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                    chamado_data["anexo"] = file_bytes
                    chamado_data["nome_anexo"] = filename
                    current_app.logger.info(
                        f"Arquivo {filename} salvo em {file_path} e bytes preparados para DB"
                    )
                except Exception as e:
                    current_app.logger.exception(
                        f"Erro ao ler arquivo salvo para armazenamento em DB: {e}"
                    )
                    chamado_data["anexo"] = None
            else:
                current_app.logger.warning(
                    f"Tipo de arquivo não permitido: {file.filename}"
                )

        session["chamado_temporario"] = chamado_data
        user = {"name": session.get("usuario_nome")}

        # Formata HTML da solução (se serviço existir)
        try:
            from ..services import format_solucao

            solucao_html = format_solucao(solucao_sugerida)
        except Exception:
            solucao_html = solucao_sugerida or ""

        return render_template(
            "solucao_ia.html",
            solucao=solucao_sugerida,
            solucao_html=solucao_html,
            user=user,
        )

    elif request.method == "POST":
        current_app.logger.warning(
            "POST em /chamados/abrir, mas form.validate_on_submit() retornou False"
        )
        current_app.logger.debug(f"form.errors: {form.errors}")
        try:
            current_app.logger.debug(f"request.form keys: {list(request.form.keys())}")
        except Exception:
            current_app.logger.debug("Não foi possível ler request.form")

        flash("Corrija os erros do formulário e tente novamente.", "danger")

    # GET
    user = {"name": session.get("usuario_nome", "Usuário")}
    return render_template("chamado.html", form=form, user=user)


# =============================================================================
# CONFIRMAR ABERTURA (DEPOIS DA SOLUÇÃO IA)
# =============================================================================
@bp.route("/confirmar_abertura", methods=["GET", "POST"])
def confirmar_abertura_chamado():
    if "usuario_id" not in session or "chamado_temporario" not in session:
        return redirect(url_for("main.index"))

    dados_chamado = session.get("chamado_temporario")
    if not dados_chamado:
        return redirect(url_for("chamados.abrir_chamado"))

    user = {"name": session.get("usuario_nome", "Usuário")}

    if request.method == "POST":
        dados_chamado = session.pop("chamado_temporario", None)
        if not dados_chamado:
            return redirect(url_for("chamados.abrir_chamado"))

        novo_chamado = Chamado(
            titulo_Chamado=dados_chamado["titulo"],
            descricao_Chamado=dados_chamado["descricao"],
            categoria_Chamado=dados_chamado["afetado"],
            solicitanteID=session["usuario_id"],
            prioridade_Chamado=dados_chamado["prioridade"],
            solucaoSugerida=dados_chamado["solucao_sugerida"],
            anexo_Chamado=dados_chamado.get("anexo"),
        )
        db.session.add(novo_chamado)
        db.session.flush()
        db.session.commit()
        return render_template(
            "chamado_enviado.html", chamado=novo_chamado, user=user
        )

    # GET
    current_app.logger.debug(
        f"Nome do usuário na sessão para chamado_enviado.html (GET): {user['name']}"
    )
    return render_template(
        "chamado_enviado.html", chamado_data=dados_chamado, user=user
    )


# =============================================================================
# RESOLVIDO PELA IA
# =============================================================================
@bp.route("/resolvido_ia", methods=["POST"])
def resolvido_pela_ia():
    if "usuario_id" not in session or "chamado_temporario" not in session:
        flash("Sessão expirada ou inválida.", "warning")
        return redirect(url_for("main.index"))

    dados_chamado = session.pop("chamado_temporario", None)
    if not dados_chamado:
        flash("Não foi possível encontrar os dados do chamado.", "danger")
        return redirect(url_for("chamados.abrir_chamado"))

    novo_chamado = Chamado(
        titulo_Chamado=dados_chamado["titulo"],
        descricao_Chamado=dados_chamado["descricao"],
        categoria_Chamado=dados_chamado["afetado"],
        solicitanteID=session["usuario_id"],
        prioridade_Chamado=dados_chamado["prioridade"],
        solucaoSugerida=dados_chamado["solucao_sugerida"],
        anexo_Chamado=dados_chamado.get("anexo"),
        status_Chamado="Resolvido por IA",
    )

    db.session.add(novo_chamado)
    db.session.flush()
    db.session.commit()

    current_app.logger.info(
        f"Chamado {novo_chamado.chamado_ID} criado e marcado como 'Resolvido por IA'."
    )
    return render_template("chamado_resolvido_ia.html", chamado=novo_chamado)


# =============================================================================
# LISTAR / FILTRAR CHAMADOS
# =============================================================================
@bp.route("/ver")
def ver_chamados():
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    search_query = request.args.get("q", "")
    status_filtro = request.args.get("status", "Todos")
    query = Chamado.query

    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(Chamado.titulo_Chamado.ilike(search_term))

    if status_filtro and status_filtro != "Todos":
        query = query.filter(Chamado.status_Chamado == status_filtro)

    lista_chamados = query.order_by(Chamado.dataAbertura.desc()).all()
    user = {"name": session.get("usuario_nome", "Usuário")}
    return render_template(
        "verChamado.html",
        chamados=lista_chamados,
        user=user,
        search_query=search_query,
        status_filtro=status_filtro,
    )


# =============================================================================
# TRIAGEM
# =============================================================================
@bp.route("/triagem", methods=["GET"])
def triagem():
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    page = request.args.get("page", 1, type=int)
    search_query = request.args.get("q", "").strip()
    prioridade_filtro = request.args.get("prioridade", "Todos")
    status_filtro = request.args.get("status", "Aberto")
    data_filtro = request.args.get("data", "Todos")
    order_by = request.args.get("order_by", "dataAbertura")
    direction = request.args.get("direction", "asc")

    query = Chamado.query.filter(Chamado.status_Chamado == "Aberto")

    if search_query:
        try:
            chamado_id = int(search_query)
            query = query.filter(Chamado.chamado_ID == chamado_id)
        except ValueError:
            query = query.filter(Chamado.titulo_Chamado.ilike(f"%{search_query}%"))

    if prioridade_filtro != "Todos":
        query = query.filter(Chamado.prioridade_Chamado == prioridade_filtro)

    if status_filtro != "Todos":
        query = query.filter(Chamado.status_Chamado == status_filtro)

    if data_filtro == "Hoje":
        query = query.filter(
            Chamado.dataAbertura
            >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        )
    elif data_filtro == "Ultimos 7 Dias":
        query = query.filter(
            Chamado.dataAbertura >= (datetime.now() - timedelta(days=7))
        )
    elif data_filtro == "Ultimos 30 Dias":
        query = query.filter(
            Chamado.dataAbertura >= (datetime.now() - timedelta(days=30))
        )

    if order_by:
        if direction == "asc":
            query = query.order_by(getattr(Chamado, order_by).asc())
        else:
            query = query.order_by(getattr(Chamado, order_by).desc())
    else:
        query = query.order_by(Chamado.dataAbertura.asc())

    chamados_paginados = query.paginate(page=page, per_page=20)

    total_aguardando_triagem = Chamado.query.filter_by(
        status_Chamado="Aberto"
    ).count()

    triados_hoje = Chamado.query.filter(
        Chamado.status_Chamado == "Em Atendimento",
        Chamado.dataUltimaModificacao != None,
        Chamado.dataUltimaModificacao
        >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
    ).count()

    pendentes_mais_24h = Chamado.query.filter(
        Chamado.status_Chamado == "Aberto",
        Chamado.dataAbertura <= (datetime.now() - timedelta(hours=24)),
    ).count()

    user = {"name": session.get("usuario_nome", "Usuário")}
    return render_template(
        "triagem.html",
        chamados_paginados=chamados_paginados,
        user=user,
        search_query=search_query,
        prioridade_filtro=prioridade_filtro,
        status_filtro=status_filtro,
        data_filtro=data_filtro,
        order_by=order_by,
        direction=direction,
        total_aguardando_triagem=total_aguardando_triagem,
        triados_hoje=triados_hoje,
        pendentes_mais_24h=pendentes_mais_24h,
    )


# =============================================================================
# TRANSFERIR
# =============================================================================
@bp.route("/transferir/<int:chamado_id>", methods=["GET", "POST"])
def transferir_chamado(chamado_id):
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    chamado = Chamado.query.get_or_404(chamado_id)

    if request.method == "POST":
        prioridade = request.form.get("prioridade")
        destino = request.form.get("transferir")

        if prioridade:
            chamado.prioridade_Chamado = prioridade

        if destino == "setor-triagem":
            chamado.status_Chamado = "Aberto"
            chamado.atendenteID = None
            msg = "Chamado transferido de volta para triagem."
            redirect_to = url_for("chamados.triagem")
        else:
            chamado.status_Chamado = "Em Atendimento"
            chamado.atendenteID = session.get("usuario_id")
            msg = "Chamado transferido e em atendimento."
            redirect_to = url_for("chamados.atender_chamado", chamado_id=chamado_id)

        try:
            chamado.dataUltimaModificacao = get_sao_paulo_time()
        except Exception:
            chamado.dataUltimaModificacao = datetime.now()

        db.session.commit()
        flash(msg, "success")
        return redirect(redirect_to)

    user = {"name": session.get("usuario_nome", "Usuário")}
    return render_template("transferir_chamado.html", chamado=chamado, user=user)


# =============================================================================
# TRIAR CHAMADO
# =============================================================================
@bp.route("/triar/<int:chamado_id>")
def triar_chamado(chamado_id):
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    chamado = Chamado.query.get_or_404(chamado_id)
    chamado.status_Chamado = "Em Atendimento"
    chamado.atendenteID = session["usuario_id"]
    chamado.dataUltimaModificacao = datetime.now()
    db.session.commit()

    flash("Chamado triado e em atendimento!", "success")
    return redirect(url_for("chamados.atender_chamado", chamado_id=chamado_id))


# =============================================================================
# ATENDER CHAMADO (TELA DO CHAT)
# =============================================================================
@bp.route("/atender/<int:chamado_id>")
def atender_chamado(chamado_id):
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    chamado = Chamado.query.get_or_404(chamado_id)
    user = {"name": session.get("usuario_nome", "Usuário")}
    return render_template("atender_chamado.html", chamado=chamado, user=user)


# =============================================================================
# ENCERRAR / DEVOLVER / REABRIR
# =============================================================================
@bp.route("/encerrar/<int:chamado_id>", methods=["POST"])
def encerrar_chamado(chamado_id):
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    chamado = Chamado.query.get_or_404(chamado_id)
    chamado.status_Chamado = "Resolvido"
    db.session.commit()
    return redirect(url_for("chamados.ver_chamados"))


@bp.route("/devolver_triagem/<int:chamado_id>")
def devolver_triagem(chamado_id):
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    chamado = Chamado.query.get_or_404(chamado_id)
    chamado.status_Chamado = "Aberto"
    chamado.atendenteID = None
    db.session.commit()

    flash("Chamado devolvido para a triagem com sucesso!", "success")
    return redirect(url_for("chamados.triagem"))


@bp.route("/reabrir/<int:chamado_id>", methods=["POST"])
def reabrir_chamado(chamado_id):
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    chamado = Chamado.query.get_or_404(chamado_id)
    chamado.status_Chamado = "Aberto"
    chamado.atendenteID = None
    db.session.commit()

    flash("Chamado reaberto com sucesso!", "success")
    return redirect(url_for("chamados.ver_chamados"))


# =============================================================================
# API DE MENSAGENS DO CHAMADO (GET + POST)
# =============================================================================
@bp.route("/api/<int:chamado_id>/mensagens", methods=["GET", "POST"])
def api_mensagens_chamado(chamado_id):
    """
    GET  -> lista todas as mensagens do chamado
    POST -> cria uma nova mensagem vinda do painel (chat da tela)
    """
    if request.method == "GET":
        current_app.logger.info(
            "GET /chamados/api/%s/mensagens chamado", chamado_id
        )

        interacoes = (
            Interacao.query.filter_by(chamado_id=chamado_id)
            .join(Usuario, Usuario.id == Interacao.usuario_id)
            .add_columns(Usuario.nome)
            .order_by(Interacao.data_criacao.asc())
            .all()
        )

        resultado = []
        for interacao, usuario_nome in interacoes:
            resultado.append(
                {
                    "id": interacao.id,
                    "chamado_id": interacao.chamado_id,
                    "usuario_id": interacao.usuario_id,
                    "usuario_nome": usuario_nome,
                    "mensagem": interacao.mensagem,
                    "data_criacao": interacao.data_criacao.strftime(
                        "%d/%m/%Y %H:%M"
                    ),
                    "origem": interacao.origem,  # usa a @property
                }
            )

        return jsonify(resultado), 200

    # ---------- POST ----------
    current_app.logger.info(
        "POST /chamados/api/%s/mensagens chamado", chamado_id
    )

    data = request.get_json(silent=True) or {}

    mensagem = (
        data.get("mensagem")
        or data.get("conteudo")
        or data.get("texto")
        or data.get("mensagem_usuario")
    )

    if not mensagem:
        return jsonify({"erro": "Campo de mensagem é obrigatório."}), 400

    usuario_id = session.get("usuario_id")
    if not usuario_id:
        current_app.logger.warning(
            "POST /chamados/api/%s/mensagens sem usuario_id na sessão.",
            chamado_id,
        )
        return jsonify({"erro": "Usuário não autenticado."}), 401

    # 🔧 AJUSTE AQUI: removido 'origem="painel"'
    interacao = Interacao(
        chamado_id=chamado_id,
        usuario_id=usuario_id,
        mensagem=mensagem,
    )
    db.session.add(interacao)
    db.session.commit()

    email = data.get("email") or session.get("usuario_email")
    nome = data.get("nome") or session.get("usuario_nome")
    texto_para_suporte = f"[Chamado #{chamado_id}]\n{mensagem}"

    if email:
        try:
            notificar_suporte(texto_para_suporte, email, nome)
        except Exception as e:
            current_app.logger.exception(
                "Erro ao notificar suporte no chamado %s: %s", chamado_id, e
            )
            return (
                jsonify(
                    {
                        "status": "parcial",
                        "mensagem": "Mensagem salva, mas houve falha ao notificar o suporte.",
                        "interacao_id": interacao.id,
                    }
                ),
                500,
            )

    return (
        jsonify(
            {
                "status": "ok",
                "mensagem": "Mensagem registrada.",
                "interacao_id": interacao.id,
            }
        ),
        200,
    )

# =============================================================================
# RELATÓRIO PDF (PLACEHOLDER)
# =============================================================================
@bp.route("/relatorio/pdf")
def gerar_relatorio_pdf():
    """(Placeholder) Rota para futura implementação de relatórios em PDF."""
    pass
