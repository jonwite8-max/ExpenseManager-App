from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, flash
from models import User, Supplier, ExpenseCategory, TransportCategory, TransportSubType, db
from datetime import datetime, timezone
import os
import shutil

settings_bp = Blueprint('settings', __name__)

@settings_bp.route("/settings")
def settings():
    """صفحة الإعدادات"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    users = User.query.all()
    suppliers = Supplier.query.all()
    expense_categories = ExpenseCategory.query.all()
    transport_categories = TransportCategory.query.all()
    transport_subtypes = TransportSubType.query.all()
    
    return render_template("settings.html",
                         users=users,
                         suppliers=suppliers,
                         expense_categories=expense_categories,
                         transport_categories=transport_categories,
                         transport_subtypes=transport_subtypes)

@settings_bp.route("/settings/user/add", methods=["POST"])
def add_user():
    """إضافة مستخدم جديد"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        user = User(
            username=request.form.get("username"),
            full_name=request.form.get("full_name", ""),
            role=request.form.get("role", "user"),
            is_active=True
        )
        user.password = request.form.get("password", "123456")  # كلمة مرور افتراضية
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم إضافة المستخدم بنجاح",
            "user_id": user.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@settings_bp.route("/settings/user/toggle/<int:id>")
def toggle_user(id):
    """تفعيل/تعطيل مستخدم"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        user = User.query.get_or_404(id)
        user.is_active = not user.is_active
        db.session.commit()
        
        status = "مفعل" if user.is_active else "معطل"
        flash(f"✅ تم {status} المستخدم {user.username}", "success")
    except Exception as e:
        flash(f"❌ خطأ في تغيير حالة المستخدم: {str(e)}", "error")
    
    return redirect(url_for("settings.settings"))

@settings_bp.route("/settings/user/reset-password/<int:user_id>", methods=['POST'])
def reset_user_password(user_id):
    """إعادة تعيين كلمة مرور مدير"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        user = User.query.get_or_404(user_id)
        
        # إنشاء كلمة مرور جديدة
        import random
        import string
        new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        
        user.password = new_password
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم إعادة تعيين كلمة المرور بنجاح",
            "new_password": new_password
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@settings_bp.route("/settings/category/add", methods=["POST"])
def add_category():
    """إضافة تصنيف جديد"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        category_type = request.form.get("type")
        name = request.form.get("name")
        
        if category_type == "expense":
            from models import ExpenseCategory
            category = ExpenseCategory(name=name)
        elif category_type == "transport":
            from models import TransportCategory
            category = TransportCategory(name=name)
        else:
            return jsonify({"success": False, "error": "نوع التصنيف غير صحيح"})
        
        db.session.add(category)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"تم إضافة التصنيف {name} بنجاح",
            "category_id": category.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@settings_bp.route("/settings/supplier/add", methods=["POST"])
def add_supplier():
    """إضافة مورد جديد"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        supplier = Supplier(
            name=request.form.get("name"),
            phone=request.form.get("phone"),
            address=request.form.get("address")
        )
        db.session.add(supplier)
        db.session.commit()
        
        return jsonify({"success": True, "message": "تم إضافة المورد بنجاح", "supplier_id": supplier.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@settings_bp.route("/settings/supplier/delete/<int:id>")
def delete_supplier(id):
    """حذف مورد"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        supplier = Supplier.query.get_or_404(id)
        db.session.delete(supplier)
        db.session.commit()
        flash("✅ تم حذف المورد بنجاح", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ خطأ في حذف المورد: {str(e)}", "error")
    
    return redirect(url_for("settings.settings"))

@settings_bp.route("/api/backup/create", methods=['POST'])
def create_backup():
    """إنشاء نسخة احتياطية"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        # اسم ملف النسخة الاحتياطية
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.db"
        backup_path = f"backups/{backup_filename}"
        
        # إنشاء مجلد النسخ الاحتياطية إذا لم يكن موجوداً
        os.makedirs("backups", exist_ok=True)
        
        # نسخ قاعدة البيانات
        shutil.copy2("data.db", backup_path)
        
        return jsonify({
            "success": True,
            "message": "تم إنشاء النسخة الاحتياطية بنجاح",
            "filename": backup_filename
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@settings_bp.route("/api/backup/history")
def get_backup_history():
    """جلب سجل النسخ الاحتياطية"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        backups = []
        if os.path.exists("backups"):
            for filename in os.listdir("backups"):
                if filename.startswith("backup_") and filename.endswith(".db"):
                    filepath = os.path.join("backups", filename)
                    stat = os.stat(filepath)
                    size = round(stat.st_size / (1024 * 1024), 2)  # حجم بالميجابايت
                    created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M")
                    
                    backups.append({
                        "filename": filename,
                        "size": f"{size} MB",
                        "created_at": created
                    })
        
        # ترتيب من الأحدث إلى الأقدم
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        
        return jsonify({
            "success": True,
            "backups": backups
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})