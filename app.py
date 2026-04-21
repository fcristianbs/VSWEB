import os
from flask import Flask
from models import db
from dotenv import load_dotenv

from extensions import db_imagens, pdfs_gerados, log_queue
from routes.web import web_bp
from routes.api import api_bp

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DOWNLOADS_GPM = os.path.join(BASE_DIR, 'downloads_gpm')
DRIVE_FOLDER = os.path.join(BASE_DIR, 'drive_local') 

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOADS_GPM'] = DOWNLOADS_GPM
app.config['DRIVE_FOLDER'] = DRIVE_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cosampa_drive.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

for pasta in [UPLOAD_FOLDER, DOWNLOADS_GPM, DRIVE_FOLDER]:
    if not os.path.exists(pasta): os.makedirs(pasta)

db.init_app(app)
with app.app_context():
    # Aumentamos o timeout para evitar "Database is Locked" e ativamos modo WAL
    db.create_all()
    from sqlalchemy import event
    @event.listens_for(db.engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000") # 5 segundos de espera
        cursor.close()

# Registrar Blueprints
app.register_blueprint(web_bp)
app.register_blueprint(api_bp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False, threaded=True)
