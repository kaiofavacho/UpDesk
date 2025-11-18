from flask import Flask
from config import Config
from .blueprints import main, auth, chamados, usuarios, telegram  # <– adicionamos telegram aqui

def create_app(config_class=Config):
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder='templates',
        static_folder='static'
    )

    app.config.from_object(config_class)

    from .extensions import db, migrate, cors
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)

    import base64

    def to_base64(data):
        if isinstance(data, bytes):
            return base64.b64encode(data).decode('utf-8')
        return data

    app.jinja_env.filters['to_base64'] = to_base64

    with app.app_context():
        from . import services
        services.init_ia()

    # blueprints
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(chamados.bp)
    app.register_blueprint(usuarios.bp)
    app.register_blueprint(telegram.bp)  # <– registra o blueprint do Telegram

    return app
