# app/app.py
from flask import Flask, session, redirect, url_for
from models import db
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.orders import orders_bp
from routes.workers import workers_bp
from routes.expenses import expenses_bp
from routes.transport import transport_bp
from routes.debts import debts_bp
from routes.tasks import tasks_bp
from routes.activities import activities_bp
from routes.settings import settings_bp
from routes.reports import reports_bp  # ✅ تم الإصلاح

app = Flask(__name__)
app.secret_key = "secretkey123"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# إعدادات تحميل الملفات
UPLOAD_FOLDER = 'uploads/receipts'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

# تهيئة قاعدة البيانات
db.init_app(app)

# تسجيل الـ Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(orders_bp)
app.register_blueprint(workers_bp)
app.register_blueprint(expenses_bp)
app.register_blueprint(transport_bp)
app.register_blueprint(debts_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(activities_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(reports_bp)  # ✅ تم الإصلاح

# المسار الرئيسي
@app.route("/")
def index():
    if "user" in session:
        if session.get("user_type") == "worker":
            return redirect(url_for("worker.worker_dashboard"))
        else:
            return redirect(url_for("dashboard.dashboard"))
    return redirect(url_for("auth.login"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        
        # إنشاء مستخدم افتراضي إذا لم يوجد
        from models import User
        if not User.query.filter_by(username="admin").first():
            default_user = User(
                username="admin",
                email="admin@localhost.com",
                full_name="مدير النظام",
                role="admin"
            )
            default_user.password = "admin123"
            db.session.add(default_user)
            db.session.commit()
            print("✅ تم إنشاء المستخدم الافتراضي: admin / admin123")
    
    app.run(debug=True)

@app.context_processor
def inject_global_functions():
    """جعل الدوال متاحة في جميع القوالب"""
    from routes.helpers import is_admin_user, total_debts
    return dict(
        is_admin_user=is_admin_user,
        total_debts=total_debts
    )