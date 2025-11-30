# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

# إنشاء instance واحدة فقط من SQLAlchemy
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.secret_key = "secretkey123"
    
    # إعدادات قاعدة البيانات
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # ✅ تهيئة SQLAlchemy مع التطبيق
    db.init_app(app)
    
    # ✅ استيراد وتسجيل الـ Blueprints
    register_blueprints(app)
    
    # ✅ تهيئة قاعدة البيانات
    init_database(app)
    
    return app

def register_blueprints(app):
    """تسجيل جميع الـ Blueprints"""
    from routes.auth import auth_bp
    from routes.dashboard import main_bp
    from routes.orders import orders_bp
    from routes.workers import workers_bp
    from routes.expenses import expenses_bp
    from routes.transport import transport_bp
    from routes.tasks import tasks_bp
    from routes.settings import settings_bp
    from routes.debts import debts_bp
    from routes.reports import reports_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(workers_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(transport_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(debts_bp)
    app.register_blueprint(reports_bp)

def init_database(app):
    """تهيئة قاعدة البيانات"""
    with app.app_context():
        # إنشاء الجداول
        db.create_all()
        
        # استيراد النماذج بعد إنشاء الجداول
        from models import User
        
        # إنشاء مستخدم افتراضي
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                full_name='المدير العام',
                role='admin'
            )
            admin.password = 'admin123'
            db.session.add(admin)
            db.session.commit()
            print("✅ تم إنشاء المستخدم الافتراضي: admin / admin123")