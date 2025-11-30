from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from models import OrderHistory, WorkerHistory, Expense, Transport, Debt, db
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import joinedload

activities_bp = Blueprint('activities', __name__)

@activities_bp.route("/activities")
def activities():
    """صفحة الأحداث والأنشطة"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    activity_type = request.args.get('type', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # جمع الأحداث من جميع المصادر
    all_activities = []
    
    # أحداث الطلبيات
    order_query = OrderHistory.query
    if date_from:
        order_query = order_query.filter(OrderHistory.timestamp >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        order_query = order_query.filter(OrderHistory.timestamp <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
    
    order_histories = order_query.order_by(OrderHistory.timestamp.desc()).limit(50).all()
    for history in order_histories:
        if activity_type != 'all' and activity_type != 'order':
            continue
            
        activity_type_detailed = 'order'
        if 'دفعة' in history.change_type or 'دفع' in history.change_type:
            activity_type_detailed = 'payment'
        elif 'نقل' in history.change_type:
            activity_type_detailed = 'transport'
        elif 'مصروف' in history.change_type:
            activity_type_detailed = 'expense'
        elif 'عامل' in history.change_type or 'تعيين' in history.change_type:
            activity_type_detailed = 'worker'
            
        all_activities.append({
            'type': activity_type_detailed,
            'icon': get_activity_icon(activity_type_detailed),
            'title': history.change_type,
            'description': history.details,
            'category': get_activity_category(activity_type_detailed),
            'timestamp': history.timestamp,
            'time': format_time_ago(history.timestamp),
            'user': history.user or 'النظام',
            'classes': get_activity_classes(activity_type_detailed)
        })
    
    # أحداث العمال
    if activity_type in ['all', 'worker']:
        worker_query = WorkerHistory.query
        if date_from:
            worker_query = worker_query.filter(WorkerHistory.timestamp >= datetime.strptime(date_from, "%Y-%m-%d"))
        if date_to:
            worker_query = worker_query.filter(WorkerHistory.timestamp <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        
        worker_histories = worker_query.order_by(WorkerHistory.timestamp.desc()).limit(30).all()
        for history in worker_histories:
            all_activities.append({
                'type': 'worker',
                'icon': get_activity_icon('worker'),
                'title': history.change_type,
                'description': history.details,
                'category': get_activity_category('worker'),
                'timestamp': history.timestamp,
                'time': format_time_ago(history.timestamp),
                'user': history.user or 'النظام',
                'classes': get_activity_classes('worker')
            })
    
    # أحداث المصاريف
    if activity_type in ['all', 'expense']:
        expense_query = Expense.query
        if date_from:
            expense_query = expense_query.filter(Expense.created_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        if date_to:
            expense_query = expense_query.filter(Expense.created_at <= datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1))
        
        recent_expenses = expense_query.order_by(Expense.created_at.desc()).limit(20).all()
        for expense in recent_expenses:
            all_activities.append({
                'type': 'expense',
                'icon': get_activity_icon('expense'),
                'title': 'مصروف جديد',
                'description': f"{expense.description} - {expense.total_amount} دج",
                'category': get_activity_category('expense'),
                'timestamp': expense.created_at,
                'time': format_time_ago(expense.created_at),
                'user': expense.recorded_by,
                'classes': get_activity_classes('expense')
            })
    
    # ترتيب جميع الأحداث حسب الوقت (الأحدث أولاً)
    all_activities.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return render_template("activities.html",
                         activities=all_activities,
                         activity_type=activity_type,
                         date_from=date_from,
                         date_to=date_to,
                         now=datetime.now(timezone.utc))

# دوال مساعدة (نفس الموجودة في dashboard)
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