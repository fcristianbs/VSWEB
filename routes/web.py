from flask import Blueprint, render_template
from models import Projeto

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index(): 
    return render_template('index.html')

@web_bp.route('/drive')
def drive():
    projetos_db = Projeto.query.order_by(Projeto.data_criacao.desc()).all()
    projetos_lista = []
    
    # Truque para não quebrar o seu drive.html com a mudança de nome no BD (status_global)
    for p in projetos_db:
        data_dec = p.data_limite if p.data_limite else p.data_criacao.date()
        projetos_lista.append({
            'id': p.id,
            'codigo_obra': p.codigo_obra,
            'nome_obra': p.nome_obra,
            'status_manual': p.status_global, 
            'data_criacao': p.data_criacao,
            'data_ultima_edicao': getattr(p, 'data_ultima_edicao', p.data_criacao),
            'data_declarada': data_dec.strftime('%Y-%m-%d'),
            'data_exibicao': data_dec.strftime('%d/%m/%Y'),
            'documentos': p.documentos
        })
        
    return render_template('drive.html', projetos=projetos_lista)

@web_bp.route('/admin')
def admin():
    return render_template('admin.html')
