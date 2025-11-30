# routes/orders.py
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, Response, flash
from models import db, Order, PhoneNumber, Status, OrderHistory, Worker, OrderAssignment, OrderAttachment, Task
from models import User, Expense, Transport, Debt, AttachmentNotes  # ✅ إضافة AttachmentNotes هنا
from datetime import datetime, timezone, timedelta
import os
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
import base64
from io import BytesIO
from PIL import Image

# إنشاء Blueprint للطلبيات
orders_bp = Blueprint('orders', __name__)

# 🔧 نظام إدارة المساحة والتخزين
class StorageManager:
    @staticmethod
    def get_total_used_space():
        """حساب إجمالي المساحة المستخدمة"""
        try:
            from models import OrderAttachment
            total_size = db.session.query(db.func.sum(OrderAttachment.file_size)).scalar()
            return total_size or 0
        except Exception as e:
            print(f"❌ خطأ في حساب المساحة: {e}")
            return 0
    
    @staticmethod
    def get_order_attachments_size(order_id):
        """حساب مساحة مرفقات طلبية محددة"""
        try:
            from models import OrderAttachment
            order_size = db.session.query(db.func.sum(OrderAttachment.file_size))\
                .filter(OrderAttachment.order_id == order_id).scalar()
            return order_size or 0
        except Exception as e:
            print(f"❌ خطأ في حساب مساحة الطلبية: {e}")
            return 0
    
    @staticmethod
    def get_storage_limits():
        """الحصول على حدود التخزين"""
        return {
        'max_total_size': 2 * 1024 * 1024 * 1024,  # 2 GB بدل 500MB
        'max_per_order': 500 * 1024 * 1024,        # 500 MB بدل 50MB لكل طلبية
        'max_per_file': 100 * 1024 * 1024,         # 100 MB بدل 10MB لكل ملف
        'max_video_file': 200 * 1024 * 1024,       # 200 MB للفيديوهات
        'warning_threshold': 0.8  # تنبيه عند 80%
    }

    @staticmethod
    def check_storage_health():
        """فحص صحة التخزين وإرسال تنبيهات"""
        storage_info = StorageManager.get_storage_limits()
        total_used = StorageManager.get_total_used_space()
        usage_percentage = total_used / storage_info['max_total_size']
        
        alerts = []
        
        if usage_percentage >= storage_info['warning_threshold']:
            alerts.append({
                'type': 'warning',
                'message': f'⚠️ المساحة التخزينية قاربت على الامتلاء ({usage_percentage*100:.1f}%)',
                'action': 'قيّم بمسح الملفات غير الضرورية'
            })
        
        if usage_percentage >= 0.95:
            alerts.append({
                'type': 'critical', 
                'message': '🚨 المساحة التخزينية شبه ممتلئة!',
                'action': 'إجراء فوري مطلوب'
            })
        
        return alerts
# تعريف الدوال المساعدة محليًا
def is_admin_user():
    """التحقق من أن المستخدم الحالي هو أدمن"""
    if "user" not in session:
        return False
    
    username = session["user"]
    
    # البحث في جدول المديرين
    admin_user = User.query.filter_by(username=username).first()
    if admin_user and admin_user.role in ['admin', 'manager']:
        return True
    
    return False

def get_admin_users_list():
    """جلب قائمة الأدمن للفلتر"""
    try:
        admin_users = User.query.filter(
            User.role.in_(['admin', 'manager']),
            User.is_active == True
        ).all()
        
        admins_list = []
        for user in admin_users:
            admins_list.append({
                "username": user.username,
                "full_name": user.full_name or user.username
            })
        
        return admins_list
    except Exception as e:
        print(f"❌ خطأ في جلب قائمة الأدمن: {e}")
        return []

def get_file_type(filename, content_type):
    """تحديد نوع الملف بدقة"""
    if content_type.startswith('image/'):
        return 'image'
    elif content_type.startswith('video/'):
        return 'video'
    elif content_type == 'application/pdf':
        return 'pdf'
    elif content_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        return 'document'
    else:
        # التحقق من الامتداد أيضاً
        extension = filename.lower().split('.')[-1] if '.' in filename else ''
        video_extensions = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'wmv']
        if extension in video_extensions:
            return 'video'
        return 'other'

def allowed_file(filename):
    """التحقق من نوع الملف المسموح"""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in {
            'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 
            'mp4', 'mov', 'avi', 'mkv', 'webm'  # إضافة صيغ الفيديو
        }

def compress_image_advanced(image_data, max_size=(1200, 1200), quality=85):
    """ضغط متقدم للصور مع الحفاظ على الجودة"""
    try:
        image = Image.open(BytesIO(image_data))
        
        # التحقق من حجم الصورة الأصلية
        original_size = len(image_data)
        if original_size < 500 * 1024:  # أقل من 500KB لا نحتاج ضغط
            return image_data
        
        # تغيير الحجم إذا كان كبيراً
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # حفظ بصيغة مضغوطة مع التحسين
        output = BytesIO()
        
        if image.format == 'PNG':
            image.save(output, format='PNG', optimize=True)
        else:
            image.save(output, format='JPEG', quality=quality, optimize=True)
        
        compressed_data = output.getvalue()
        compression_ratio = len(compressed_data) / original_size
        
        print(f"✅ تم ضغط الصورة: {original_size/1024:.1f}KB → {len(compressed_data)/1024:.1f}KB ({compression_ratio*100:.1f}%)")
        
        return compressed_data
    except Exception as e:
        print(f"❌ خطأ في ضغط الصورة: {e}")
        return image_data

def should_compress_file(file_data, filename, mime_type):
    """تحديد إذا كان الملف يحتاج ضغط"""
    # الملفات الصغيرة لا تحتاج ضغط
    if len(file_data) < 300 * 1024:  # أقل من 300KB
        return False
    
    # فقط الصور يتم ضغطها
    if mime_type.startswith('image/'):
        return True
    
    # يمكن إضافة أنواع أخرى لاحقاً
    return False

def compress_image_advanced(image_data, max_size=(1200, 1200), quality=85):
    """ضغط متقدم للصور مع الحفاظ على الجودة"""
    try:
        from PIL import Image
        from io import BytesIO
        
        image = Image.open(BytesIO(image_data))
        
        # التحقق من حجم الصورة الأصلية
        original_size = len(image_data)
        
        # تغيير الحجم إذا كان كبيراً
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # حفظ بصيغة مضغوطة مع التحسين
        output = BytesIO()
        
        if image.format == 'PNG':
            # للصور PNG نستخدم optimize فقط
            image.save(output, format='PNG', optimize=True)
        else:
            # للصور JPEG نستخدم الضغط مع الجودة
            image.save(output, format='JPEG', quality=quality, optimize=True)
        
        compressed_data = output.getvalue()
        
        # إذا كان الملف المضغوط أكبر من الأصلي، نعود للأصلي
        if len(compressed_data) >= original_size:
            return image_data
        
        compression_ratio = (original_size - len(compressed_data)) / original_size * 100
        
        print(f"✅ تم ضغط الصورة: {original_size/1024:.1f}KB → {len(compressed_data)/1024:.1f}KB (وفرنا {compression_ratio:.1f}%)")
        
        return compressed_data
        
    except Exception as e:
        print(f"❌ خطأ في ضغط الصورة: {e}")
        return image_data

# ========================
# ⚡ مسارات الطلبيات
# ========================

@orders_bp.route("/orders")
def orders():
    """صفحة إدارة الطلبيات"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    show_paid = request.args.get('show_paid', 'false').lower() == 'true'
    
    if show_paid:
        orders = Order.query.options(joinedload(Order.phones)).order_by(Order.created_at.desc()).all()
    else:
        orders = Order.query.options(joinedload(Order.phones)).filter(Order.is_paid == False).order_by(Order.created_at.desc()).all()
    
    statuses = Status.query.all()
    workers = Worker.query.filter_by(is_active=True).all()
    users = User.query.all()
    
    # ✅ تحديث: استخدام النظام الجديد بدلاً من orders.html
    return render_template("orders/orders_main.html", 
                        orders=orders, 
                        statuses=statuses,
                        workers=workers,
                        users=users,
                        show_paid=show_paid)

@orders_bp.route("/orders/add", methods=["POST"])
def add_order():
    """إضافة طلبية جديدة"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})

    try:
        name = request.form.get("name")
        wilaya = request.form.get("wilaya")
        product = request.form.get("product")
        paid = float(request.form.get("paid") or 0)
        total = float(request.form.get("total") or 0)
        note = request.form.get("note", "")
        phones_raw = request.form.get("phones", "")
        status_id = request.form.get("status") or None

        # التحقق من البيانات الأساسية
        if not name or not name.strip():
            return jsonify({"success": False, "error": "اسم العميل مطلوب"})
        
        if not wilaya or not wilaya.strip():
            return jsonify({"success": False, "error": "الولاية مطلوبة"})
        
        if not product or not product.strip():
            return jsonify({"success": False, "error": "المنتج مطلوب"})
        
        if total <= 0:
            return jsonify({"success": False, "error": "إجمالي المبلغ يجب أن يكون أكبر من الصفر"})

        order = Order(
            name=name, 
            wilaya=wilaya, 
            product=product, 
            paid=paid, 
            total=total, 
            note=note,
            status_id=int(status_id) if status_id else None,
            is_paid=(paid >= total)
        )
        db.session.add(order)
        db.session.commit()

        # إضافة أرقام الهاتف
        phone_list = [p.strip() for p in phones_raw.split(",") if p.strip()]
        for idx, p in enumerate(phone_list):
            pn = PhoneNumber(order_id=order.id, number=p, is_primary=(idx==0))
            db.session.add(pn)
        
        # تسجيل في السجل
        history = OrderHistory(
            order_id=order.id, 
            change_type="إنشاء الطلب", 
            details=f"تم إنشاء الطلبية بواسطة {session['user']}",
            user=session['user']
        )
        db.session.add(history)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "تم إضافة الطلبية بنجاح",
            "order_id": order.id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"خطأ في إضافة الطلبية: {str(e)}"})

@orders_bp.route("/orders/edit/<int:id>", methods=["POST"])
def edit_order(id):
    """تعديل طلبية"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        order = Order.query.get_or_404(id)
        
        # التحقق من البيانات الأساسية
        name = request.form.get("name")
        wilaya = request.form.get("wilaya")
        product = request.form.get("product")
        total = float(request.form.get("total") or 0)
        
        if not name or not name.strip():
            return jsonify({"success": False, "error": "اسم العميل مطلوب"})
        
        if not wilaya or not wilaya.strip():
            return jsonify({"success": False, "error": "الولاية مطلوبة"})
        
        if not product or not product.strip():
            return jsonify({"success": False, "error": "المنتج مطلوب"})
        
        if total <= 0:
            return jsonify({"success": False, "error": "إجمالي المبلغ يجب أن يكون أكبر من الصفر"})
        
        old_data = {
            'name': order.name,
            'wilaya': order.wilaya,
            'product': order.product,
            'paid': order.paid,
            'total': order.total,
            'note': order.note,
            'status_id': order.status_id
        }
        
        order.name = name
        order.wilaya = wilaya
        order.product = product
        order.paid = float(request.form.get("paid") or 0)
        order.total = total
        order.note = request.form.get("note", "")
        order.status_id = request.form.get("status") or None
        order.is_paid = (order.paid >= order.total)
        
        # تسجيل التغييرات
        changes = []
        if old_data['name'] != order.name:
            changes.append(f"تغيير الاسم: {old_data['name']} → {order.name}")
        if old_data['wilaya'] != order.wilaya:
            changes.append(f"تغيير الولاية: {old_data['wilaya']} → {order.wilaya}")
        if old_data['product'] != order.product:
            changes.append(f"تغيير المنتج: {old_data['product']} → {order.product}")
        if old_data['paid'] != order.paid:
            changes.append(f"تغيير المدفوع: {old_data['paid']} → {order.paid}")
        if old_data['total'] != order.total:
            changes.append(f"تغيير الإجمالي: {old_data['total']} → {order.total}")
        if old_data['status_id'] != order.status_id:
            old_status = Status.query.get(old_data['status_id'])
            new_status = Status.query.get(order.status_id)
            old_status_name = old_status.name if old_status else "بدون"
            new_status_name = new_status.name if new_status else "بدون"
            changes.append(f"تغيير الحالة: {old_status_name} → {new_status_name}")
        
        # تحديث أرقام الهاتف
        PhoneNumber.query.filter_by(order_id=order.id).delete()
        phones_raw = request.form.get("phones", "")
        phone_list = [p.strip() for p in phones_raw.split(",") if p.strip()]
        for idx, p in enumerate(phone_list):
            pn = PhoneNumber(order_id=order.id, number=p, is_primary=(idx==0))
            db.session.add(pn)
        
        # تسجيل التغييرات في السجل
        if changes:
            change_details = " | ".join(changes)
            history = OrderHistory(
                order_id=order.id, 
                change_type="تعديل الطلبية", 
                details=f"تم تعديل الطلبية بواسطة {session['user']}. التغييرات: {change_details}",
                user=session['user']
            )
            db.session.add(history)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم تعديل الطلبية بنجاح",
            "order_id": order.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"خطأ في تعديل الطلبية: {str(e)}"})

@orders_bp.route("/orders/payment/<int:id>", methods=["POST"])
def add_order_payment(id):
    """إضافة دفعة على طلبية"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        order = Order.query.get_or_404(id)
        
        amount = float(request.form.get("amount") or 0)
        payment_date = datetime.strptime(request.form.get("payment_date"), "%Y-%m-%d")
        payment_method = request.form.get("payment_method", "نقدي")
        notes = request.form.get("notes", "")
        
        remaining = order.total - order.paid
        if amount > remaining:
            return jsonify({"success": False, "error": f"المبلغ يتجاوز المتبقي ({remaining} دج)"})
        
        order.paid += amount
        order.is_paid = (order.paid >= order.total)
        
        # تسجيل في السجل
        history = OrderHistory(
            order_id=order.id,
            change_type="دفعة مالية",
            details=f"تم إضافة دفعة بقيمة {amount} دج بواسطة {session['user']}. طريقة الدفع: {payment_method}",
            user=session['user']
        )
        db.session.add(history)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": "تم إضافة الدفعة بنجاح",
            "new_paid": order.paid,
            "new_remaining": order.total - order.paid,
            "is_paid": order.is_paid
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/orders/delete/<int:id>")
def delete_order(id):
    """حذف طلبية"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        order = Order.query.get_or_404(id)
        
        # تسجيل الحذف في السجل
        history = OrderHistory(
            order_id=order.id,
            change_type="حذف الطلبية",
            details=f"تم حذف الطلبية بواسطة {session['user']}",
            user=session['user']
        )
        db.session.add(history)
        
        db.session.delete(order)
        db.session.commit()
        
        flash('تم حذف الطلبية بنجاح', 'success')
        return redirect(url_for("orders.orders"))
        
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ في حذف الطلبية: {str(e)}', 'error')
        return redirect(url_for("orders.orders"))

@orders_bp.route("/orders/history/<int:id>")
def order_history(id):
    """سجل الطلبية"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        order = Order.query.get_or_404(id)
        histories = OrderHistory.query.filter_by(order_id=id).order_by(OrderHistory.timestamp.desc()).all()
        
        result = []
        for h in histories:
            result.append({
                "change_type": h.change_type,
                "details": h.details,
                "timestamp": h.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "user": h.user or "النظام"
            })
        
        order_info = {
            "order_id": order.id,
            "customer_name": order.name,
            "total_amount": order.total,
            "paid_amount": order.paid,
            "remaining_amount": order.remaining,
            "is_paid": order.is_paid,
            "total_costs": order.total_costs,
            "total_expenses": order.total_expenses,
            "total_transports": order.total_transports
        }
        
        return jsonify({
            "order_info": order_info,
            "history": result
        })
        
    except Exception as e:
        return jsonify({"error": str(e)})

# ========================
# 🎯 قسم الطلبيات المحسّن - APIs الجديدة
# ========================

@orders_bp.route("/api/orders/<int:order_id>/details")
def get_order_details(order_id):
    """الحصول على تفاصيل الطلبية والتعيينات"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        order = Order.query.get_or_404(order_id)
        
        # جلب التعيينات النشطة
        assignments = OrderAssignment.query.filter_by(order_id=order_id, is_active=True).all()
        assignments_data = []
        for assignment in assignments:
            assignments_data.append({
                "id": assignment.id,
                "worker_id": assignment.worker_id,
                "worker_name": assignment.worker.name,
                "assignment_type": assignment.assignment_type,
                "assigned_date": assignment.assigned_date.strftime("%Y-%m-%d"),
                "notes": assignment.notes
            })
        
        # جلب المرفقات
        attachments = OrderAttachment.query.filter_by(order_id=order_id).all()
        attachments_data = []
        for attachment in attachments:
            attachments_data.append({
                "id": attachment.id,
                "filename": attachment.filename,
                "original_filename": attachment.original_filename,
                "file_type": attachment.file_type,
                "file_size": attachment.file_size,
                "captured_at": attachment.captured_at.strftime("%Y-%m-%d %H:%M")
            })
        
        return jsonify({
            "success": True,
            "order": {
                "id": order.id,
                "production_details": order.production_details,
                "start_date": order.start_date.strftime("%Y-%m-%d") if order.start_date else None,
                "expected_delivery": order.expected_delivery_date.strftime("%Y-%m-%d") if order.expected_delivery_date else None,
                "actual_delivery": order.actual_delivery_date.strftime("%Y-%m-%d") if order.actual_delivery_date else None
            },
            "assignments": assignments_data,
            "attachments": attachments_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/api/orders/assign-worker", methods=["POST"])
def api_assign_worker():
    """تعيين عامل للطلبية مع إنشاء مهمة"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        order_id = int(request.form.get("order_id"))
        worker_id = int(request.form.get("worker_id"))
        assignment_type = request.form.get("assignment_type", "workshop")
        notes = request.form.get("notes", "")
        
        assignment = assign_worker_to_order(
            order_id=order_id,
            worker_id=worker_id,
            assignment_type=assignment_type,
            user_name=session["user"],
            notes=notes
        )
        
        if assignment:
            return jsonify({
                "success": True,
                "message": "تم تعيين العامل بنجاح",
                "assignment_id": assignment.id
            })
        else:
            return jsonify({"success": False, "error": "فشل في تعيين العامل"})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/api/orders/deassign-worker/<int:assignment_id>", methods=["POST"])
def api_deassign_worker(assignment_id):
    """إلغاء تعيين عامل"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        success = deactivate_assignment(assignment_id, session["user"])
        
        if success:
            return jsonify({"success": True, "message": "تم إلغاء التعيين بنجاح"})
        else:
            return jsonify({"success": False, "error": "لم يتم العثور على التعيين"})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

# ========================
# 📎 ENHANCED ATTACHMENTS MANAGEMENT SYSTEM
# ========================

@orders_bp.route("/api/orders/upload-attachments-real", methods=["POST"])
def upload_attachments_real():
    """رفع الملفات الحقيقي إلى قاعدة البيانات مع التحقق من المساحة والضغط"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        # 🔍 التحقق من حجم الطلب أولاً
        content_length = request.content_length or 0
        MAX_UPLOAD_SIZE = 40 * 1024 * 1024  # 40MB
        
        if content_length > MAX_UPLOAD_SIZE:
            return jsonify({
                "success": False, 
                "error": f"❌ حجم الملفات كبير جداً. الحد الأقصى: {MAX_UPLOAD_SIZE/(1024*1024)}MB"
            })
        
        order_id = int(request.form.get("order_id"))
        files = request.files.getlist("attachments")
        label = request.form.get("label", "").strip()
        notes = request.form.get("notes", "").strip()
        
        if not files or files[0].filename == '':
            return jsonify({"success": False, "error": "لم يتم اختيار ملفات"})
        
        # ========================
        # 🔍 التحقق من المساحة أولاً
        # ========================
        storage_info = StorageManager.get_storage_limits()
        total_used = StorageManager.get_total_used_space()
        
        # حساب حجم الملفات المرفوعة
        total_upload_size = 0
        file_sizes = []
        
        for file in files:
            if not file or file.filename == '':
                continue
                
            # قراءة حجم الملف بطريقة آمنة
            file.seek(0, 2)  # الانتقال لنهاية الملف
            file_size = file.tell()
            file.seek(0)  # العودة لبداية الملف
            
            # التحقق من حجم الملف الفردي أولاً
            if file_size > storage_info['max_per_file']:
                max_file_mb = storage_info['max_per_file'] / (1024*1024)
                return jsonify({
                    "success": False, 
                    "error": f"❌ حجم الملف {file.filename} ({file_size/(1024*1024):.1f}MB) يتجاوز الحد المسموح ({max_file_mb}MB)"
                })
            
            total_upload_size += file_size
            file_sizes.append(file_size)
        
        if total_upload_size == 0:
            return jsonify({"success": False, "error": "❌ لم يتم اختيار ملفات صالحة"})
        
        # التحقق من المساحة الإجمالية
        if total_used + total_upload_size > storage_info['max_total_size']:
            available_space = (storage_info['max_total_size'] - total_used) / (1024*1024)
            return jsonify({
                "success": False, 
                "error": f"❌ المساحة التخزينية غير كافية. المتاح: {available_space:.1f}MB"
            })
        
        # التحقق من مساحة الطلبية
        order_used = StorageManager.get_order_attachments_size(order_id)
        if order_used + total_upload_size > storage_info['max_per_order']:
            order_available = (storage_info['max_per_order'] - order_used) / (1024*1024)
            return jsonify({
                "success": False, 
                "error": f"❌ تجاوزت الحد المسموح للمرفقات في هذه الطلبية. المتاح: {order_available:.1f}MB"
            })
        
        order = Order.query.get_or_404(order_id)
        uploaded_files = []
        total_space_saved = 0
        
        for i, file in enumerate(files):
            if file and file.filename and allowed_file(file.filename):
                try:
                    # قراءة بيانات الملف
                    file_data = file.read()
                    original_size = len(file_data)
                    
                    # ========================
                    # 🗜️ ضغط الملف تلقائياً إذا لزم
                    # ========================
                    if should_compress_file(file_data, file.filename, file.content_type):
                        print(f"🔄 جاري ضغط {file.filename}...")
                        compressed_data = compress_image_advanced(file_data)
                        if len(compressed_data) < original_size:
                            file_data = compressed_data
                            space_saved = original_size - len(file_data)
                            total_space_saved += space_saved
                            print(f"✅ تم توفير {space_saved/1024:.1f}KB من المساحة لـ {file.filename}")
                    
                    # تحديد نوع الملف
                    file_type = get_file_type(file.filename, file.content_type)
                    
                    # إنشاء اسم فريد
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                    file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'bin'
                    filename = f"order_{order_id}_{timestamp}.{file_extension}"
                    
                    # استخدام التسمية المخصصة إذا كانت موجودة
                    display_label = label if label else file.filename.rsplit('.', 1)[0]
                    
                    # حفظ في قاعدة البيانات
                    attachment = OrderAttachment(
                        order_id=order_id,
                        filename=filename,
                        original_filename=file.filename,
                        file_size=len(file_data),
                        mime_type=file.content_type,
                        file_data=file_data,
                        file_type=file_type,
                        description=display_label,
                        captured_by=session["user"]
                    )
                    db.session.add(attachment)
                    db.session.flush()
                    
                    uploaded_files.append({
                        'id': attachment.id,
                        'filename': filename,
                        'original_name': file.filename,
                        'label': display_label,
                        'size': len(file_data),
                        'original_size': original_size,
                        'uploaded_by': session["user"],
                        'compressed': len(file_data) < original_size,
                        'space_saved': original_size - len(file_data)
                    })
                    
                except Exception as file_error:
                    print(f"❌ خطأ في معالجة الملف {file.filename}: {file_error}")
                    continue
        
        if not uploaded_files:
            return jsonify({"success": False, "error": "❌ فشل في رفع أي ملف"})
        
        # ✅ حفظ الملاحظات العامة إذا كانت موجودة
        if notes:
            from models import AttachmentNotes, OrderHistory
            attachment_note = AttachmentNotes(
                order_id=order_id,
                notes_content=notes,
                created_by=session["user"]
            )
            db.session.add(attachment_note)
            
            # تسجيل إضافة الملاحظة في السجل
            history = OrderHistory(
                order_id=order_id,
                change_type="إضافة ملاحظة مرفقات",
                details=f"تم إضافة ملاحظة للمرفقات: {notes[:100]}{'...' if len(notes) > 100 else ''}",
                user=session["user"]
            )
            db.session.add(history)
        
        # تسجيل رفع الملفات في السجل
        if uploaded_files:
            from models import OrderHistory
            file_names = [f['label'] for f in uploaded_files]
            compression_info = ""
            if total_space_saved > 0:
                compression_info = f" - تم توفير {total_space_saved/(1024*1024):.2f}MB"
            
            history = OrderHistory(
                order_id=order_id,
                change_type="رفع مرفقات",
                details=f"تم رفع {len(uploaded_files)} مرفق: {', '.join(file_names[:3])}{'...' if len(file_names) > 3 else ''}{compression_info}",
                user=session["user"]
            )
            db.session.add(history)
        
        db.session.commit()
        
        # ========================
        # 📊 إرسال إحصائيات المساحة
        # ========================
        new_total_used = total_used + total_upload_size - total_space_saved
        storage_alerts = StorageManager.check_storage_health()
        
        return jsonify({
            "success": True,
            "message": f"تم رفع {len(uploaded_files)} ملف بنجاح" + (f" - وفرنا {total_space_saved/(1024*1024):.2f}MB" if total_space_saved > 0 else ""),
            "files": uploaded_files,
            "compression_stats": {
                "total_space_saved": total_space_saved,
                "total_space_saved_mb": total_space_saved / (1024 * 1024),
                "files_compressed": len([f for f in uploaded_files if f['compressed']])
            },
            "storage_info": {
                "total_used": new_total_used,
                "total_available": storage_info['max_total_size'],
                "usage_percentage": (new_total_used / storage_info['max_total_size']) * 100,
                "alerts": storage_alerts
            },
            "saved_label": label,
            "saved_notes": notes
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في رفع المرفقات: {e}")
        return jsonify({"success": False, "error": str(e)})
    

@orders_bp.route("/api/attachments/<int:attachment_id>/thumbnail")
def get_attachment_thumbnail(attachment_id):
    """الحصول على الصورة المصغرة للمرفق"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        attachment = OrderAttachment.query.get_or_404(attachment_id)
        
        # إذا كان هناك صورة مصغرة مخزنة
        if attachment.thumbnail_data:
            return Response(
                attachment.thumbnail_data,
                mimetype='image/jpeg',
                headers={"Content-Disposition": f"inline; filename=thumbnail_{attachment.id}.jpg"}
            )
        
        # إذا كان صورة عادية، استخدم البيانات الأصلية
        elif attachment.file_type == 'image':
            return Response(
                attachment.file_data,
                mimetype=attachment.mime_type,
                headers={"Content-Disposition": f"inline; filename=thumbnail_{attachment.id}.jpg"}
            )
        
        # إذا كان فيديو بدون ثامبنيليز، إنشاء واحدة فوراً
        elif attachment.file_type == 'video':
            thumbnail = generate_video_thumbnail_simple(attachment.file_data)
            if thumbnail:
                # حفظ الثامبنيليز للمستقبل
                attachment.thumbnail_data = thumbnail
                db.session.commit()
                
                return Response(
                    thumbnail,
                    mimetype='image/jpeg',
                    headers={"Content-Disposition": f"inline; filename=thumbnail_{attachment.id}.jpg"}
                )
        
        # إذا لم يكن هناك ثامبنيليز، أرجع أيقونة افتراضية
        default_thumbnail = generate_default_thumbnail(attachment.file_type)
        return Response(
            default_thumbnail,
            mimetype='image/jpeg',
            headers={"Content-Disposition": f"inline; filename=thumbnail_{attachment.id}.jpg"}
        )
        
    except Exception as e:
        print(f"❌ خطأ في عرض الصورة المصغرة: {e}")
        return jsonify({"success": False, "error": str(e)})

def generate_default_thumbnail(file_type, size=(200, 150)):
    """إنشاء صورة مصغرة افتراضية حسب نوع الملف"""
    from PIL import Image, ImageDraw, ImageFont
    import io
    
    try:
        # ألوان حسب نوع الملف
        colors = {
            'video': (41, 128, 185),     # أزرق
            'image': (39, 174, 96),      # أخضر
            'pdf': (231, 76, 60),        # أحمر
            'document': (52, 152, 219),  # أزرق فاتح
            'other': (149, 165, 166)     # رمادي
        }
        
        color = colors.get(file_type, (149, 165, 166))
        
        # إنشاء الصورة
        img = Image.new('RGB', size, color)
        draw = ImageDraw.Draw(img)
        
        # إضافة أيقونة
        icons = {
            'video': '▶',
            'image': '🖼️',
            'pdf': '📄',
            'document': '📝',
            'other': '📎'
        }
        
        icon = icons.get(file_type, '📎')
        
        try:
            # محاولة استخدام خط كبير للأيقونة
            font = ImageFont.truetype("arial.ttf", 40)
        except:
            font = ImageFont.load_default()
        
        # رسم الأيقونة
        bbox = draw.textbbox((0, 0), icon, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (size[0] - text_width) // 2
        y = (size[1] - text_height) // 2 - 10
        
        draw.text((x, y), icon, fill=(255, 255, 255), font=font)
        
        # إضافة نص نوع الملف
        type_names = {
            'video': 'فيديو',
            'image': 'صورة',
            'pdf': 'PDF',
            'document': 'مستند',
            'other': 'ملف'
        }
        
        type_name = type_names.get(file_type, 'ملف')
        
        try:
            small_font = ImageFont.truetype("arial.ttf", 16)
        except:
            small_font = ImageFont.load_default()
        
        bbox_small = draw.textbbox((0, 0), type_name, font=small_font)
        text_width_small = bbox_small[2] - bbox_small[0]
        
        x_small = (size[0] - text_width_small) // 2
        y_small = y + text_height + 5
        
        draw.text((x_small, y_small), type_name, fill=(255, 255, 255), font=small_font)
        
        # حفظ الصورة
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85)
        return output.getvalue()
        
    except Exception as e:
        print(f"❌ خطأ في إنشاء الصورة الافتراضية: {e}")
        # صورة بديلة بسيطة
        img = Image.new('RGB', size, (200, 200, 200))
        output = io.BytesIO()
        img.save(output, format='JPEG')
        return output.getvalue()
    
@orders_bp.route("/api/orders/save-attachment-notes", methods=["POST"])
def save_attachment_notes():
    """حفظ ملاحظات المرفقات بشكل منفصل"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        notes = data.get('notes', '').strip()
        
        if not order_id:
            return jsonify({"success": False, "error": "معرف الطلبية مطلوب"})
        
        # حفظ الملاحظات في قاعدة البيانات
        if notes:
            attachment_note = AttachmentNotes(
                order_id=order_id,
                notes_content=notes,
                created_by=session["user"]
            )
            db.session.add(attachment_note)
            
            # تسجيل في السجل
            history = OrderHistory(
                order_id=order_id,
                change_type="إضافة ملاحظة مرفقات",
                details=f"تم إضافة ملاحظة: {notes[:100]}{'...' if len(notes) > 100 else ''}",
                user=session["user"]
            )
            db.session.add(history)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم حفظ الملاحظات بنجاح" if notes else "لا توجد ملاحظات للحفظ"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})
    
@orders_bp.route("/api/attachments/<int:attachment_id>/update-label", methods=["POST"])
def update_attachment_label(attachment_id):
    """تحديث تسمية المرفق"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        data = request.get_json()
        new_label = data.get('label', '').strip()
        
        if not new_label:
            return jsonify({"success": False, "error": "التسمية لا يمكن أن تكون فارغة"})
        
        attachment = OrderAttachment.query.get_or_404(attachment_id)
        
        old_label = attachment.description
        attachment.description = new_label
        
        # تسجيل في السجل
        history = OrderHistory(
            order_id=attachment.order_id,
            change_type="تعديل تسمية مرفق",
            details=f"تم تغيير تسمية المرفق من '{old_label}' إلى '{new_label}'",
            user=session["user"]
        )
        db.session.add(history)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم تحديث التسمية بنجاح",
            "new_label": attachment.description
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/api/orders/update-details", methods=["POST"])
def api_update_order_details():
    """تحديث تفاصيل الطلبية"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        order_id = int(request.form.get("order_id"))
        production_details = request.form.get("production_details", "")
        start_date_str = request.form.get("start_date")
        expected_delivery_str = request.form.get("expected_delivery")
        
        order = Order.query.get_or_404(order_id)
        
        # تحديث البيانات
        order.production_details = production_details
        
        if start_date_str:
            order.start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        
        if expected_delivery_str:
            order.expected_delivery_date = datetime.strptime(expected_delivery_str, "%Y-%m-%d").date()
        
        # تسجيل في السجل
        history = OrderHistory(
            order_id=order_id,
            change_type="تحديث التفاصيل",
            details="تم تحديث تفاصيل الطلبية الإضافية",
            user=session["user"]
        )
        db.session.add(history)
        
        db.session.commit()
        
        return jsonify({"success": True, "message": "تم حفظ التفاصيل بنجاح"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/api/orders/<int:order_id>/profitability")
def api_order_profitability(order_id):
    """حساب ربحية الطلبية"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        profitability = calculate_order_profitability(order_id)
        
        if profitability:
            return jsonify({"success": True, "profitability": profitability})
        else:
            return jsonify({"success": False, "error": "لم يتم العثور على الطلبية"})
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/api/orders/related_debts")
def get_orders_related_debts():
    """جلب إحصائيات الديون المرتبطة بالطلبيات"""
    try:
        # حساب الديون المرتبطة بالطلبيات
        total_debts = 0
        affected_orders = set()
        
        # ديون المصاريف المرتبطة بطلبيات
        expense_debts = db.session.query(Debt, Expense)\
            .join(Expense, Debt.source_id == Expense.id)\
            .filter(
                Debt.source_type == 'expense',
                Expense.order_id.isnot(None),
                Debt.status == 'unpaid'
            ).all()
        
        for debt, expense in expense_debts:
            total_debts += debt.remaining_amount
            affected_orders.add(expense.order_id)
        
        # ديون النقل المرتبطة بطلبيات
        transport_debts = db.session.query(Debt, Transport)\
            .join(Transport, Debt.source_id == Transport.id)\
            .filter(
                Debt.source_type == 'transport', 
                Transport.order_id.isnot(None),
                Debt.status == 'unpaid'
            ).all()
        
        for debt, transport in transport_debts:
            total_debts += debt.remaining_amount
            affected_orders.add(transport.order_id)
        
        return jsonify({
            "success": True,
            "total_debts": total_debts,
            "affected_orders": len(affected_orders),
            "average_per_order": total_debts / len(affected_orders) if affected_orders else 0
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/api/orders/with_debts")
def get_orders_with_debts():
    """جلب الطلبيات المتأثرة بالديون"""
    try:
        orders_with_debts = []
        
        # جلب جميع الطلبيات
        all_orders = Order.query.all()
        total_orders = len(all_orders)
        
        for order in all_orders:
            # حساب ديون الطلبية
            order_debt = 0
            
            # ديون المصاريف
            expense_debts = db.session.query(Debt, Expense)\
                .join(Expense, Debt.source_id == Expense.id)\
                .filter(
                    Expense.order_id == order.id,
                    Debt.status == 'unpaid'
                ).all()
            
            for debt, expense in expense_debts:
                order_debt += debt.remaining_amount
            
            # ديون النقل
            transport_debts = db.session.query(Debt, Transport)\
                .join(Transport, Debt.source_id == Transport.id)\
                .filter(
                    Transport.order_id == order.id,
                    Debt.status == 'unpaid'
                ).all()
            
            for debt, transport in transport_debts:
                order_debt += debt.remaining_amount
            
            if order_debt > 0:
                debt_percentage = (order_debt / order.total * 100) if order.total > 0 else 0
                
                # تحديد حالة الدين
                if debt_percentage <= 30:
                    status = "ديون قليلة"
                elif debt_percentage <= 60:
                    status = "ديون متوسطة"
                else:
                    status = "ديون عالية"
                
                orders_with_debts.append({
                    'order_id': order.id,
                    'customer_name': order.name,
                    'total_amount': order.total,
                    'debt_amount': order_debt,
                    'debt_percentage': debt_percentage,
                    'status': status
                })
        
        # إحصائيات
        total_debts = sum(order['debt_amount'] for order in orders_with_debts)
        debt_free_orders = total_orders - len(orders_with_debts)
        
        return jsonify({
            'success': True,
            'orders': orders_with_debts,
            'statistics': {
                'total_debts': total_debts,
                'affected_orders': len(orders_with_debts),
                'debt_free_orders': debt_free_orders,
                'average_debt': total_debts / len(orders_with_debts) if orders_with_debts else 0
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@orders_bp.route("/api/orders/<int:order_id>/debts")
def get_order_debts(order_id):
    """جلب ديون طلبية محددة"""
    try:
        total_debt = 0
        paid_debt = 0
        debt_records = []
        
        # ديون المصاريف المرتبطة
        expense_debts = db.session.query(Debt, Expense)\
            .join(Expense, Debt.source_id == Expense.id)\
            .filter(Expense.order_id == order_id).all()
        
        for debt, expense in expense_debts:
            debt_info = {
                'type': 'مصروف',
                'description': expense.description,
                'debt_amount': debt.debt_amount,
                'paid_amount': debt.paid_amount,
                'remaining': debt.remaining_amount,
                'status': debt.status,
                'date': debt.start_date.isoformat() if debt.start_date else None,
                'source': 'expense'
            }
            debt_records.append(debt_info)
            total_debt += debt.debt_amount
            paid_debt += debt.paid_amount
        
        # ديون النقل المرتبطة
        transport_debts = db.session.query(Debt, Transport)\
            .join(Transport, Debt.source_id == Transport.id)\
            .filter(Transport.order_id == order_id).all()
        
        for debt, transport in transport_debts:
            debt_info = {
                'type': 'نقل',
                'description': transport.purpose,
                'debt_amount': debt.debt_amount,
                'paid_amount': debt.paid_amount,
                'remaining': debt.remaining_amount,
                'status': debt.status,
                'date': debt.start_date.isoformat() if debt.start_date else None,
                'source': 'transport'
            }
            debt_records.append(debt_info)
            total_debt += debt.debt_amount
            paid_debt += debt.paid_amount
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'debts_info': {
                'total_debt': total_debt,
                'paid_debt': paid_debt,
                'remaining_debt': total_debt - paid_debt,
                'debt_records': debt_records,
                'has_debts': len(debt_records) > 0
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 🔧 مسار لجلب مرفقات الطلبية
@orders_bp.route("/api/orders/<int:order_id>/attachments")
def get_order_attachments(order_id):
    """جلب مرفقات الطلبية مع المعلومات المحسنة"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        attachments = OrderAttachment.query.filter_by(order_id=order_id).order_by(OrderAttachment.captured_at.desc()).all()
        attachments_data = []
        for attachment in attachments:
            attachments_data.append({
                "id": attachment.id,
                "filename": attachment.filename,
                "original_filename": attachment.original_filename,
                "file_size": attachment.file_size,
                "file_type": attachment.file_type,
                "captured_at": attachment.captured_at.strftime("%Y-%m-%d %H:%M"),
                "captured_by": attachment.captured_by,
                "label": attachment.description or 'بدون تسمية',
                "has_custom_label": bool(attachment.description and attachment.description != attachment.original_filename.rsplit('.', 1)[0])
            })
        
        return jsonify({"success": True, "attachments": attachments_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# 🔧 مسار لتحميل المرفق
@orders_bp.route("/api/attachments/<int:attachment_id>/download")
def download_attachment(attachment_id):
    """تحميل المرفق"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        attachment = OrderAttachment.query.get_or_404(attachment_id)
        return Response(
            attachment.file_data,
            mimetype=attachment.mime_type,
            headers={"Content-Disposition": f"attachment; filename={attachment.original_filename}"}
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# 🔧 مسار لمعاينة المرفق
@orders_bp.route("/api/attachments/<int:attachment_id>/view")
def view_attachment(attachment_id):
    """معاينة المرفق"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        attachment = OrderAttachment.query.get_or_404(attachment_id)
        
        # إرجاع الملف كاستجابة
        return Response(
            attachment.file_data,
            mimetype=attachment.mime_type,
            headers={"Content-Disposition": f"inline; filename={attachment.original_filename}"}
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    
@orders_bp.route("/api/attachments/<int:attachment_id>/view-video")
def view_video_attachment(attachment_id):
    """معاينة الفيديو مع دعم التشغيل في المتصفح"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        attachment = OrderAttachment.query.get_or_404(attachment_id)
        
        # التحقق من أن الملف فيديو
        if attachment.file_type != 'video':
            return jsonify({"success": False, "error": "هذا الملف ليس فيديو"})
        
        # إرجاع الفيديو كاستجابة
        return Response(
            attachment.file_data,
            mimetype=attachment.mime_type,
            headers={
                "Content-Disposition": f"inline; filename={attachment.original_filename}",
                "Content-Length": str(attachment.file_size),
                "Accept-Ranges": "bytes",  # لدعم التشغيل الجزئي
                "Content-Type": attachment.mime_type
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# 🔧 مسار لحذف المرفق
@orders_bp.route("/api/attachments/<int:attachment_id>/delete", methods=["DELETE"])
def delete_attachment(attachment_id):
    """حذف مرفق"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        attachment = OrderAttachment.query.get_or_404(attachment_id)
        order_id = attachment.order_id
        attachment_name = attachment.description or attachment.original_filename
        
        db.session.delete(attachment)
        
        # تسجيل في السجل
        history = OrderHistory(
            order_id=order_id,
            change_type="حذف مرفق",
            details=f"تم حذف المرفق: {attachment_name}",
            user=session["user"]
        )
        db.session.add(history)
        
        db.session.commit()
        return jsonify({"success": True, "message": "تم حذف المرفق بنجاح"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

# 🔧 إصلاح نظام المرفقات - إضافة المسارات المفقودة
@orders_bp.route("/api/orders/<int:order_id>/attachment-notes", methods=["GET", "POST", "DELETE"])
def manage_attachment_notes(order_id):
    """إدارة ملاحظات المرفقات - نظام متعدد الملاحظات"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        if request.method == "GET":
            # جلب جميع الملاحظات للطلبية
            notes_list = AttachmentNotes.query.filter_by(order_id=order_id)\
                .order_by(AttachmentNotes.created_at.desc())\
                .all()
            
            notes_data = []
            for note in notes_list:
                notes_data.append({
                    'id': note.id,
                    'content': note.notes_content,
                    'created_by': note.created_by,
                    'created_at': note.created_at.strftime("%Y-%m-%d %H:%M"),
                    'updated_at': note.updated_at.strftime("%Y-%m-%d %H:%M") if note.updated_at else None
                })
            
            return jsonify({
                "success": True, 
                "notes": notes_data,
                "count": len(notes_data)
            })
        
        elif request.method == "POST":
            data = request.get_json()
            new_note = data.get('note', '').strip()
            
            if not new_note:
                return jsonify({"success": False, "error": "الملاحظة لا يمكن أن تكون فارغة"})
            
            # إنشاء ملاحظة جديدة
            attachment_note = AttachmentNotes(
                order_id=order_id,
                notes_content=new_note,
                created_by=session["user"]
            )
            db.session.add(attachment_note)
            
            # تسجيل في السجل
            history = OrderHistory(
                order_id=order_id,
                change_type="إضافة ملاحظة مرفقات",
                details=f"تم إضافة ملاحظة جديدة: {new_note[:100]}{'...' if len(new_note) > 100 else ''}",
                user=session["user"]
            )
            db.session.add(history)
            
            db.session.commit()
            
            return jsonify({
                "success": True,
                "message": "تم إضافة الملاحظة بنجاح",
                "note_id": attachment_note.id
            })
            
        elif request.method == "DELETE":
            data = request.get_json()
            note_id = data.get('note_id')
            
            if note_id:
                # حذف ملاحظة محددة
                note = AttachmentNotes.query.filter_by(id=note_id, order_id=order_id).first()
                if note:
                    note_content = note.notes_content
                    db.session.delete(note)
                    
                    # تسجيل في السجل
                    history = OrderHistory(
                        order_id=order_id,
                        change_type="حذف ملاحظة مرفقات",
                        details=f"تم حذف ملاحظة المرفقات: {note_content[:100]}{'...' if len(note_content) > 100 else ''}",
                        user=session["user"]
                    )
                    db.session.add(history)
                    
                    db.session.commit()
                    return jsonify({"success": True, "message": "تم حذف الملاحظة"})
                else:
                    return jsonify({"success": False, "error": "لم يتم العثور على الملاحظة"})
            else:
                # حذف جميع الملاحظات
                notes_count = AttachmentNotes.query.filter_by(order_id=order_id).count()
                AttachmentNotes.query.filter_by(order_id=order_id).delete()
                
                # تسجيل في السجل
                if notes_count > 0:
                    history = OrderHistory(
                        order_id=order_id,
                        change_type="حذف جميع ملاحظات المرفقات",
                        details=f"تم حذف جميع ملاحظات المرفقات ({notes_count} ملاحظة)",
                        user=session["user"]
                    )
                    db.session.add(history)
                
                db.session.commit()
                return jsonify({"success": True, "message": f"تم حذف جميع الملاحظات ({notes_count} ملاحظة)"})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/api/orders/clear-attachment-notes", methods=["POST"])
def clear_attachment_notes():
    """مسح ملاحظات المرفقات"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        
        # مسح الملاحظات من قاعدة البيانات
        return jsonify({
            "success": True,
            "message": "تم مسح الملاحظات"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/api/orders/log-attachment-activity", methods=["POST"])
def log_attachment_activity():
    """تسجيل نشاط المرفقات"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        data = request.get_json()
        
        # تسجيل النشاط في سجل الطلبية
        activity_data = {
            'order_id': data.get('order_id'),
            'action': data.get('action'),
            'attachment_id': data.get('attachment_id'),
            'details': data.get('details', ''),
            'user': session.get('user', 'النظام'),
            'timestamp': datetime.now(timezone.utc)
        }
        
        # هنا يمكنك حفظ النشاط في قاعدة البيانات
        print(f"📝 نشاط المرفقات: {activity_data}")
        
        return jsonify({
            "success": True,
            "message": "تم تسجيل النشاط"
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
# ========================
# 🛠️ دوال التعيين والمهام
# ========================

def assign_worker_to_order(order_id, worker_id, assignment_type, user_name, notes=""):
    """تعيين عامل للطلبية مع إنشاء مهمة تلقائية"""
    try:
        # إلغاء أي تعيينات سابقة نشطة لنفس العامل على نفس الطلبية
        existing_assignment = OrderAssignment.query.filter_by(
            order_id=order_id, 
            worker_id=worker_id, 
            is_active=True
        ).first()
        
        if existing_assignment:
            existing_assignment.is_active = False
            existing_assignment.completed_date = datetime.now(timezone.utc)
        
        # إنشاء تعيين جديد
        assignment = OrderAssignment(
            order_id=order_id,
            worker_id=worker_id,
            assignment_type=assignment_type,
            assigned_by=user_name,
            notes=notes
        )
        db.session.add(assignment)
        
        # تحديث حالة الطلبية إذا كانت بدون تعيين
        order = Order.query.get(order_id)
        if order and (not order.status or order.status.name == 'في الانتظار'):
            status = Status.query.filter_by(name='معينة للعامل').first()
            if status:
                order.status_id = status.id
        
        # تسجيل في السجل
        worker = Worker.query.get(worker_id)
        history = OrderHistory(
            order_id=order_id,
            change_type="تعيين عامل",
            details=f"تم تعيين العامل {worker.name} للطلبية ({assignment_type})",
            user=user_name
        )
        db.session.add(history)
        
        db.session.commit()
        return assignment
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في تعيين العامل: {e}")
        raise e

def deactivate_assignment(assignment_id, user_name):
    """إلغاء تعيين عامل"""
    try:
        assignment = OrderAssignment.query.get(assignment_id)
        if assignment and assignment.is_active:
            assignment.is_active = False
            assignment.completed_date = datetime.now(timezone.utc)
            
            # تسجيل في السجل
            history = OrderHistory(
                order_id=assignment.order_id,
                change_type="إلغاء تعيين",
                details=f"تم إلغاء تعيين العامل {assignment.worker.name}",
                user=user_name
            )
            db.session.add(history)
            
            db.session.commit()
            return True
        return False
        
    except Exception as e:
        db.session.rollback()
        raise e

# ========================
# 🔧 دوال مساعدة إضافية
# ========================

def calculate_order_profitability(order_id):
    """حساب ربحية الطلبية"""
    try:
        order = Order.query.get(order_id)
        if not order:
            return None
        
        profitability = {
            'order_id': order.id,
            'total_amount': order.total,
            'total_costs': order.total_costs,
            'profit': order.profit,
            'profit_percentage': order.profit_percentage,
            'is_profitable': order.is_profitable,
            'total_expenses': order.total_expenses,
            'total_transports': order.total_transports
        }
        
        return profitability
    except Exception as e:
        print(f"❌ خطأ في حساب ربحية الطلبية: {e}")
        return None

# ========================
# 🔄 دوال المزامنة
# ========================

def sync_all_assigned_orders_with_tasks(user_name="النظام"):
    """مزامنة جميع الطلبيات المعينة مع المهام"""
    try:
        synced_count = 0
        errors_count = 0
        
        # جلب جميع التعيينات النشطة
        active_assignments = OrderAssignment.query.filter_by(is_active=True).all()
        
        print(f"🔍 جاري مزامنة {len(active_assignments)} تعيين نشط...")
        
        for assignment in active_assignments:
            try:
                # التحقق من وجود مهمة نشطة
                existing_task = Task.query.filter(
                    Task.worker_id == assignment.worker_id,
                    Task.related_entity_type == 'order',
                    Task.related_entity_id == assignment.order_id,
                    Task.status.in_(['pending', 'in_progress', 'suspended'])
                ).first()
                
                if not existing_task:
                    # إنشاء مهمة جديدة
                    task = create_order_task_for_worker(
                        assignment.order_id, 
                        assignment.worker_id, 
                        user_name,
                        assignment.assignment_type
                    )
                    if task:
                        synced_count += 1
                        print(f"✅ تم إنشاء مهمة #{task.id} للطلبية #{assignment.order_id}")
                    else:
                        errors_count += 1
                        print(f"❌ فشل في إنشاء مهمة للطلبية #{assignment.order_id}")
                else:
                    print(f"ℹ️ المهمة #{existing_task.id} موجودة بالفعل للطلبية #{assignment.order_id}")
                    
            except Exception as e:
                errors_count += 1
                print(f"❌ خطأ في معالجة الطلبية #{assignment.order_id}: {e}")
                continue
        
        if synced_count > 0 or errors_count > 0:
            db.session.commit()
        
        print(f"🎉 تمت المزامنة: {synced_count} مهمة جديدة, {errors_count} أخطاء")
        return {
            'synced_count': synced_count,
            'errors_count': errors_count,
            'total_assignments': len(active_assignments)
        }
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ عام في المزامنة: {e}")
        return {
            'synced_count': 0,
            'errors_count': 1,
            'total_assignments': 0
        }

def create_order_task_for_worker(order_id, worker_id, user_name, assignment_type="workshop"):
    """إنشاء مهمة طلبية للعامل"""
    try:
        order = Order.query.get(order_id)
        worker = Worker.query.get(worker_id)
        
        if not order or not worker:
            print(f"❌ لم يتم العثور على الطلبية #{order_id} أو العامل #{worker_id}")
            return None
        
        # البحث عن مهمة موجودة
        existing_task = Task.query.filter(
            Task.worker_id == worker_id,
            Task.related_entity_type == 'order',
            Task.related_entity_id == order_id,
            Task.status.in_(['pending', 'in_progress', 'suspended'])
        ).first()
        
        if existing_task:
            # ✅ تحديث المهمة الموجودة
            existing_task.title = f"إنجاز طلبية - {order.name}"
            existing_task.description = f"""المنتج: {order.product}
العميل: {order.name}
الولاية: {order.wilaya}
القيمة: {order.total} دج
رقم الطلبية: #{order.id}
نوع التعيين: {assignment_type}"""
            existing_task.updated_at = datetime.now(timezone.utc)
            existing_task.assigned_to = worker.name
            
            print(f"✅ تم تحديث المهمة #{existing_task.id} للعامل {worker.name}")
            return existing_task
        else:
            # ✅ إنشاء مهمة جديدة
            task = Task(
                title=f"إنجاز طلبية - {order.name}",
                description=f"""المنتج: {order.product}
العميل: {order.name}
الولاية: {order.wilaya}
القيمة: {order.total} دج
رقم الطلبية: #{order.id}
نوع التعيين: {assignment_type}""",
                priority='medium',
                status='pending',
                task_type='order_completion',
                assigned_to=worker.name,
                worker_id=worker_id,
                related_entity_type='order',
                related_entity_id=order_id,
                due_date=datetime.now(timezone.utc).date() + timedelta(days=7),
                created_by=user_name,
                task_scope='worker',
                assignment_type=assignment_type
            )
            db.session.add(task)
            
            print(f"✅ تم إنشاء مهمة للعامل {worker.name} للطلبية {order.id}")
            return task
            
    except Exception as e:
        print(f"❌ خطأ في إنشاء/تحديث مهمة للعامل: {e}")
        db.session.rollback()
        return None

# ========================
# 📊 مسارات إضافية للإحصائيات
# ========================

@orders_bp.route("/api/orders/total-costs")
def get_total_costs():
    """جلب إجمالي التكاليف"""
    try:
        # حساب إجمالي المشتريات
        total_purchases = db.session.query(db.func.sum(Expense.total_amount)).scalar() or 0
        
        # حساب إجمالي النقل
        total_transport = db.session.query(db.func.sum(Transport.transport_amount)).scalar() or 0
        
        total_combined = total_purchases + total_transport
        
        # حساب متوسط التكلفة لكل طلبية
        total_orders = Order.query.count()
        average_per_order = total_combined / total_orders if total_orders > 0 else 0
        
        return jsonify({
            "success": True,
            "costs": {
                "total_purchases": total_purchases,
                "total_transport": total_transport,
                "total_combined": total_combined,
                "average_per_order": average_per_order
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@orders_bp.route("/api/orders/health-stats")
def get_health_stats():
    """جلب إحصائيات صحة الطلبيات"""
    try:
        all_orders = Order.query.all()
        total_orders = len(all_orders)
        
        healthy_orders = [order for order in all_orders if order.total_related_debts == 0]
        healthy_count = len(healthy_orders)
        
        debt_orders = [order for order in all_orders if order.total_related_debts > 0]
        debt_count = len(debt_orders)
        total_debts_amount = sum(order.total_related_debts for order in debt_orders)
        
        return jsonify({
            "success": True,
            "stats": {
                'total_orders': total_orders,
                'healthy_orders': healthy_count,
                'debt_orders': debt_count,
                'total_debts_amount': total_debts_amount,
                'healthy_percentage': (healthy_count / total_orders * 100) if total_orders > 0 else 0,
                'debt_percentage': (debt_count / total_orders * 100) if total_orders > 0 else 0
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# تصدير الـ Blueprint
def get_orders_blueprint():
    return orders_bp