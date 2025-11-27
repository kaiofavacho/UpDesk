"""
Blueprint para Gerenciamento de Usuários

Responsabilidade:
- Agrupar todas as rotas relacionadas às operações de CRUD (Create, Read, Update, Delete) de usuários.
- Fornece endpoints para criar, listar, editar e desativar usuários, além de visualizar o perfil do usuário logado.
"""

from flask import (
    Blueprint,
    request,
    jsonify,
    render_template,
    session,
    redirect,
    url_for,
    current_app,
)
from werkzeug.security import generate_password_hash
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from wtforms.validators import Optional as WTOptional

from ..models import db, Usuario
from ..forms import CriarUsuarioForm, EditarUsuarioForm

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


def _json_error(message, status=400, errors=None):
    payload = {"mensagem": message}
    if errors:
        payload["erros"] = errors
    return jsonify(payload), status


@bp.route("/ger_usuarios")
def ger_usuarios():
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    search_query = (request.args.get("q") or "").strip()

    current_app.logger.info(
        "[USUÁRIOS] GET /usuarios/ger_usuarios - search_query=%r", search_query
    )

    query = Usuario.query.filter_by(ativo=True)

    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_(Usuario.nome.ilike(search_term), Usuario.email.ilike(search_term)))

    lista_usuarios = query.order_by(Usuario.id.desc()).all()

    form_criar = CriarUsuarioForm()
    form_editar = EditarUsuarioForm()

    user = {"name": session.get("usuario_nome", "Usuário")}

    return render_template(
        "ger_usuarios.html",
        usuarios=lista_usuarios,
        user=user,
        form_criar=form_criar,
        form_editar=form_editar,
        search_query=search_query,
    )


@bp.route("/criar", methods=["POST"])
def criar_usuario():
    form = CriarUsuarioForm()

    if not form.validate_on_submit():
        erros = {campo: erro[0] for campo, erro in form.errors.items()}
        current_app.logger.warning(
            "[USUÁRIOS] POST /usuarios/criar - validação falhou: %s", erros
        )
        return _json_error("Dados inválidos", 400, erros)

    try:
        novo_usuario = Usuario(
            nome=form.nome.data,
            email=form.email.data,
            telefone=form.telefone.data,
            setor=form.setor.data,
            cargo=form.cargo.data,
            senha=generate_password_hash(form.senha.data),
            ativo=True,
        )
        db.session.add(novo_usuario)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _json_error("E-mail já cadastrado", 409, {"email": "Já existe um usuário com este e-mail."})

    current_app.logger.info(
        "[USUÁRIOS] Usuário criado com sucesso: id=%s, email=%s",
        novo_usuario.id,
        novo_usuario.email,
    )
    return jsonify({"mensagem": "Usuário criado com sucesso!"}), 201


@bp.route("/editar/<int:usuario_id>", methods=["POST"])
def editar_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    form = EditarUsuarioForm()

    # Se senha ficar vazia, não valida senha/confirma_senha
    if hasattr(form, "senha") and not (form.senha.data or "").strip():
        form.senha.validators = [WTOptional()]
        if hasattr(form, "confirma_senha"):
            form.confirma_senha.validators = [WTOptional()]

    if not form.validate_on_submit():
        erros = {campo: erro[0] for campo, erro in form.errors.items()}
        current_app.logger.warning(
            "[USUÁRIOS] POST /usuarios/editar/%s - validação falhou: %s",
            usuario_id,
            erros,
        )
        return _json_error("Dados inválidos", 400, erros)

    usuario.nome = form.nome.data
    usuario.email = form.email.data
    usuario.telefone = form.telefone.data
    usuario.setor = form.setor.data
    usuario.cargo = form.cargo.data

    if hasattr(form, "senha") and (form.senha.data or "").strip():
        usuario.senha = generate_password_hash(form.senha.data.strip())

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _json_error("E-mail já cadastrado", 409, {"email": "Já existe um usuário com este e-mail."})

    current_app.logger.info(
        "[USUÁRIOS] Usuário atualizado com sucesso: id=%s, email=%s",
        usuario.id,
        usuario.email,
    )
    return jsonify({"mensagem": "Usuário atualizado com sucesso!"}), 200


@bp.route("/excluir/<int:usuario_id>", methods=["POST"])
def excluir_usuario(usuario_id):
    usuario = Usuario.query.get_or_404(usuario_id)
    usuario.ativo = False
    db.session.commit()

    current_app.logger.info(
        "[USUÁRIOS] Usuário desativado: id=%s, email=%s", usuario.id, usuario.email
    )
    return jsonify({"mensagem": "Usuário desativado com sucesso!"}), 200


@bp.route("/perfil")
def perfil():
    if "usuario_id" not in session:
        return redirect(url_for("main.index"))

    usuario = Usuario.query.get_or_404(session["usuario_id"])

    user = {
        "name": usuario.nome,
        "email": usuario.email,
        "cargo": usuario.cargo,
        "setor": usuario.setor,
        "telefone": usuario.telefone,
    }

    return render_template("perfil.html", user=user)
