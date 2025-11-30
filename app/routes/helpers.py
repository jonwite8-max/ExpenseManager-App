# ====== routes/helpers.py ======
from models import User, Debt, Order
from datetime import datetime, timezone

def is_admin_user(username=None):
    """التحقق إذا كان المستخدم مسؤول"""
    if username is None:
        from flask import session
        if 'user' not in session:
            return False
        username = session['user']
    
    user = User.query.filter_by(username=username).first()
    return user and user.role in ['admin', 'manager']

def get_admin_users_list():
    """جلب قائمة الأدمن"""
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

def total_debts():
    """إجمالي الديون غير المدفوعة"""
    try:
        return Debt.query.filter_by(status="unpaid").count()
    except:
        return 0

def get_orders_health_stats():
    """جلب إحصائيات صحة الطلبيات"""
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