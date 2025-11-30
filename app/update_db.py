# أنشئ ملفاً اسمه update_db.py وأضف:
from app import app
from models import db, OrderAttachment

with app.app_context():
    try:
        # هذا سيحاول تحديث الجدول
        db.create_all()
        print("✅ تم تحديث قاعدة البيانات بنجاح")
    except Exception as e:
        print(f"❌ خطأ في تحديث قاعدة البيانات: {e}")