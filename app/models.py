# ====== models.py ======
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import json

db = SQLAlchemy()

def now_utc():
    return datetime.now(timezone.utc)

# دالة مساعدة للوقت الحالي
def now_utc():
    return datetime.now(timezone.utc)

# ========================
# 🏷️ قسم الحالات والطلبيات
# ========================
# 🔧 إضافة الدوال المفقودة
def create_or_update_order_task(order_id, worker_id, assignment_type, user_name):
    """إنشاء أو تحديث مهمة مرتبطة بالطلبية"""
    try:
        # البحث عن مهمة موجودة
        existing_task = Task.query.filter_by(
            related_entity_type='order',
            related_entity_id=order_id,
            worker_id=worker_id,
            status='pending'
        ).first()
        
        if existing_task:
            # تحديث المهمة الموجودة
            existing_task.updated_at = datetime.now(timezone.utc)
            return existing_task
        else:
            # إنشاء مهمة جديدة
            order = Order.query.get(order_id)
            worker = Worker.query.get(worker_id)
            
            task = Task(
                title=f"طلبية #{order_id} - {assignment_type}",
                description=f"تنفيذ طلبية للعميل {order.name} - المنتج: {order.product}",
                priority='medium',
                task_type='order_execution',
                task_scope='workshop',
                worker_id=worker_id,
                assigned_to=worker.name,
                due_date=datetime.now(timezone.utc).date() + timedelta(days=3),
                related_entity_type='order',
                related_entity_id=order_id,
                related_entity_info=f"العميل: {order.name} - المنتج: {order.product}",
                created_by=user_name
            )
            db.session.add(task)
            return task
    except Exception as e:
        print(f"❌ خطأ في إنشاء مهمة الطلبية: {e}")
        return None

def sync_all_assigned_orders_with_tasks():
    """مزامنة جميع التعيينات مع المهام"""
    try:
        active_assignments = OrderAssignment.query.filter_by(is_active=True).all()
        tasks_created = 0
        
        for assignment in active_assignments:
            # التحقق من عدم وجود مهمة نشطة بالفعل
            existing_task = Task.query.filter_by(
                related_entity_type='order',
                related_entity_id=assignment.order_id,
                worker_id=assignment.worker_id,
                status='pending'
            ).first()
            
            if not existing_task:
                order = Order.query.get(assignment.order_id)
                worker = Worker.query.get(assignment.worker_id)
                
                if order and worker:
                    task = Task(
                        title=f"طلبية #{order.id} - {assignment.assignment_type}",
                        description=f"تنفيذ طلبية للعميل {order.name}",
                        priority='medium',
                        task_type='order_execution',
                        task_scope='workshop',
                        worker_id=worker.id,
                        assigned_to=worker.name,
                        due_date=datetime.now(timezone.utc).date() + timedelta(days=3),
                        related_entity_type='order',
                        related_entity_id=order.id,
                        related_entity_info=f"العميل: {order.name} - المنتج: {order.product}",
                        created_by='system'
                    )
                    db.session.add(task)
                    tasks_created += 1
        
        db.session.commit()
        return tasks_created
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في مزامنة المهام: {e}")
        return 0

def is_admin_user(username):
    """التحقق إذا كان المستخدم مسؤول"""
    user = User.query.filter_by(username=username).first()
    return user and user.role in ['admin', 'manager']
    
class Status(db.Model):
    __tablename__ = 'status'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    color = db.Column(db.String(20), default="#FFC107")
    is_system = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_utc)

    def __repr__(self):
        return f"<Status {self.name}>"

class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    wilaya = db.Column(db.String(50))
    product = db.Column(db.String(200))
    paid = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    note = db.Column(db.Text, default="")
    status_id = db.Column(db.Integer, db.ForeignKey('status.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=now_utc)
    is_paid = db.Column(db.Boolean, default=False)
    
    # الحقول الجديدة للنظام المحسن
    production_details = db.Column(db.Text)
    expected_delivery_date = db.Column(db.Date)
    actual_delivery_date = db.Column(db.Date)
    start_date = db.Column(db.Date, default=lambda: now_utc().date())
    completion_date = db.Column(db.Date)
    is_travel_assignment = db.Column(db.Boolean, default=False)
    media_attachments = db.Column(db.JSON)
    assigned_worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True)
    
    # العلاقات
    status = db.relationship('Status', backref='orders')
    phones = db.relationship('PhoneNumber', backref='order', cascade="all, delete-orphan", lazy=True)
    history = db.relationship('OrderHistory', backref='order', cascade="all, delete-orphan", lazy=True)
    order_assignments = db.relationship('OrderAssignment', backref='order', cascade="all, delete-orphan", lazy=True)
    order_expenses = db.relationship('Expense', backref='order', lazy=True)
    order_transports = db.relationship('Transport', backref='order', lazy=True)
    order_attachments = db.relationship('OrderAttachment', backref='order', cascade="all, delete-orphan", lazy=True)
    assigned_worker = db.relationship('Worker', backref='assigned_orders')
    
    # ========== 🆕 الخصائص الجديدة للديون المرتبطة ==========
    @property
    def total_expense_debts(self):
        """إجمالي ديون المصاريف المرتبطة بالطلبية"""
        try:
            expense_debts = db.session.query(Debt)\
                .join(Expense, Debt.source_id == Expense.id)\
                .filter(
                    Expense.order_id == self.id,
                    Debt.status == 'unpaid',
                    Debt.source_type == 'expense'
                ).all()
            return sum(debt.remaining_amount for debt in expense_debts)
        except Exception as e:
            print(f"❌ خطأ في حساب ديون مصاريف الطلبية {self.id}: {e}")
            return 0.0

    @property
    def total_transport_debts(self):
        """إجمالي ديون النقل المرتبطة بالطلبية"""
        try:
            transport_debts = db.session.query(Debt)\
                .join(Transport, Debt.source_id == Transport.id)\
                .filter(
                    Transport.order_id == self.id,
                    Debt.status == 'unpaid',
                    Debt.source_type == 'transport'
                ).all()
            return sum(debt.remaining_amount for debt in transport_debts)
        except Exception as e:
            print(f"❌ خطأ في حساب ديون نقل الطلبية {self.id}: {e}")
            return 0.0

    @property
    def total_related_debts(self):
        """إجمالي الديون المرتبطة بالطلبية (مصاريف + نقل)"""
        return self.total_expense_debts + self.total_transport_debts

    @property
    def financial_health(self):
        """الصحة المالية للطلبية بناءً على الديون المرتبطة"""
        if self.total_related_debts == 0:
            return "سليمة"
        else:
            return "بها ديون"

    @property
    def has_related_debts(self):
        """هل للطلبية ديون مرتبطة؟"""
        return self.total_related_debts > 0

    @property
    def remaining(self):
        return round((self.total or 0.0) - (self.paid or 0.0), 2)

    @property
    def total_expenses(self):
        """إجمالي المصاريف المرتبطة بالطلبية - الإصلاح النهائي"""
        try:
            # الاستعلام المباشر من قاعدة البيانات
            from models import Expense
            expenses = Expense.query.filter_by(order_id=self.id).all()
            return sum(expense.total_amount for expense in expenses)
        except Exception as e:
            print(f"❌ خطأ في حساب مصاريف الطلبية {self.id}: {e}")
            return 0.0

    @property
    def total_transports(self):
        """إجمالي تكاليف النقل المرتبطة بالطلبية - الإصلاح النهائي"""
        try:
            # الاستعلام المباشر من قاعدة البيانات
            from models import Transport
            transports = Transport.query.filter_by(order_id=self.id).all()
            return sum(transport.transport_amount for transport in transports)
        except Exception as e:
            print(f"❌ خطأ في حساب نقل الطلبية {self.id}: {e}")
            return 0.0

    @property
    def total_costs(self):
        """إجمالي التكاليف - الإصلاح النهائي"""
        try:
            return self.total_expenses + self.total_transports
        except:
            return 0.0

    @property
    def profit(self):
        """ربح الطلبية - الإصلاح النهائي"""
        try:
            return float(self.total or 0) - float(self.total_costs or 0)
        except:
            return 0.0

    @property
    def profit_percentage(self):
        """نسبة الربح - الإصلاح النهائي"""
        try:
            if float(self.total or 0) == 0:
                return 0
            return (self.profit / float(self.total)) * 100
        except:
            return 0.0

    @property
    def is_profitable(self):
        """هل الطلبية مربحة؟"""
        return self.profit >= 0

    @property
    def assigned_workers(self):
        """العمال المعينين حالياً على الطلبية"""
        return [assignment.worker for assignment in self.order_assignments if assignment.is_active]

    @property
    def progress_status(self):
        """حالة تقدم الطلبية"""
        if self.completion_date:
            return "مكتملة"
        elif self.actual_delivery_date:
            return "تم التسليم"
        elif self.expected_delivery_date and self.expected_delivery_date < now_utc().date():
            return "متأخرة"
        elif self.order_assignments:
            return "قيد التنفيذ"
        else:
            return "في الانتظار"

class PhoneNumber(db.Model):
    __tablename__ = 'phone_number'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    number = db.Column(db.String(40), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)

class OrderHistory(db.Model):
    __tablename__ = 'order_history'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    change_type = db.Column(db.String(120))
    details = db.Column(db.Text)  # ✅ التفاصيل فقط (بدون اسم المستخدم)
    timestamp = db.Column(db.DateTime, default=now_utc)
    user = db.Column(db.String(50))  # ✅ اسم المستخدم في حقل منفصل - تأكد من وجوده

# ========================
# 👥 قسم العمال والتعيينات
# ========================

class OrderAssignment(db.Model):
    __tablename__ = 'order_assignment'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    assignment_type = db.Column(db.String(20), default='workshop')
    assigned_date = db.Column(db.DateTime, default=now_utc)
    completed_date = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    assigned_by = db.Column(db.String(50))
    
    # العلاقات
    worker = db.relationship('Worker', backref='worker_assignments')

class WorkerHistory(db.Model):
    __tablename__ = 'worker_history'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    change_type = db.Column(db.String(120))
    details = db.Column(db.Text)
    amount = db.Column(db.Float, default=0.0)
    timestamp = db.Column(db.DateTime, default=now_utc)
    user = db.Column(db.String(50))
    
    worker = db.relationship('Worker', backref='worker_histories')

class Worker(db.Model):
    __tablename__ = 'worker'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    address = db.Column(db.String(200))
    id_card = db.Column(db.String(50), unique=False, nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    monthly_salary = db.Column(db.Float, default=0.0)
    absences = db.Column(db.Float, default=0.0)
    outside_work_days = db.Column(db.Integer, default=0)
    outside_work_bonus = db.Column(db.Float, default=0.0)
    advances = db.Column(db.Float, default=0.0)
    incentives = db.Column(db.Float, default=0.0)
    late_hours = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=now_utc)

    username = db.Column(db.String(80), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=True)
    is_login_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)

    # تخزين كلمة المرور الأصلية
    original_password = db.Column(db.String(200), nullable=True)

    def set_password(self, password):
        """تحديث كلمة المرور مع تخزين النسخة الأصلية"""
        self.password_hash = generate_password_hash(password)

        import base64
        self.original_password = base64.b64encode(password.encode()).decode()

    def get_original_password(self):
        """استرجاع كلمة المرور الأصلية (للعرض فقط)"""
        if self.original_password:
            import base64
            try:
                return base64.b64decode(self.original_password.encode()).decode()
            except:
                return "غير متاحة"
        return "غير متاحة"

    def check_password(self, password):
        """التحقق من كلمة المرور"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.set_password(password)

    @property
    def total_salary(self):
        """حساب الراتب الإجمالي المستحق بدقة"""
        try:
            today = now_utc().date()
            days_since_start = (today - self.start_date).days
            days_worked = max(0, days_since_start)
            
            daily_salary = self.monthly_salary / 30.0
            base_salary = days_worked * daily_salary
            
            absence_deduction = self.absences * daily_salary
            late_deduction = (self.late_hours or 0) * 500
            
            total = (base_salary + 
                    self.outside_work_bonus + 
                    self.incentives - 
                    self.advances - 
                    absence_deduction - 
                    late_deduction)
            
            return max(0, round(total, 2))
        except:
            return 0.0

    @property
    def assigned_orders(self):
        """الطلبيات المعينة للعامل حالياً"""
        return [
            assignment.order
            for assignment in self.worker_assignments
            if assignment.is_active
        ]

    def __repr__(self):
        return f"<Worker {self.name}>"


def get_orders_health_stats():
    """جلب إحصائيات صحة الطلبيات بدون تكرار"""
    try:
        all_orders = Order.query.all()
        total_orders = len(all_orders)

        healthy_orders = [order for order in all_orders if order.total_related_debts == 0]
        healthy_count = len(healthy_orders)

        debt_orders = [order for order in all_orders if order.total_related_debts > 0]
        debt_count = len(debt_orders)

        total_debts_amount = sum(order.total_related_debts for order in debt_orders)

        return {
            'total_orders': total_orders,
            'healthy_orders': healthy_count,
            'debt_orders': debt_count,
            'total_debts_amount': total_debts_amount,
            'healthy_percentage': (healthy_count / total_orders * 100) if total_orders > 0 else 0,
            'debt_percentage': (debt_count / total_orders * 100) if total_orders > 0 else 0
        }

    except Exception as e:
        print(f"❌ خطأ في حساب إحصائيات الصحة: {e}")

        return {
            'total_orders': 0,
            'healthy_orders': 0,
            'debt_orders': 0,
            'total_debts_amount': 0,
            'healthy_percentage': 0,
            'debt_percentage': 0
        }


class WorkerAttendance(db.Model):
    __tablename__ = 'worker_attendance'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    date = db.Column(db.Date, default=lambda: now_utc().date())
    check_in_morning = db.Column(db.DateTime)
    check_out_morning = db.Column(db.DateTime)
    check_in_afternoon = db.Column(db.DateTime)
    check_out_afternoon = db.Column(db.DateTime)
    total_hours = db.Column(db.Float, default=0.0)
    absence_hours = db.Column(db.Float, default=0.0)
    location_verified = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_utc)
    
    worker = db.relationship('Worker', backref='worker_attendances')



    
# ========================
# 💰 قسم المصاريف والمشتريات
# ========================

class ExpenseCategory(db.Model):
    __tablename__ = 'expense_category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default='#3B82F6')
    icon = db.Column(db.String(50), default='📦')
    created_at = db.Column(db.DateTime, default=now_utc)

class Expense(db.Model):
    __tablename__ = 'expense'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_category.id'))
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)  # ربط المصروف بالطلبية
    purchased_by = db.Column(db.String(50), default='owner')
    recorded_by = db.Column(db.String(50), nullable=False)
    purchase_date = db.Column(db.Date, default=lambda: now_utc().date())
    payment_status = db.Column(db.String(20), default='paid')
    payment_method = db.Column(db.String(20), default='cash')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now_utc)

    paid_amount = db.Column(db.Float, default=0.0)
    
    # العلاقات
    category = db.relationship('ExpenseCategory', backref='category_expenses')
    supplier = db.relationship('Supplier', backref='supplier_expenses')

    receipts = db.relationship('ExpenseReceipt', backref='expenses', cascade="all, delete-orphan", lazy=True)

    @property
    def calculated_total(self):
        return self.quantity * self.unit_price

    @property
    def remaining_amount(self):
        """المبلغ المتبقي للدفع"""
        return self.total_amount - self.paid_amount

    @property
    def calculated_total(self):
        return self.quantity * self.unit_price

class ProductPriceHistory(db.Model):
    __tablename__ = 'product_price_history'
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    price = db.Column(db.Float, default=0.0)
    purchase_date = db.Column(db.Date, default=lambda: now_utc().date())
    recorded_by = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)
    
    supplier = db.relationship('Supplier', backref='supplier_price_history')


# ========================
# 🏢 قسم الموردين
# ========================

class Supplier(db.Model):
    __tablename__ = 'supplier'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(40))
    address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=now_utc)

# ========================
# 📦 قسم المنتجات
# ========================

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_category.id'))
    created_at = db.Column(db.DateTime, default=now_utc)
    
    category = db.relationship('ExpenseCategory', backref='category_products')

# ========================
# 🛒 قسم المشتريات القديم (للتوافق)
# ========================

class Purchase(db.Model):
    __tablename__ = 'purchase'
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    price = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=1)
    total_price = db.Column(db.Float, default=0.0)
    purchase_date = db.Column(db.Date, default=lambda: now_utc().date())
    status = db.Column(db.String(20), default="unpaid")
    type = db.Column(db.String(20), default="fixed")
    created_at = db.Column(db.DateTime, default=now_utc)

    supplier = db.relationship('Supplier', backref='supplier_purchases')
    product = db.relationship('Product', backref='product_purchases')

# ========================
# 🚚 قسم النقل المحسّن
# ========================

class TransportCategory(db.Model):
    __tablename__ = 'transport_category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default='#3B82F6')
    icon = db.Column(db.String(50), default='🚗')
    created_at = db.Column(db.DateTime, default=now_utc)

class TransportSubType(db.Model):
    __tablename__ = 'transport_sub_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('transport_category.id'))
    created_at = db.Column(db.DateTime, default=now_utc)
    
    category = db.relationship('TransportCategory', backref='category_sub_types')

class TransportReceipt(db.Model):
    __tablename__ = 'transport_receipt'
    id = db.Column(db.Integer, primary_key=True)
    transport_id = db.Column(db.Integer, db.ForeignKey('transport.id'))
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    image_data = db.Column(db.LargeBinary)
    captured_at = db.Column(db.DateTime, default=now_utc)
    captured_by = db.Column(db.String(50), nullable=False)
    


class Transport(db.Model):
    __tablename__ = 'transport'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(40))
    address = db.Column(db.String(200))
    transport_amount = db.Column(db.Float, default=0.0)
    destination = db.Column(db.String(200))
    paid_amount = db.Column(db.Float, default=0.0)
    type = db.Column(db.String(20), default="inside")
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))  # ربط النقل بالطلبية
    
    # الحقول الجديدة للنظام المحسّن
    category_id = db.Column(db.Integer, db.ForeignKey('transport_category.id'))
    sub_type_id = db.Column(db.Integer, db.ForeignKey('transport_sub_type.id'))
    transport_method = db.Column(db.String(50), default='car')
    purpose = db.Column(db.String(200))
    distance = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    is_quick = db.Column(db.Boolean, default=False)
    recorded_by = db.Column(db.String(50), nullable=False)
    transport_date = db.Column(db.Date, default=lambda: now_utc().date())
    created_at = db.Column(db.DateTime, default=now_utc)

    category = db.relationship('TransportCategory', backref='category_transports')
    sub_type = db.relationship('TransportSubType', backref='sub_type_transports')

    receipts = db.relationship('TransportReceipt', backref='transport', cascade="all, delete-orphan", lazy=True)

    @property
    def remaining_amount(self):
        return round(self.transport_amount - self.paid_amount, 2)

# ========================
# 💸 قسم الديون المحسّن
# ========================

class Debt(db.Model):
    __tablename__ = 'debt'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(40))
    address = db.Column(db.String(200))
    debt_amount = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.Date, default=lambda: now_utc().date())
    payment_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="unpaid")
    created_at = db.Column(db.DateTime, default=now_utc)
    
    # الحقول الجديدة للنظام الذكي
    source_type = db.Column(db.String(50))
    source_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    recorded_by = db.Column(db.String(50))

    @property
    def remaining_amount(self):
        return round(self.debt_amount - self.paid_amount, 2)
    
    @property
    def source_info(self):
        """معلومات المصدر للعرض في الواجهة"""
        if self.source_type == 'expense':
            return f"مصروف - {self.description}"
        elif self.source_type == 'purchase':
            return f"مشتريات - {self.description}"
        elif self.source_type == 'transport':
            return f"نقل - {self.description}"
        else:
            return f"دين يدوي - {self.description}"

# ========================
# 👤 قسم المستخدمين
# ========================

class User(db.Model):
    __tablename__ = 'app_user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(200), nullable=False)  # تغيير الاسم
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20), default='user')
    permissions = db.Column(db.JSON, default=list)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=now_utc)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        self.set_password(password)

# ========================
# 👤 نظام تتبع المستخدمين المحسن
# ========================

def record_activity(user_name, entity_type, entity_id, action, details, amount=0.0):
    """تسجيل نشاط المستخدم في النظام - محدث"""
    try:
        if entity_type == 'order':
            history = OrderHistory(
                order_id=entity_id,
                change_type=action,
                details=details,
                user=user_name
            )
            db.session.add(history)
        
        elif entity_type == 'expense':
            expense = Expense.query.get(entity_id)
            if expense and expense.order_id:
                history = OrderHistory(
                    order_id=expense.order_id,
                    change_type="مصروف",
                    details=f"{details} - المبلغ: {amount} دج",
                    user=user_name
                )
                db.session.add(history)
        
        elif entity_type == 'transport':
            transport = Transport.query.get(entity_id)
            if transport and transport.order_id:
                history = OrderHistory(
                    order_id=transport.order_id,
                    change_type="نقل",
                    details=f"{details} - المبلغ: {amount} دج",
                    user=user_name
                )
                db.session.add(history)
        
        elif entity_type == 'worker':
            history = WorkerHistory(
                worker_id=entity_id,
                change_type=action,
                details=details,
                amount=amount,
                user=user_name
            )
            db.session.add(history)
        
        db.session.commit()
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في تسجيل النشاط: {e}")
        return False

# ========================
# ⚙️ قسم الإعدادات
# ========================

class SystemSettings(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), default='SOFAZI')
    logo = db.Column(db.String(200))
    currency = db.Column(db.String(10), default='DZD')
    language = db.Column(db.String(10), default='ar')
    theme = db.Column(db.String(20), default='light')
    primary_color = db.Column(db.String(7), default='#3B82F6')
    rows_per_page = db.Column(db.Integer, default=25)
    compact_mode = db.Column(db.Boolean, default=False)
    two_factor = db.Column(db.Boolean, default=False)
    activity_logging = db.Column(db.Boolean, default=True)
    session_timeout = db.Column(db.Integer, default=30)
    password_strength = db.Column(db.String(20), default='medium')
    email_notifications = db.Column(db.Boolean, default=True)
    payment_notifications = db.Column(db.Boolean, default=True)
    inventory_notifications = db.Column(db.Boolean, default=True)
    notification_time = db.Column(db.String(20), default='instant')
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

# ========================
# 📸 قسم فواتير المصاريف
# ========================

class ExpenseReceipt(db.Model):
    __tablename__ = 'expense_receipt'
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expense.id'))
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500))
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    image_data = db.Column(db.LargeBinary)
    captured_at = db.Column(db.DateTime, default=now_utc)
    captured_by = db.Column(db.String(50), nullable=False)
    
    expense = db.relationship('Expense', backref='expense_receipts')

# ========================
# 📎 قسم مرفقات الطلبيات
# ========================

class OrderAttachment(db.Model):
    __tablename__ = 'order_attachment'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    file_data = db.Column(db.LargeBinary)
    file_type = db.Column(db.String(20))
    description = db.Column(db.String(200))
    captured_at = db.Column(db.DateTime, default=now_utc)
    captured_by = db.Column(db.String(50), nullable=False)

# ========================
# 📎 ATTACHMENT NOTES MODEL
# ========================

class AttachmentNotes(db.Model):
    __tablename__ = 'attachment_notes'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    notes_content = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)
    
    order = db.relationship('Order', backref='attachment_notes')



# ========================
#  نظام حساب المساحة المستخدمة 
# ========================
class StorageManager:
    @staticmethod
    def get_total_used_space():
        """حساب إجمالي المساحة المستخدمة"""
        total_size = db.session.query(db.func.sum(OrderAttachment.file_size)).scalar()
        return total_size or 0
    
    @staticmethod
    def get_order_attachments_size(order_id):
        """حساب مساحة مرفقات طلبية محددة"""
        order_size = db.session.query(db.func.sum(OrderAttachment.file_size))\
            .filter(OrderAttachment.order_id == order_id).scalar()
        return order_size or 0
    
    @staticmethod
    def get_storage_limits():
        """الحصول على حدود التخزين"""
        return {
            'max_total_size': 500 * 1024 * 1024,  # 500 MB
            'max_per_order': 50 * 1024 * 1024,    # 50 MB لكل طلبية
            'max_per_file': 10 * 1024 * 1024,     # 10 MB لكل ملف
            'warning_threshold': 0.8  # تنبيه عند 80%
        }
# ========================
# 🔔 نظام الإشعارات المحسن
# ========================

class Notification(db.Model):
    __tablename__ = 'notification'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50))
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    type = db.Column(db.String(20))
    is_read = db.Column(db.Boolean, default=False)
    related_entity_type = db.Column(db.String(50))
    related_entity_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=now_utc)

# ========================
# 📊 نظام الإحصائيات المتقدم
# ========================

class FinancialSummary(db.Model):
    __tablename__ = 'financial_summary'
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(20))
    period_date = db.Column(db.Date)
    total_orders = db.Column(db.Float, default=0.0)
    total_paid = db.Column(db.Float, default=0.0)
    total_remaining = db.Column(db.Float, default=0.0)
    total_expenses = db.Column(db.Float, default=0.0)
    total_transports = db.Column(db.Float, default=0.0)
    total_profits = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=now_utc)

# ========================
# 🎯 دوال مساعدة للنظام
# ========================
# إضافة دالة لتهيئة النظام
def initialize_system():
    """تهيئة النظام بالبيانات الأساسية"""
    try:
        # إنشاء الحالات النظامية
        create_system_statuses()
        
        # إنشاء التصنيفات الأساسية
        create_default_categories()
        
        # إنشاء إعدادات النظام
        if not SystemSettings.query.first():
            settings = SystemSettings()
            db.session.add(settings)
            db.session.commit()
            
        print("✅ تم تهيئة النظام بنجاح")
        return True
        
    except Exception as e:
        print(f"❌ خطأ في تهيئة النظام: {e}")
        return False
    
def create_default_categories():
    """إنشاء التصنيفات الافتراضية"""
    default_categories = [
        ('مواد أولية', '#3B82F6', '📦'),
        ('أدوات عمل', '#10B981', '🛠️'),
        ('نقل ومواصلات', '#F59E0B', '🚚'),
        ('مرتبات عمال', '#EF4444', '👷'),
        ('مصاريف إدارية', '#8B5CF6', '📊'),
        ('صيانة', '#06B6D4', '🔧'),
        ('كهرباء وماء', '#84CC16', '💡'),
        ('إيجار', '#F97316', '🏢')
    ]
    
    for name, color, icon in default_categories:
        if not ExpenseCategory.query.filter_by(name=name).first():
            category = ExpenseCategory(name=name, color=color, icon=icon)
            db.session.add(category)
    
    db.session.commit()

# ========================
# 📊 نظام السجلات الشهرية وتقييم العمال
# ========================

class WorkerMonthlyRecord(db.Model):
    __tablename__ = 'worker_monthly_record'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    total_salary = db.Column(db.Float, default=0.0)  # إجمالي المستحق
    paid_amount = db.Column(db.Float, default=0.0)   # المبلغ المدفوع فعلياً
    advances = db.Column(db.Float, default=0.0)      # التسبيقات
    absences = db.Column(db.Float, default=0.0)      # أيام الغياب
    late_hours = db.Column(db.Float, default=0.0)    # ساعات التأخر
    outside_work_days = db.Column(db.Integer, default=0)  # أيام العمل الخارجي
    outside_work_bonus = db.Column(db.Float, default=0.0) # مكافأة العمل الخارجي
    incentives = db.Column(db.Float, default=0.0)    # التحفيزات
    penalties = db.Column(db.Float, default=0.0)     # الغرامات
    notes = db.Column(db.Text)
    recorded_by = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=now_utc)
    
    worker = db.relationship('Worker', backref='monthly_records')

class WorkerEvaluation(db.Model):
    __tablename__ = 'worker_evaluation'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'))
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    evaluation_date = db.Column(db.Date, default=lambda: now_utc().date())
    
    # معايير التقييم (من 1-10)
    quality_score = db.Column(db.Integer, default=10)        # جودة العمل
    timing_score = db.Column(db.Integer, default=10)        # الالتزام بالوقت
    accuracy_score = db.Column(db.Integer, default=10)      # الدقة
    efficiency_score = db.Column(db.Integer, default=10)    # الكفاءة
    
    # النتائج
    total_score = db.Column(db.Integer, default=40)         # المجموع
    bonus_amount = db.Column(db.Float, default=0.0)         # مبلغ التحفيز
    penalty_amount = db.Column(db.Float, default=0.0)       # مبلغ الغرامة
    notes = db.Column(db.Text)
    evaluated_by = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=now_utc)
    
    worker = db.relationship('Worker', backref='evaluations')
    order = db.relationship('Order', backref='worker_evaluations')

class EvaluationCriteria(db.Model):
    __tablename__ = 'evaluation_criteria'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    max_score = db.Column(db.Integer, default=10)
    weight = db.Column(db.Float, default=1.0)  # وزن المعيار
    bonus_per_point = db.Column(db.Float, default=100.0)  # مكافأة لكل نقطة
    penalty_per_point = db.Column(db.Float, default=50.0) # غرامة لكل نقطة ناقصة
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=now_utc)

def create_monthly_record(worker_id, user_name):
    """إنشاء سجل شهري للعامل"""
    today = now_utc()
    worker = Worker.query.get(worker_id)
    
    if worker:
        # التحقق من وجود سجل لهذا الشهر
        existing_record = WorkerMonthlyRecord.query.filter_by(
            worker_id=worker_id,
            year=today.year,
            month=today.month
        ).first()
        
        if not existing_record:
            record = WorkerMonthlyRecord(
                worker_id=worker_id,
                year=today.year,
                month=today.month,
                total_salary=worker.total_salary,
                advances=worker.advances,
                absences=worker.absences,
                late_hours=worker.late_hours or 0,
                outside_work_days=worker.outside_work_days,
                outside_work_bonus=worker.outside_work_bonus,
                incentives=worker.incentives,
                recorded_by=user_name
            )
            db.session.add(record)
            db.session.commit()
            return record
    return None

def evaluate_worker_performance(worker_id, order_id, scores, user_name, notes=""):
    """تقييم أداء العامل على طلبية"""
    evaluation = WorkerEvaluation(
        worker_id=worker_id,
        order_id=order_id,
        quality_score=scores.get('quality', 10),
        timing_score=scores.get('timing', 10),
        accuracy_score=scores.get('accuracy', 10),
        efficiency_score=scores.get('efficiency', 10),
        evaluated_by=user_name,
        notes=notes
    )
    
    # حساب النقاط والتحفيز/الغرامة
    total_score = sum([
        scores.get('quality', 10),
        scores.get('timing', 10),
        scores.get('accuracy', 10),
        scores.get('efficiency', 10)
    ])
    
    evaluation.total_score = total_score
    
    # حساب المكافآت والغرامات
    max_possible_score = 40
    if total_score >= 38:  # ممتاز
        evaluation.bonus_amount = 500.0
    elif total_score >= 35:  # جيد جداً
        evaluation.bonus_amount = 300.0
    elif total_score >= 32:  # جيد
        evaluation.bonus_amount = 150.0
    elif total_score <= 25:  # ضعيف
        evaluation.penalty_amount = 200.0
    elif total_score <= 28:  # مقبول
        evaluation.penalty_amount = 100.0
    
    db.session.add(evaluation)
    
    # تحديث تحفيزات العامل إذا كان هناك مكافأة
    if evaluation.bonus_amount > 0:
        worker = Worker.query.get(worker_id)
        worker.incentives += evaluation.bonus_amount
        
        # تسجيل في السجل
        history = WorkerHistory(
            worker_id=worker_id,
            change_type="تحفيز",
            details=f"مكافأة تقييم أداء على الطلبية #{order_id}. النقاط: {total_score}/40",
            amount=evaluation.bonus_amount,
            user=user_name
        )
        db.session.add(history)
    
    # تطبيق الغرامة إذا كانت موجودة
    if evaluation.penalty_amount > 0:
        worker = Worker.query.get(worker_id)
        
        # تسجيل في السجل
        history = WorkerHistory(
            worker_id=worker_id,
            change_type="غرامة",
            details=f"غرامة تقييم أداء على الطلبية #{order_id}. النقاط: {total_score}/40",
            amount=-evaluation.penalty_amount,
            user=user_name
        )
        db.session.add(history)
    
    db.session.commit()
    return evaluation

def get_monthly_workers_cost(year, month):
    """حساب تكلفة العمال لشهر معين"""
    records = WorkerMonthlyRecord.query.filter_by(year=year, month=month).all()
    
    total_cost = {
        'total_salaries': sum(record.total_salary for record in records),
        'total_paid': sum(record.paid_amount for record in records),
        'total_bonuses': sum(record.incentives + record.outside_work_bonus for record in records),
        'total_penalties': sum(record.penalties for record in records),
        'workers_count': len(records)
    }
    
    return total_cost

def get_worker_monthly_history(worker_id):
    """الحصول على السجل الشهري للعامل"""
    return WorkerMonthlyRecord.query.filter_by(worker_id=worker_id).order_by(
        WorkerMonthlyRecord.year.desc(), 
        WorkerMonthlyRecord.month.desc()
    ).all()

def create_system_statuses():
    """إنشاء الحالات النظامية الأساسية"""
    system_statuses = [
        ('في الانتظار', '#FFC107', True),
        ('قيد التنفيذ', '#3B82F6', True),
        ('معينة للعامل', '#8B5CF6', True),
        ('قيد التركيب', '#F59E0B', True),
        ('مكتملة التركيب', '#10B981', True),
        ('تم التسليم', '#059669', True),
        ('ملغاة', '#EF4444', True)
    ]
    
    for name, color, is_system in system_statuses:
        if not Status.query.filter_by(name=name).first():
            status = Status(name=name, color=color, is_system=is_system)
            db.session.add(status)
    
    db.session.commit()

def update_order_status(order_id, new_status_name, user_name):
    """تحديث حالة الطلبية مع التسجيل في السجل"""
    status = Status.query.filter_by(name=new_status_name).first()
    if status:
        order = Order.query.get(order_id)
        if order:
            old_status = order.status.name if order.status else "بدون حالة"
            order.status_id = status.id
            
            # تسجيل في السجل
            history = OrderHistory(
                order_id=order_id,
                change_type="تغيير الحالة",
                details=f"تم تغيير حالة الطلبية من {old_status} إلى {new_status_name}",
                user=user_name
            )
            db.session.add(history)
            db.session.commit()
            return True
    return False

def assign_worker_to_order(order_id, worker_id, assignment_type, user_name, notes=""):
    """تعيين عامل للطلبية"""
    # إلغاء أي تعيينات سابقة نشطة لنفس العامل على نفس الطلبية
    existing_assignment = OrderAssignment.query.filter_by(
        order_id=order_id, 
        worker_id=worker_id, 
        is_active=True
    ).first()
    
    if existing_assignment:
        existing_assignment.is_active = False
        existing_assignment.completed_date = now_utc()
    
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
        update_order_status(order_id, 'معينة للعامل', user_name)
    
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

def create_suspension_request(task_id, product_name, quantity, issue_description, user_name):
    """إنشاء طلب تعليق للمهمة"""
    task = Task.query.get(task_id)
    if task:
        # إنشاء مهمة تعليق
        suspension_task = Task(
            title=f"طلب تعليق - {product_name}",
            description=f"المنتج الناقص: {product_name}\nالكمية: {quantity}\nالمشكلة: {issue_description}",
            priority='high',
            task_type='suspension_request',
            assigned_to='الإدارة',
            related_entity_type='task',
            related_entity_id=task_id,
            created_by=user_name,
            task_scope='management'
        )
        db.session.add(suspension_task)
        
        # تعليق المهمة الأصلية
        task.status = 'suspended'
        task.notes = f"معلقة - منتج ناقص: {product_name}"
        
        db.session.commit()
        return suspension_task
    return None

def resume_suspended_task(task_id, user_name):
    """استئناف مهمة معلقة"""
    task = Task.query.get(task_id)
    if task and task.status == 'suspended':
        task.status = 'in_progress'
        task.notes = "تم استئناف العمل"
        
        # تسجيل في السجل
        history = OrderHistory(
            order_id=task.related_entity_id,
            change_type="استئناف العمل",
            details=f"تم استئناف العمل على الطلبية بعد توفير المنتج",
            user=user_name
        )
        db.session.add(history)
        
        db.session.commit()
        return True
    return False

def auto_detect_product_availability(order_id, product_name):
    """الكشف التلقائي عن توفر المنتج"""
    # البحث في المصاريف الحديثة عن نفس المنتج
    recent_expenses = Expense.query.filter(
        Expense.description.ilike(f"%{product_name}%"),
        Expense.created_at >= datetime.now(timezone.utc) - timedelta(days=1)
    ).all()
    
    if recent_expenses:
        return recent_expenses[0]  # أول مصروف مطابق
    return None

def create_order_task_for_worker(order_id, worker_id, user_name):
    """إنشاء مهمة طلبية للعامل"""
    try:
        order = Order.query.get(order_id)
        worker = Worker.query.get(worker_id)
        
        if order and worker:
            # التحقق من عدم وجود مهمة نشطة مسبقاً
            existing_task = Task.query.filter(
                Task.worker_id == worker_id,
                Task.related_entity_type == 'order',
                Task.related_entity_id == order_id,
                Task.status.in_(['pending', 'in_progress'])
            ).first()
            
            if existing_task:
                print(f"⚠️ توجد مهمة نشطة مسبقاً للعامل {worker.name} على الطلبية {order.id}")
                return existing_task  # إرجاع المهمة الموجودة
            
            # إنشاء مهمة جديدة
            task = Task(
                title=f"إنجاز طلبية - {order.name}",
                description=f"المنتج: {order.product}\nالعميل: {order.name}\nالولاية: {order.wilaya}\nالقيمة: {order.total} دج",
                priority='medium',
                status='pending',
                task_type='order_completion',
                assigned_to=worker.name,
                worker_id=worker_id,
                related_entity_type='order',
                related_entity_id=order_id,
                due_date=datetime.now(timezone.utc).date() + timedelta(days=7),
                created_by=user_name,
                task_scope='worker'
            )
            db.session.add(task)
            db.session.commit()
            
            print(f"✅ تم إنشاء مهمة #{task.id} للعامل {worker.name} للطلبية {order.id}")
            return task
        else:
            print(f"❌ لم يتم العثور على الطلبية #{order_id} أو العامل #{worker_id}")
            return None
            
    except Exception as e:
        print(f"❌ خطأ في إنشاء مهمة للعامل: {e}")
        db.session.rollback()
        return None

def create_tasks_for_existing_assignments(user_name="النظام"):
    """إنشاء مهام للطلبيات القديمة المعينة"""
    try:
        tasks_created = 0
        
        # جلب جميع التعيينات النشطة التي ليس لها مهام مرتبطة
        active_assignments = OrderAssignment.query.filter_by(is_active=True).all()
        
        for assignment in active_assignments:
            # التحقق من عدم وجود مهمة نشطة مسبقاً
            existing_task = Task.query.filter(
                Task.worker_id == assignment.worker_id,
                Task.related_entity_type == 'order',
                Task.related_entity_id == assignment.order_id,
                Task.status.in_(['pending', 'in_progress'])
            ).first()
            
            if not existing_task:
                order = assignment.order
                worker = assignment.worker
                
                # إنشاء مهمة جديدة
                task = Task(
                    title=f"إنجاز طلبية - {order.name}",
                    description=f"المنتج: {order.product}\nالعميل: {order.name}\nالولاية: {order.wilaya}\nالقيمة: {order.total} دج",
                    priority='medium',
                    status='pending',
                    task_type='order_completion',
                    assigned_to=worker.name,
                    worker_id=worker.id,
                    related_entity_type='order',
                    related_entity_id=order.id,
                    due_date=datetime.now(timezone.utc).date() + timedelta(days=7),
                    created_by=user_name,
                    task_scope='worker'
                )
                db.session.add(task)
                tasks_created += 1
                print(f"✅ تم إنشاء مهمة للطلبية القديمة #{order.id} للعامل {worker.name}")
        
        if tasks_created > 0:
            db.session.commit()
            print(f"🎉 تم إنشاء {tasks_created} مهمة للطلبيات القديمة")
        else:
            print("ℹ️ لا توجد طلبيات قديمة تحتاج إلى مهام")
        
        return tasks_created
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في إنشاء مهام للطلبيات القديمة: {e}")
        return 0
    
def create_suspension_request(task_id, product_name, quantity, issue_description, user_name):
    """إنشاء طلب تعليق للمهمة"""
    task = Task.query.get(task_id)
    if task:
        # إنشاء مهمة تعليق
        suspension_task = Task(
            title=f"طلب تعليق - {product_name}",
            description=f"المنتج الناقص: {product_name}\nالكمية: {quantity}\nالمشكلة: {issue_description}",
            priority='high',
            task_type='suspension_request',
            assigned_to='الإدارة',
            related_entity_type='task',
            related_entity_id=task_id,
            created_by=user_name,
            task_scope='management'
        )
        db.session.add(suspension_task)
        
        # تعليق المهمة الأصلية
        task.status = 'suspended'
        task.notes = f"معلقة - منتج ناقص: {product_name}"
        
        db.session.commit()
        return suspension_task
    return None

def deactivate_assignment(assignment_id, user_name):
    """إلغاء تعيين عامل"""
    assignment = OrderAssignment.query.get(assignment_id)
    if assignment and assignment.is_active:
        assignment.is_active = False
        assignment.completed_date = now_utc()
        
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

def calculate_order_profitability(order_id):
    """حساب ربحية الطلبية"""
    try:
        from sqlalchemy.orm import joinedload
        
        # جلب الطلبية مع علاقاتها
        order = Order.query.options(
            joinedload(Order.order_expenses),
            joinedload(Order.order_transports)
        ).get(order_id)
        
        if not order:
            return None
        
        # إعادة حساب التكاليف
        expenses_total = sum(exp.total_amount for exp in order.order_expenses)
        transport_total = sum(trans.transport_amount for trans in order.order_transports)
        total_costs = expenses_total + transport_total
        
        profit = order.total - total_costs
        profit_percentage = (profit / order.total * 100) if order.total > 0 else 0
        
        return {
            'order_id': order.id,
            'total_amount': order.total,
            'total_expenses': expenses_total,
            'total_transport': transport_total,
            'total_costs': total_costs,
            'profit': profit,
            'profit_percentage': profit_percentage,
            'is_profitable': profit >= 0
        }
    except Exception as e:
        print(f"Error in calculate_order_profitability: {e}")
        return None

def get_financial_overview(period='month'):
    """نظرة عامة على الوضع المالي"""
    today = now_utc().date()
    
    if period == 'month':
        start_date = today.replace(day=1)
    elif period == 'week':
        start_date = today - timedelta(days=today.weekday())
    else:  # day
        start_date = today
    
    # الطلبيات المدفوعة
    paid_orders = Order.query.filter(
        Order.is_paid == True,
        Order.created_at >= start_date
    ).all()
    total_paid = sum(order.total for order in paid_orders)
    
    # الطلبيات غير المدفوعة
    unpaid_orders = Order.query.filter(
        Order.is_paid == False,
        Order.created_at >= start_date
    ).all()
    total_unpaid = sum(order.total for order in unpaid_orders)
    
    # المصاريف
    expenses = Expense.query.filter(
        Expense.purchase_date >= start_date
    ).all()
    total_expenses = sum(expense.total_amount for expense in expenses)
    
    # النقل
    transports = Transport.query.filter(
        Transport.transport_date >= start_date
    ).all()
    total_transports = sum(transport.transport_amount for transport in transports)
    
    return {
        'period': period,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        'total_expenses': total_expenses,
        'total_transports': total_transports,
        'net_income': total_paid - total_expenses - total_transports
    }

# ========================
# 📋 نظام المهام الذكي
# ========================
# في قسم نظام المهام الذكي في models.py - تحديث نموذج Task
class Task(db.Model):
    __tablename__ = 'task'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    priority = db.Column(db.String(20), default='medium')
    status = db.Column(db.String(20), default='pending')
    task_type = db.Column(db.String(50), default='general')
    assigned_to = db.Column(db.String(50))
    due_date = db.Column(db.Date)
    related_entity_type = db.Column(db.String(50))
    related_entity_id = db.Column(db.Integer)
    auto_generated = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=now_utc)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)
    completed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    task_scope = db.Column(db.String(20), default='internal')
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=True)
    worker = db.relationship('Worker', backref='assigned_tasks')
    assigned_by_partner = db.Column(db.Boolean, default=False)
    visibility_scope = db.Column(db.String(20), default='all')
    waiting_approval = db.Column(db.Boolean, default=False)
    completion_notes = db.Column(db.Text)
    approved_by = db.Column(db.String(50))
    approval_date = db.Column(db.DateTime)
    assignment_type = db.Column(db.String(50), default='workshop')
    
    # 🆕 الحقول الجديدة لنظام الإدارة
    admin_assigned_to = db.Column(db.String(50))  # الأدمن المعين له المهمة
    admin_approval_required = db.Column(db.Boolean, default=False)  # تحتاج موافقة أدمن آخر
    admin_approved = db.Column(db.Boolean, default=False)  # تمت الموافقة من الأدمن
    admin_approved_by = db.Column(db.String(50))  # الأدمن الذي وافق
    admin_approval_date = db.Column(db.DateTime)
    suspension_requested = db.Column(db.Boolean, default=False)  # طلب تعليق من العامل
    suspension_reason = db.Column(db.Text)  # سبب التعليق
    suspension_approved = db.Column(db.Boolean, default=False)  # تمت الموافقة على التعليق
    archived = db.Column(db.Boolean, default=False)  # مؤرشف

    @property
    def is_overdue(self):
        """هل المهمة متأخرة؟"""
        if self.due_date and self.status in ['pending', 'in_progress']:
            return self.due_date < datetime.now(timezone.utc).date()
        return False
    
    @property
    def related_order(self):
        """الحصول على الطلبية المرتبطة"""
        if self.related_entity_type == 'order' and self.related_entity_id:
            return Order.query.get(self.related_entity_id)
        return None

    @property
    def days_until_due(self):
        """الأيام المتبقية حتى الموعد النهائي"""
        if self.due_date and self.status in ['pending', 'in_progress']:
            delta = self.due_date - datetime.now(timezone.utc).date()
            return delta.days
        return None

    @property
    def badge_color(self):
        """لون البادج حسب الأولوية"""
        colors = {
            'low': 'blue',
            'medium': 'green', 
            'high': 'orange',
            'critical': 'red'
        }
        return colors.get(self.priority, 'gray')

    @property
    def related_entity_info(self):
        """معلومات الكيان المرتبط"""
        if self.related_entity_type == 'order' and self.related_entity_id:
            order = Order.query.get(self.related_entity_id)
            return f"طلبية: {order.name}" if order else None
        elif self.related_entity_type == 'worker' and self.related_entity_id:
            worker = Worker.query.get(self.related_entity_id)
            return f"عامل: {worker.name}" if worker else None
        elif self.related_entity_type == 'debt' and self.related_entity_id:
            debt = Debt.query.get(self.related_entity_id)
            return f"دين: {debt.name}" if debt else None
        return None
# ========================
# 🤖 دوال المهام الذكية
# ========================
# 🆕 دوال نظام إدارة المهام بين الأدمن
def create_admin_task(title, description, priority, assigned_admin, due_date, created_by, require_approval=True):
    """إنشاء مهمة بين الأدمن"""
    task = Task(
        title=title,
        description=description,
        priority=priority,
        task_type='admin_task',
        assigned_to=assigned_admin,
        admin_assigned_to=assigned_admin,
        admin_approval_required=require_approval,
        due_date=due_date,
        created_by=created_by,
        task_scope='admin_management',
        visibility_scope='admins_only'
    )
    db.session.add(task)
    db.session.commit()
    return task

def approve_admin_task(task_id, approved_by):
    """موافقة الأدمن على مهمة"""
    task = Task.query.get(task_id)
    if task and task.admin_approval_required and not task.admin_approved:
        task.admin_approved = True
        task.admin_approved_by = approved_by
        task.admin_approval_date = datetime.now(timezone.utc)
        task.status = 'in_progress'
        db.session.commit()
        return True
    return False

def complete_admin_task(task_id, completion_notes, completed_by):
    """إكمال مهمة أدمن وطلب الموافقة النهائية"""
    task = Task.query.get(task_id)
    if task and task.admin_approved and task.status == 'in_progress':
        task.status = 'completed'
        task.completion_notes = completion_notes
        task.completed_at = datetime.now(timezone.utc)
        task.waiting_approval = True  # تنتظر موافقة أدمن آخر
        db.session.commit()
        return True
    return False

def final_approve_admin_task(task_id, approved_by):
    """الموافقة النهائية على مهمة أدمن مكتملة"""
    task = Task.query.get(task_id)
    if task and task.waiting_approval and task.status == 'completed':
        task.waiting_approval = False
        task.approved_by = approved_by
        task.approval_date = datetime.now(timezone.utc)
        task.archived = True  # أرشفة المهمة
        db.session.commit()
        return True
    return False

def request_task_suspension(task_id, reason, requested_by):
    """طلب تعليق مهمة من قبل العامل"""
    task = Task.query.get(task_id)
    if task and task.worker_id and task.status == 'in_progress':
        task.suspension_requested = True
        task.suspension_reason = reason
        task.status = 'suspended'
        db.session.commit()
        return True
    return False

def approve_suspension(task_id, approved_by):
    """موافقة الإدارة على تعليق المهمة"""
    task = Task.query.get(task_id)
    if task and task.suspension_requested and not task.suspension_approved:
        task.suspension_approved = True
        task.suspension_approved_by = approved_by
        db.session.commit()
        return True
    return False

def resume_suspended_task(task_id, resumed_by):
    """استئناف مهمة معلقة"""
    task = Task.query.get(task_id)
    if task and task.status == 'suspended':
        task.status = 'in_progress'
        task.suspension_requested = False
        task.suspension_approved = False
        task.suspension_reason = None
        db.session.commit()
        return True
    return False

def archive_completed_tasks():
    """أرشفة المهام المكتملة والمقبولة"""
    completed_tasks = Task.query.filter(
        Task.status == 'completed',
        Task.waiting_approval == False,
        Task.archived == False
    ).all()
    
    for task in completed_tasks:
        task.archived = True
    
    db.session.commit()
    return len(completed_tasks)

# 🔥 نموذج جديد لإدارة الصلاحيات
class UserPermission(db.Model):
    __tablename__ = 'user_permission'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app_user.id'))
    module = db.Column(db.String(50))  # orders, expenses, workers, tasks, etc.
    can_view = db.Column(db.Boolean, default=False)
    can_edit = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_export = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_utc)
    
    user = db.relationship('User', backref='user_permissions')

# 🔥 دوال مساعدة للصلاحيات
def check_permission(user_id, module, action):
    """التحقق من صلاحية مستخدم"""
    user = User.query.get(user_id)
    if not user:
        return False
    
    # المديرين لديهم جميع الصلاحيات
    if user.role in ['admin', 'manager']:
        return True
    
    # العمال - صلاحيات محدودة
    permission = UserPermission.query.filter_by(
        user_id=user_id, 
        module=module
    ).first()
    
    if not permission:
        return False
    
    if action == 'view':
        return permission.can_view
    elif action == 'edit':
        return permission.can_edit
    elif action == 'delete':
        return permission.can_delete
    elif action == 'export':
        return permission.can_export
    
    return False

def set_default_permissions(user_id, role):
    """تعيين الصلاحيات الافتراضية حسب الدور"""
    if role == 'worker':
        # صلاحيات العمال
        modules = [
            ('tasks', True, False, False, False),
            ('orders', True, False, False, False),
            ('dashboard', True, False, False, False)
        ]
    elif role == 'user':
        # صلاحيات المستخدم العادي
        modules = [
            ('tasks', True, True, False, False),
            ('orders', True, True, False, False),
            ('expenses', True, False, False, False),
            ('dashboard', True, False, False, False)
        ]
    else:  # admin/manager
        # المديرين لديهم جميع الصلاحيات (لا داعي لتسجيلها)
        return
    
    for module, view, edit, delete, export in modules:
        permission = UserPermission(
            user_id=user_id,
            module=module,
            can_view=view,
            can_edit=edit,
            can_delete=delete,
            can_export=export
        )
        db.session.add(permission)

def get_user_accessible_tasks(user_id):
    """جلب المهام المتاحة للمستخدم حسب صلاحياته"""
    user = User.query.get(user_id)
    
    if not user:
        return []
    
    # المديرين يرون جميع المهام
    if user.role in ['admin', 'manager']:
        return Task.query.all()
    
    # العمال يرون فقط المهام المخصصة لهم أو المهام العامة
    return Task.query.filter(
        (Task.worker_id == user_id) | 
        (Task.visibility_scope.in_(['all', 'workers_only']))
    ).all()

def generate_auto_tasks():
    """توليد مهام تلقائية بناءً على بيانات النظام"""
    tasks_created = 0
    
    try:
        # 1. فحص الديون المتأخرة
        overdue_debts = Debt.query.filter(
            Debt.status == 'unpaid',
            Debt.start_date < (datetime.now(timezone.utc).date() - timedelta(days=30))
        ).all()
        
        for debt in overdue_debts:
            existing_task = Task.query.filter(
                Task.related_entity_type == 'debt',
                Task.related_entity_id == debt.id,
                Task.status.in_(['pending', 'in_progress'])
            ).first()
            
            if not existing_task:
                task = Task(
                    title=f"متابعة دين متأخر - {debt.name}",
                    description=f"دين بقيمة {debt.debt_amount} دج متأخر منذ أكثر من 30 يوم. المتبقي: {debt.remaining_amount} دج",
                    priority='high' if debt.remaining_amount > 10000 else 'medium',
                    task_type='debt',
                    related_entity_type='debt',
                    related_entity_id=debt.id,
                    due_date=datetime.now(timezone.utc).date() + timedelta(days=3),
                    auto_generated=True,
                    created_by='system'
                )
                db.session.add(task)
                tasks_created += 1
        
        # 2. فحص الطلبيات المتوقفة
        stalled_orders = Order.query.filter(
            Order.status_id.isnot(None),
            Order.actual_delivery_date.is_(None),
            Order.created_at < (datetime.now(timezone.utc) - timedelta(days=14))
        ).all()
        
        for order in stalled_orders:
            existing_task = Task.query.filter(
                Task.related_entity_type == 'order',
                Task.related_entity_id == order.id,
                Task.status.in_(['pending', 'in_progress'])
            ).first()
            
            if not existing_task:
                task = Task(
                    title=f"متابعة طلبية متوقفة - {order.name}",
                    description=f"الطلبية #{order.id} متوقفة منذ أكثر من أسبوعين. القيمة: {order.total} دج",
                    priority='medium',
                    task_type='order', 
                    related_entity_type='order',
                    related_entity_id=order.id,
                    due_date=datetime.now(timezone.utc).date() + timedelta(days=7),
                    auto_generated=True,
                    created_by='system'
                )
                db.session.add(task)
                tasks_created += 1
        
        # 3. فحص العمال بدون نشاط
        inactive_workers = Worker.query.filter(
            Worker.is_active == True,
            ~Worker.worker_assignments.any(OrderAssignment.is_active == True)
        ).all()
        
        for worker in inactive_workers:
            existing_task = Task.query.filter(
                Task.related_entity_type == 'worker',
                Task.related_entity_id == worker.id,
                Task.status.in_(['pending', 'in_progress'])
            ).first()
            
            if not existing_task and worker.monthly_salary > 0:
                task = Task(
                    title=f"مراجعة عامل بدون مهام - {worker.name}",
                    description=f"العامل {worker.name} بدون مهام نشطة مع راتب {worker.monthly_salary} دج",
                    priority='low',
                    task_type='worker',
                    related_entity_type='worker', 
                    related_entity_id=worker.id,
                    due_date=datetime.now(timezone.utc).date() + timedelta(days=14),
                    auto_generated=True,
                    created_by='system'
                )
                db.session.add(task)
                tasks_created += 1
        
        if tasks_created > 0:
            db.session.commit()
        
        return tasks_created
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في توليد المهام التلقائية: {e}")
        return 0
    

# 🆕 تحديث دالة توليد المهام الذكية
def generate_smart_tasks():
    """توليد مهام ذكية حسب أنواع المستخدمين"""
    tasks_created = 0
    
    try:
        # 1. مهام النظام التلقائية (للجميع)
        system_tasks = generate_system_tasks()
        tasks_created += system_tasks
        
        # 2. مهام المحاسبة بين الشركاء (للمديرين فقط)
        accountability_tasks = generate_accountability_tasks()
        tasks_created += accountability_tasks
        
        # 3. مهام العمال (مخصصة للعمال)
        worker_tasks = generate_worker_tasks()
        tasks_created += worker_tasks
        
        if tasks_created > 0:
            db.session.commit()
        
        return tasks_created
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في توليد المهام الذكية: {e}")
        return 0


def generate_accountability_tasks():
    """إنشاء مهام محاسبة بين الشركاء"""
    tasks_created = 0
    
    # مهام المراجعة المالية الشهرية
    today = datetime.now(timezone.utc).date()
    first_of_month = today.replace(day=1)
    
    if today.day in [1, 15]:  # أول ومنتصف الشهر
        existing_task = Task.query.filter(
            Task.task_scope == 'accountability',
            Task.title.like('%مراجعة مالية%'),
            Task.created_at >= first_of_month
        ).first()
        
        if not existing_task:
            task = Task(
                title="مراجعة المصاريف والمدفوعات الشهرية",
                description="مراجعة وتدقيق جميع المصاريف والمدفوعات للشهر الحالي وتوزيع الأرباح",
                task_scope="accountability",
                priority="high",
                task_type="expense",
                assigned_to="الشركاء",
                due_date=today + timedelta(days=3),
                auto_generated=True,
                created_by="system",
                visibility_scope="managers_only"
            )
            db.session.add(task)
            tasks_created += 1
    
    return tasks_created

def generate_worker_tasks():
    """إنشاء مهام مخصصة للعمال"""
    tasks_created = 0
    active_workers = Worker.query.filter_by(is_active=True).all()
    
    for worker in active_workers:
        # مهام المتابعة الأسبوعية
        existing_task = Task.query.filter(
            Task.worker_id == worker.id,
            Task.task_scope == 'worker',
            Task.created_at >= (datetime.now(timezone.utc) - timedelta(days=7))
        ).first()
        
        if not existing_task and worker.assigned_orders:
            task = Task(
                title=f"متابعة أعمال العامل {worker.name}",
                description=f"متابعة تقدم العامل في الطلبيات الموكلة له والتحقق من الجودة",
                task_scope="worker",
                priority="medium",
                task_type="worker",
                worker_id=worker.id,
                assigned_to=worker.name,
                due_date=datetime.now(timezone.utc).date() + timedelta(days=2),
                auto_generated=True,
                created_by="system",
                visibility_scope="managers_only"
            )
            db.session.add(task)
            tasks_created += 1
    
    return tasks_created

def get_urgent_tasks(limit=10):
    """جلب المهام العاجلة"""
    return Task.query.filter(
        Task.status.in_(['pending', 'in_progress']),
        Task.priority.in_(['high', 'critical'])
    ).order_by(
        Task.priority.desc(),
        Task.due_date.asc()
    ).limit(limit).all()

def complete_task(task_id, user_name, notes=""):
    """إكمال مهمة"""
    task = Task.query.get(task_id)
    if task:
        task.status = 'completed'
        task.completed_at = datetime.now(timezone.utc)
        task.updated_at = datetime.now(timezone.utc)
        task.notes = notes if notes else task.notes
        db.session.commit()
        return True
    return False

def create_manual_task(title, description, priority, task_type, assigned_to, due_date, user_name, related_entity_type=None, related_entity_id=None):
    """إنشاء مهمة يدوية"""
    task = Task(
        title=title,
        description=description,
        priority=priority,
        task_type=task_type,
        assigned_to=assigned_to,
        due_date=due_date,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        created_by=user_name
    )
    db.session.add(task)
    db.session.commit()
    return task

# 🔧 دوال مساعدة للنظام
def is_admin_user(username=None):
    """التحقق إذا كان المستخدم مسؤول"""
    if username is None:
        # إذا لم يتم تمرير اسم مستخدم، نحاول الحصول عليه من الجلسة
        from flask import session
        if 'user' not in session:
            return False
        username = session['user']
    
    user = User.query.filter_by(username=username).first()
    return user and user.role in ['admin', 'manager']

def total_debts():
    """حساب إجمالي الديون"""
    return Debt.query.filter_by(status="unpaid").count()

def get_admin_users_list():
    """جلب قائمة الأدمن"""
    return User.query.filter(User.role.in_(['admin', 'manager'])).all()

def get_orders_health_stats():
    """جلب إحصائيات صحة الطلبيات"""
    total_orders = Order.query.count()
    orders_with_debts = 0  # يمكنك تحسين هذا المنطق
    
    return {
        'total_orders': total_orders,
        'orders_with_debts': orders_with_debts,
        'healthy_orders': total_orders - orders_with_debts
    }