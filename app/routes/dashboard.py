from flask import Blueprint, render_template, session, redirect, url_for, jsonify
from models import Order, Worker, Debt, Expense, Purchase, OrderHistory, WorkerHistory, Transport
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import joinedload

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route("/dashboard")
def dashboard():
    """لوحة التحكم الرئيسية"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    # جلب بيانات لوحة التحكم مع الأحداث الحديثة
    dashboard_data = get_dashboard_data()
    
    return render_template("dashboard.html", 
                         user=session["user"],
                         recent_activities=dashboard_data['recent_activities'],
                         total_orders=dashboard_data['total_orders'],
                         total_workers=dashboard_data['total_workers'],
                         total_debts=dashboard_data['total_debts'],
                         total_expenses=dashboard_data['total_expenses'],
                         total_purchases=dashboard_data.get('total_purchases', 0),
                         now=datetime.now(timezone.utc))

def get_dashboard_data():
    """جلب بيانات لوحة التحكم مع الأحداث الحديثة"""
    try:
        today = datetime.now(timezone.utc).date()
        
        # البيانات الأساسية
        total_orders = Order.query.count()
        total_workers = Worker.query.filter_by(is_active=True).count()
        total_debts = Debt.query.filter_by(status="unpaid").count()
        total_expenses = Expense.query.count()
        total_purchases = Purchase.query.count()
        
        # جمع الأحداث الحديثة من جميع المصادر
        recent_activities = []
        
        # 1. أحداث الطلبيات (آخر 10 أحداث)
        order_histories = OrderHistory.query.order_by(OrderHistory.timestamp.desc()).limit(10).all()
        for history in order_histories:
            activity_type = 'order'
            if 'دفعة' in history.change_type or 'دفع' in history.change_type:
                activity_type = 'payment'
            elif 'نقل' in history.change_type:
                activity_type = 'transport'
            elif 'مصروف' in history.change_type:
                activity_type = 'expense'
            elif 'عامل' in history.change_type or 'تعيين' in history.change_type:
                activity_type = 'worker'
                
            recent_activities.append({
                'type': activity_type,
                'icon': get_activity_icon(activity_type),
                'title': history.change_type,
                'description': history.details,
                'category': get_activity_category(activity_type),
                'time': format_time_ago(history.timestamp),
                'user': history.user or 'النظام',
                'classes': get_activity_classes(activity_type)
            })
        
        # 2. أحداث العمال (آخر 5 أحداث)
        worker_histories = WorkerHistory.query.order_by(WorkerHistory.timestamp.desc()).limit(5).all()
        for history in worker_histories:
            recent_activities.append({
                'type': 'worker',
                'icon': get_activity_icon('worker'),
                'title': history.change_type,
                'description': history.details,
                'category': get_activity_category('worker'),
                'time': format_time_ago(history.timestamp),
                'user': history.user or 'النظام',
                'classes': get_activity_classes('worker')
            })
        
        # 3. أحداث المصاريف الجديدة (آخر 5 أحداث)
        recent_expenses = Expense.query.order_by(Expense.created_at.desc()).limit(5).all()
        for expense in recent_expenses:
            recent_activities.append({
                'type': 'expense',
                'icon': get_activity_icon('expense'),
                'title': 'مصروف جديد',
                'description': f"{expense.description} - {expense.total_amount} دج",
                'category': get_activity_category('expense'),
                'time': format_time_ago(expense.created_at),
                'user': expense.recorded_by,
                'classes': get_activity_classes('expense')
            })
        
        # 4. أحداث النقل الجديدة (آخر 5 أحداث)
        recent_transports = Transport.query.order_by(Transport.created_at.desc()).limit(5).all()
        for transport in recent_transports:
            recent_activities.append({
                'type': 'transport',
                'icon': get_activity_icon('transport'),
                'title': 'نقل جديد',
                'description': f"{transport.purpose} - {transport.transport_amount} دج",
                'category': get_activity_category('transport'),
                'time': format_time_ago(transport.created_at),
                'user': transport.recorded_by,
                'classes': get_activity_classes('transport')
            })
        
        # ترتيب جميع الأحداث حسب الوقت (الأحدث أولاً) وأخذ آخر 15 حدث
        recent_activities.sort(key=lambda x: x.get('timestamp', datetime.now(timezone.utc)), reverse=True)
        recent_activities = recent_activities[:15]
        
        return {
            'total_orders': total_orders,
            'total_workers': total_workers,
            'total_debts': total_debts,
            'total_expenses': total_expenses,
            'total_purchases': total_purchases,
            'recent_activities': recent_activities
        }
        
    except Exception as e:
        print(f"❌ خطأ في جلب بيانات لوحة التحكم: {e}")
        return {
            'total_orders': 0,
            'total_workers': 0,
            'total_debts': 0,
            'total_expenses': 0,
            'total_purchases': 0,
            'recent_activities': []
        }

def get_activity_icon(activity_type):
    """الحصول على أيقونة النشاط"""
    icons = {
        'order': '📦',
        'payment': '💰',
        'transport': '🚚',
        'expense': '🧾',
        'worker': '👷',
        'debt': '💸'
    }
    return icons.get(activity_type, '📝')

def get_activity_category(activity_type):
    """الحصول على تصنيف النشاط"""
    categories = {
        'order': 'طلبية',
        'payment': 'دفعة',
        'transport': 'نقل',
        'expense': 'مصروف',
        'worker': 'عامل',
        'debt': 'دين'
    }
    return categories.get(activity_type, 'نشاط')

def get_activity_classes(activity_type):
    """الحصول على classes للنشاط"""
    classes = {
        'order': {
            'bg': 'bg-blue-50 dark:bg-blue-900/20',
            'border': 'border-blue-200 dark:border-blue-800',
            'text': 'text-blue-800 dark:text-blue-300',
            'desc': 'text-blue-600 dark:text-blue-400',
            'badge': 'text-blue-700 dark:text-blue-400 bg-blue-100 dark:bg-blue-800',
            'icon': 'text-blue-600 dark:text-blue-400'
        },
        'payment': {
            'bg': 'bg-green-50 dark:bg-green-900/20',
            'border': 'border-green-200 dark:border-green-800',
            'text': 'text-green-800 dark:text-green-300',
            'desc': 'text-green-600 dark:text-green-400',
            'badge': 'text-green-700 dark:text-green-400 bg-green-100 dark:bg-green-800',
            'icon': 'text-green-600 dark:text-green-400'
        },
        'transport': {
            'bg': 'bg-indigo-50 dark:bg-indigo-900/20',
            'border': 'border-indigo-200 dark:border-indigo-800',
            'text': 'text-indigo-800 dark:text-indigo-300',
            'desc': 'text-indigo-600 dark:text-indigo-400',
            'badge': 'text-indigo-700 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-800',
            'icon': 'text-indigo-600 dark:text-indigo-400'
        },
        'expense': {
            'bg': 'bg-orange-50 dark:bg-orange-900/20',
            'border': 'border-orange-200 dark:border-orange-800',
            'text': 'text-orange-800 dark:text-orange-300',
            'desc': 'text-orange-600 dark:text-orange-400',
            'badge': 'text-orange-700 dark:text-orange-400 bg-orange-100 dark:bg-orange-800',
            'icon': 'text-orange-600 dark:text-orange-400'
        },
        'worker': {
            'bg': 'bg-teal-50 dark:bg-teal-900/20',
            'border': 'border-teal-200 dark:border-teal-800',
            'text': 'text-teal-800 dark:text-teal-300',
            'desc': 'text-teal-600 dark:text-teal-400',
            'badge': 'text-teal-700 dark:text-teal-400 bg-teal-100 dark:bg-teal-800',
            'icon': 'text-teal-600 dark:text-teal-400'
        },
        'debt': {
            'bg': 'bg-red-50 dark:bg-red-900/20',
            'border': 'border-red-200 dark:border-red-800',
            'text': 'text-red-800 dark:text-red-300',
            'desc': 'text-red-600 dark:text-red-400',
            'badge': 'text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-800',
            'icon': 'text-red-600 dark:text-red-400'
        }
    }
    return classes.get(activity_type, {
        'bg': 'bg-gray-50 dark:bg-gray-800',
        'border': 'border-gray-200 dark:border-gray-700',
        'text': 'text-gray-800 dark:text-gray-300',
        'desc': 'text-gray-600 dark:text-gray-400',
        'badge': 'text-gray-700 dark:text-gray-400 bg-gray-100 dark:bg-gray-700',
        'icon': 'text-gray-600 dark:text-gray-400'
    })

def format_time_ago(timestamp):
    """تنسيق الوقت المنقضي"""
    now = datetime.now(timezone.utc)
    diff = now - timestamp
    
    if diff.days > 0:
        return f"قبل {diff.days} يوم"
    elif diff.seconds // 3600 > 0:
        return f"قبل {diff.seconds // 3600} ساعة"
    elif diff.seconds // 60 > 0:
        return f"قبل {diff.seconds // 60} دقيقة"
    else:
        return "الآن"