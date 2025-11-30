from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from models import Worker, WorkerHistory, WorkerMonthlyRecord, WorkerEvaluation, OrderAssignment, Task, db
from models import create_monthly_record, evaluate_worker_performance, get_monthly_workers_cost, get_worker_monthly_history
from datetime import datetime, timezone
import random
import string

workers_bp = Blueprint('workers', __name__)

@workers_bp.route("/workers")
def workers():
    """صفحة إدارة العمال"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    workers_list = Worker.query.order_by(Worker.created_at.desc()).all()
    
    total_salaries = sum(worker.total_salary for worker in workers_list)
    total_advances = sum(worker.advances for worker in workers_list)
    
    active_workers = [worker for worker in workers_list if worker.is_active]
    frozen_workers = [worker for worker in workers_list if not worker.is_active]
    
    return render_template(
        "workers.html", 
        workers=workers_list, 
        total_salaries=total_salaries,
        total_advances=total_advances,
        active_workers=active_workers,
        frozen_workers=frozen_workers,
        now=datetime.now(timezone.utc)
    )

@workers_bp.route("/workers/add", methods=["POST"])
def add_worker():
    """إضافة عامل جديد مع إنشاء حساب تسجيل دخول تلقائي"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        worker_data = {
            "name": request.form.get("name"),
            "phone": request.form.get("phone"),
            "address": request.form.get("address"),
            "id_card": request.form.get("id_card"),
            "start_date": datetime.strptime(request.form.get("start_date"), "%Y-%m-%d"),
            "monthly_salary": float(request.form.get("monthly_salary") or 0),
        }
        
        # 🆕 إنشاء اسم مستخدم وكلمة مرور تلقائياً
        phone = worker_data["phone"].strip()
        
        # تنظيف رقم الهاتف من المسافات والرموز
        clean_phone = ''.join(filter(str.isdigit, phone))
        
        # إنشاء اسم المستخدم من رقم الهاتف (أخر 8 أرقام)
        if len(clean_phone) >= 8:
            username = "worker_" + clean_phone[-8:]
        else:
            username = "worker_" + clean_phone
        
        # التحقق من عدم تكرار اسم المستخدم
        existing_worker = Worker.query.filter_by(username=username).first()
        if existing_worker:
            # إذا كان مكرراً، أضف رقم عشوائي
            username = f"{username}_{random.randint(100, 999)}"
        
        # إنشاء كلمة مرور عشوائية
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        
        worker_data["username"] = username
        worker_data["is_login_active"] = True
        
        worker = Worker(**worker_data)
        worker.password = password  # 🆕 هذا سيخزن كلمة المرور الأصلية تلقائياً
        
        db.session.add(worker)
        db.session.flush()  # للحصول على ID قبل الـ commit
        
        print(f"✅ تم إنشاء حساب عامل: {username} / {password}")
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم إضافة العامل وإنشاء حساب تسجيل دخول له",
            "worker_id": worker.id,
            "login_info": {
                "username": username,
                "password": password
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في إضافة العامل: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 400

@workers_bp.route("/workers/edit/<int:id>", methods=["POST"])
def edit_worker(id):
    """تعديل بيانات عامل"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        worker = Worker.query.get_or_404(id)
        
        worker.name = request.form.get("name")
        worker.phone = request.form.get("phone")
        worker.address = request.form.get("address")
        worker.id_card = request.form.get("id_card")
        worker.monthly_salary = float(request.form.get("monthly_salary") or 0)
        
        db.session.commit()
        return redirect(url_for("workers.workers"))
    except Exception as e:
        db.session.rollback()
        return f"خطأ في تعديل العامل: {str(e)}", 400

@workers_bp.route("/workers/delete/<int:id>")
def delete_worker(id):
    """حذف عامل"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        worker = Worker.query.get_or_404(id)
        db.session.delete(worker)
        db.session.commit()
        return redirect(url_for("workers.workers"))
    except Exception as e:
        db.session.rollback()
        return f"خطأ في حذف العامل: {str(e)}", 400

@workers_bp.route("/workers/toggle_status/<int:id>")
def toggle_worker_status(id):
    """تجميد/تفعيل عامل"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        worker = Worker.query.get_or_404(id)
        worker.is_active = not worker.is_active
        db.session.commit()
        return redirect(url_for("workers.workers"))
    except Exception as e:
        db.session.rollback()
        return f"خطأ في تغيير حالة العامل: {str(e)}", 400

# APIs إضافية للعمال
@workers_bp.route("/workers/record_absence/<int:id>", methods=["POST"])
def record_worker_absence(id):
    """تسجيل غياب للعامل"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        worker = Worker.query.get_or_404(id)
        absence_type = request.form.get("type", "full")
        notes = request.form.get("notes", "")
        days_to_add = 0.5 if absence_type == "half" else 1
        
        daily_salary = worker.monthly_salary / 30.0
        deduction_amount = days_to_add * daily_salary
        
        worker.absences += days_to_add
        
        history = WorkerHistory(
            worker_id=worker.id,
            change_type="غياب",
            details=f"تسجيل {absence_type} غياب. {notes}",
            amount=-deduction_amount
        )
        db.session.add(history)
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"تم تسجيل غياب {absence_type} للعامل",
            "new_absences": worker.absences,
            "deduction": deduction_amount
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@workers_bp.route("/workers/pay_salary/<int:id>", methods=["POST"])
def pay_worker_salary(id):
    """دفع راتب العامل"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        worker = Worker.query.get_or_404(id)
        amount = float(request.form.get("amount") or 0)
        payment_method = request.form.get("payment_method", "نقدي")
        notes = request.form.get("notes", "")
        
        if amount <= 0:
            return jsonify({"success": False, "error": "المبلغ يجب أن يكون أكبر من الصفر"})
        
        current_total_salary = worker.total_salary
        
        if amount > current_total_salary:
            return jsonify({"success": False, "error": f"المبلغ يتجاوز المستحق ({current_total_salary:.2f} دج)"})
        
        # إنشاء السجل الشهري قبل الدفع
        monthly_record = create_monthly_record(id, session["user"])
        
        # تحديث بيانات العامل
        worker.start_date = datetime.now(timezone.utc).date()
        worker.absences = 0
        worker.outside_work_days = 0
        worker.outside_work_bonus = 0
        worker.advances = 0
        worker.incentives = 0
        worker.late_hours = 0
        
        history = WorkerHistory(
            worker_id=worker.id,
            change_type="دفع راتب",
            details=f"تم دفع راتب بقيمة {amount:.2f} دج. طريقة الدفع: {payment_method}. {notes} | بداية فترة جديدة من: {worker.start_date.strftime('%Y-%m-%d')}",
            amount=-amount,
            user=session["user"]
        )
        db.session.add(history)
        
        # تحديث السجل الشهري بالمبلغ المدفوع
        if monthly_record:
            monthly_record.paid_amount = amount
            monthly_record.notes = f"تم دفع الراتب وبدء فترة جديدة من {worker.start_date.strftime('%Y-%m-%d')}"
        
        db.session.commit()
        
        new_total_salary = worker.total_salary
        
        return jsonify({
            "success": True, 
            "message": f"تم دفع راتب بقيمة {amount:.2f} دج وبدء فترة عمل جديدة",
            "paid_amount": amount,
            "new_start_date": worker.start_date.strftime('%Y-%m-%d'),
            "old_salary": current_total_salary,
            "new_salary": new_total_salary,
            "worker_name": worker.name,
            "monthly_record_id": monthly_record.id if monthly_record else None
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في دفع الراتب: {str(e)}")
        return jsonify({"success": False, "error": str(e)})
    
@workers_bp.context_processor
def inject_functions():
    """جعل الدوال متاحة في قوالب العمال"""
    return dict(
        is_admin_user=is_admin_user,
        total_debts=total_debts
    )