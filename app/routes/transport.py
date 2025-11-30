from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from models import Transport, TransportCategory, TransportSubType, TransportReceipt, Order, Debt, db
from sqlalchemy.orm import joinedload
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image

transport_bp = Blueprint('transport', __name__)

@transport_bp.route("/transport")
def transport():
    """صفحة النقل المحسّنة"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    transport_type = request.args.get('type', 'inside')
    category_id = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = Transport.query.options(
        joinedload(Transport.category),
        joinedload(Transport.sub_type),
        joinedload(Transport.receipts)
    )
    
    if transport_type == 'inside':
        query = query.filter(Transport.type == 'inside')
    elif transport_type == 'outside':
        query = query.filter(Transport.type == 'outside')
    
    if category_id and category_id != 'all':
        query = query.filter(Transport.category_id == int(category_id))
    
    if date_from:
        query = query.filter(Transport.transport_date >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        query = query.filter(Transport.transport_date <= datetime.strptime(date_to, "%Y-%m-%d"))
    
    transports = query.order_by(Transport.created_at.desc()).all()
    categories = TransportCategory.query.all()
    sub_types = TransportSubType.query.all()
    
    orders = Order.query.options(joinedload(Order.phones)).order_by(Order.created_at.desc()).all()

    total_amount = sum(transport.transport_amount for transport in transports)
    paid_amount = sum(transport.paid_amount for transport in transports)
    remaining_amount = sum(transport.remaining_amount for transport in transports)
    
    return render_template("transport.html", 
                         transports=transports, 
                         transport_type=transport_type,
                         categories=categories,
                         sub_types=sub_types,
                         orders=orders,
                         category_id=category_id,
                         date_from=date_from,
                         date_to=date_to,
                         total_amount=total_amount,
                         paid_amount=paid_amount,
                         remaining_amount=remaining_amount,
                         now=datetime.now(timezone.utc))

@transport_bp.route("/transport/add", methods=["POST"])
def add_transport():
    """إضافة نقل جديد"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        # معالجة order_id أولاً
        order_id = request.form.get("order_id")
        print(f"🔍 order_id المستلم من النموذج: '{order_id}'")
        
        if order_id and order_id != '' and order_id != 'null':
            order_id = int(order_id)
            # التحقق من وجود الطلبية
            order = Order.query.get(order_id)
            if not order:
                print(f"❌ الطلبية #{order_id} غير موجودة")
                return jsonify({"success": False, "error": "الطلبية غير موجودة"})
            print(f"✅ تم العثور على الطلبية #{order_id}")
        else:
            order_id = None
            print("ℹ️ لم يتم اختيار طلبية")

        # جعل الحقول اختيارية
        category_id = request.form.get("category_id")
        if category_id and category_id != '':
            category_id = int(category_id)
        else:
            category_id = None
            
        sub_type_id = request.form.get("sub_type_id")
        if sub_type_id and sub_type_id != '':
            sub_type_id = int(sub_type_id)
        else:
            sub_type_id = None
        
        transport_amount = float(request.form.get("transport_amount", 0))
        
        # الحصول على حالة الدفع والمبلغ المدفوع مع قيم افتراضية
        payment_status = request.form.get("payment_status", "paid")
        paid_amount = float(request.form.get("paid_amount", 0) or 0)
        
        transport = Transport(
            order_id=order_id,  # ✅ إضافة order_id هنا
            name=request.form.get("name", "نقل شخصي"),
            phone=request.form.get("phone", ""),
            address=request.form.get("address", ""),
            transport_amount=transport_amount,
            destination=request.form.get("destination", "العلمة"),
            paid_amount=paid_amount,
            type=request.form.get("type", "inside"),
            category_id=category_id,
            sub_type_id=sub_type_id,
            transport_method=request.form.get("transport_method", "car"),
            purpose=request.form.get("purpose", ""),
            distance=float(request.form.get("distance", 0)),
            notes=request.form.get("notes", ""),
            is_quick=request.form.get("is_quick") == "true",
            recorded_by=session["user"],
            transport_date=datetime.strptime(request.form.get("transport_date"), "%Y-%m-%d")
        )
        db.session.add(transport)
        db.session.flush()
        
        print(f"✅ تم إنشاء النقل #{transport.id} مرتبط بالطلبية #{order_id}")
        
        # إذا كان النقل غير مدفوع أو مدفوع جزئياً، إنشاء دين تلقائياً
        if payment_status in ['unpaid', 'partial']:
            remaining_amount = transport_amount - paid_amount
            
            debt = Debt(
                name=transport.name,
                phone=transport.phone,
                address=transport.address,
                debt_amount=transport_amount,
                paid_amount=paid_amount,
                start_date=transport.transport_date,
                status="unpaid",
                source_type='transport',
                source_id=transport.id,
                description=f"{transport.purpose} - {transport.destination}",
                recorded_by=session["user"]
            )
            db.session.add(debt)
            print(f"✅ تم إنشاء دين تلقائي للنقل #{transport.id}")
        
        # حفظ الفاتورة إذا كانت موجودة
        if 'receipt' in request.files:
            file = request.files['receipt']
            if file and file.filename != '':
                file_data = file.read()
                if file_data:
                    compressed_data = compress_image(file_data)
                    
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    filename = f"transport_receipt_{transport.id}_{timestamp}.{file_extension}"
                    
                    receipt = TransportReceipt(
                        transport_id=transport.id,
                        filename=filename,
                        original_filename=file.filename,
                        file_size=len(compressed_data),
                        mime_type=file.mimetype,
                        image_data=compressed_data,
                        captured_by=session["user"]
                    )
                    db.session.add(receipt)
        
        db.session.commit()
        print(f"✅ تم إضافة النقل #{transport.id} بحالة دفع: {payment_status}")
        
        return redirect(url_for("transport.transport", type=transport.type))
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في إضافة النقل: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@transport_bp.route("/transport/delete/<int:id>")
def delete_transport(id):
    """حذف نقل"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        transport = Transport.query.get_or_404(id)
        TransportReceipt.query.filter_by(transport_id=id).delete()
        
        db.session.delete(transport)
        db.session.commit()
        
        return redirect(url_for("transport.transport"))
    except Exception as e:
        db.session.rollback()
        return redirect(url_for("transport.transport"))

def compress_image(image_data, max_size=(1200, 1200), quality=85):
    """ضغط الصورة للحفاظ على المساحة"""
    try:
        image = Image.open(BytesIO(image_data))
        
        # تغيير الحجم إذا كان كبيراً
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # حفظ بصيغة مضغوطة
        output = BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"خطأ في ضغط الصورة: {e}")
        return image_data