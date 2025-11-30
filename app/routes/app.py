# app/routes/app.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, flash
from models import db, User, Worker
from datetime import datetime, timezone, timedelta
import os
from werkzeug.utils import secure_filename

# استيراد المسارات من الملفات الجديدة
from orders import create_orders_routes
from routes.expenses import expenses_bp
from routes.transport import transport_bp
from routes.debts import debts_bp
from routes.settings import settings_bp
from routes.tasks import tasks_bp
from routes.workers import workers_bp
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp

app = Flask(__name__)
app.secret_key = "secretkey123"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# إعدادات تحميل الملفات
UPLOAD_FOLDER = 'uploads/receipts'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 16 * 1024 * 1024

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# تسجيل البلوب prints
app.register_blueprint(orders_bp)
app.register_blueprint(expenses_bp)
app.register_blueprint(transport_bp)
app.register_blueprint(debts_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(workers_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)

# إنشاء المجلد إذا لم يكن موجوداً
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# تهيئة قاعدة البيانات
db.init_app(app)

# دالة لضغط الصور
def compress_image(image_data, max_size=(1200, 1200), quality=85):
    """ضغط الصورة للحفاظ على المساحة"""
    try:
        from PIL import Image
        from io import BytesIO
        image = Image.open(BytesIO(image_data))
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"خطأ في ضغط الصورة: {e}")
        return image_data

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        
        # إنشاء مستخدم افتراضي إذا لم يوجد
        if not User.query.first():
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