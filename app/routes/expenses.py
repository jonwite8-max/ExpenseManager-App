from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify, flash
from models import Expense, ExpenseCategory, Supplier, Order, ProductPriceHistory, Debt, ExpenseReceipt, db
from sqlalchemy.orm import joinedload
from datetime import datetime, timezone
import base64
from io import BytesIO
from PIL import Image
import os

expenses_bp = Blueprint('expenses', __name__)

@expenses_bp.route("/expenses")
def expenses():
    """صفحة إدارة المصاريف والمشتريات"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
        
    expense_type = request.args.get('type', 'all')
    category_id = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = Expense.query
    
    if expense_type == 'paid':
        query = query.filter(Expense.payment_status == 'paid')
    elif expense_type == 'unpaid':
        query = query.filter(Expense.payment_status == 'unpaid')
    elif expense_type == 'owner':
        query = query.filter(Expense.purchased_by == 'owner')
    elif expense_type == 'partner':
        query = query.filter(Expense.purchased_by == 'partner')
    elif expense_type == 'worker':
        query = query.filter(Expense.purchased_by == 'worker')
    
    if category_id and category_id != 'all':
        query = query.filter(Expense.category_id == int(category_id))
    
    if date_from:
        query = query.filter(Expense.purchase_date >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        query = query.filter(Expense.purchase_date <= datetime.strptime(date_to, "%Y-%m-%d"))
    
    expenses_list = query.order_by(Expense.created_at.desc()).all()
    categories = ExpenseCategory.query.all()
    suppliers = Supplier.query.all()
    
    orders = Order.query.options(joinedload(Order.phones)).order_by(Order.created_at.desc()).all()

    total_amount = sum(expense.total_amount for expense in expenses_list)
    paid_amount = sum(expense.total_amount for expense in expenses_list if expense.payment_status == 'paid')
    unpaid_amount = sum(expense.total_amount for expense in expenses_list if expense.payment_status == 'unpaid')
    
    return render_template("expenses.html", 
                         expenses=expenses_list,
                         categories=categories,
                         suppliers=suppliers,
                         orders=orders,
                         expense_type=expense_type,
                         category_id=category_id,
                         date_from=date_from,
                         date_to=date_to,
                         total_amount=total_amount,
                         paid_amount=paid_amount,
                         unpaid_amount=unpaid_amount)

@expenses_bp.route("/expenses/add", methods=["POST"])
def add_expense():
    """إضافة مصروف جديد"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        # معالجة order_id بشكل صحيح
        order_id = request.form.get("order_id")
        print(f"🔍 order_id المستلم من النموذج: '{order_id}'")
        
        if order_id and order_id != '' and order_id != 'null':
            order_id = int(order_id)
            # التحقق من وجود الطلبية
            order = Order.query.get(order_id)
            if not order:
                print(f"❌ الطلبية #{order_id} غير موجودة")
                return redirect(url_for('expenses.expenses'))
            print(f"✅ تم العثور على الطلبية #{order_id}")
        else:
            order_id = None
            print("ℹ️ لم يتم اختيار طلبية")
        
        quantity = int(request.form.get("quantity", 1))
        unit_price = float(request.form.get("unit_price", 0))
        total_amount = quantity * unit_price
        
        # جعل supplier_id اختياري
        supplier_id = request.form.get("supplier_id")
        if supplier_id and supplier_id != '':
            supplier_id = int(supplier_id)
        else:
            supplier_id = None
        
        expense = Expense(
            order_id=order_id,  # ✅ حفظ الربط مع الطلبية
            category_id=int(request.form.get("category_id")),
            description=request.form.get("description", ""),
            amount=total_amount,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=total_amount,
            supplier_id=supplier_id,
            purchased_by=request.form.get("purchased_by", "owner"),
            recorded_by=session["user"],
            purchase_date=datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d"),
            payment_status=request.form.get("payment_status", "paid"),
            payment_method=request.form.get("payment_method", "cash"),
            notes=request.form.get("notes", "")
        )
        
        db.session.add(expense)
        db.session.flush()  # للحصول على expense.id قبل الـ commit
        
        print(f"✅ تم إنشاء المصروف #{expense.id} مرتبط بالطلبية #{order_id}")
        
        # حفظ في سجل الأسعار إذا طلب المستخدم ذلك
        if request.form.get("save_to_price_history") == "yes":
            price_history = ProductPriceHistory(
                product_name=request.form.get("description", ""),
                supplier_id=supplier_id,
                price=unit_price,
                purchase_date=datetime.strptime(request.form.get("purchase_date"), "%Y-%m-%d"),
                recorded_by=session["user"]
            )
            db.session.add(price_history)
        
        # إذا كان المصروف غير مدفوع، إنشاء دين تلقائياً
        if expense.payment_status in ['unpaid', 'partial']:
            paid_amount = float(request.form.get("paid_amount", 0) or 0)
            remaining_amount = total_amount - paid_amount
            
            debt = Debt(
                name=expense.supplier.name if expense.supplier else "مورد",
                phone=expense.supplier.phone if expense.supplier else "",
                address=expense.supplier.address if expense.supplier else "",
                debt_amount=total_amount,
                paid_amount=paid_amount,
                start_date=expense.purchase_date,
                status="unpaid",
                source_type='expense',
                source_id=expense.id,
                description=f"{expense.description} - {expense.category.name if expense.category else 'عام'}",
                recorded_by=session["user"]
            )
            db.session.add(debt)
            print(f"✅ تم إنشاء دين تلقائي للمصروف #{expense.id}")

        # حفظ الفاتورة إذا كانت موجودة
        if 'receipt' in request.files:
            file = request.files['receipt']
            if file and file.filename != '':
                # حفظ الفاتورة
                file_data = file.read()
                if file_data:
                    compressed_data = compress_image(file_data)
                    
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
                    filename = f"receipt_{expense.id}_{timestamp}.{file_extension}"
                    
                    receipt = ExpenseReceipt(
                        expense_id=expense.id,
                        filename=filename,
                        original_filename=file.filename,
                        file_size=len(compressed_data),
                        mime_type=file.mimetype,
                        image_data=compressed_data,
                        captured_by=session["user"]
                    )
                    db.session.add(receipt)
        
        db.session.commit()
        print(f"✅ تم إضافة المصروف #{expense.id} بنجاح")
        
        return redirect(url_for('expenses.expenses'))
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في إضافة المصروف: {str(e)}")
        return redirect(url_for('expenses.expenses'))

@expenses_bp.route("/expenses/delete/<int:id>")
def delete_expense(id):
    """حذف مصروف"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        expense = Expense.query.get_or_404(id)
        db.session.delete(expense)
        db.session.commit()
        return redirect(url_for('expenses.expenses'))
    except Exception as e:
        db.session.rollback()
        return redirect(url_for('expenses.expenses'))

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