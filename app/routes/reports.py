# ====== routes/reports.py ======
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, extract
from models import Order, Expense, Transport, Worker, Debt, Purchase, OrderHistory, WorkerHistory, db

# ✅ تعريف الـ Blueprint هنا بدلاً من الاستيراد
reports_bp = Blueprint('reports', __name__)

@reports_bp.route("/reports")
def reports():
    """صفحة التقارير"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    return render_template("reports.html")

@reports_bp.route("/api/reports/financial")
def financial_report():
    """تقرير مالي"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        period = request.args.get('period', 'month')  # month, quarter, year
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # تحديد نطاق التاريخ
        if date_from and date_to:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
            end_date = datetime.strptime(date_to, "%Y-%m-%d")
        else:
            end_date = datetime.now(timezone.utc)
            if period == 'month':
                start_date = end_date - timedelta(days=30)
            elif period == 'quarter':
                start_date = end_date - timedelta(days=90)
            else:  # year
                start_date = end_date - timedelta(days=365)
        
        # إيرادات الطلبيات
        orders_revenue = db.session.query(
            func.sum(Order.total).label('total_revenue'),
            func.sum(Order.paid).label('total_paid'),
            func.count(Order.id).label('orders_count')
        ).filter(
            Order.created_at.between(start_date, end_date)
        ).first()
        
        # المصاريف
        expenses_total = db.session.query(
            func.sum(Expense.total_amount).label('total_expenses')
        ).filter(
            Expense.purchase_date.between(start_date, end_date)
        ).first()
        
        # تكاليف النقل
        transport_total = db.session.query(
            func.sum(Transport.transport_amount).label('total_transport')
        ).filter(
            Transport.transport_date.between(start_date, end_date)
        ).first()
        
        # رواتب العمال
        workers_salaries = db.session.query(
            func.sum(Worker.total_salary).label('total_salaries')
        ).scalar() or 0
        
        # الديون
        debts_total = db.session.query(
            func.sum(Debt.debt_amount).label('total_debt'),
            func.sum(Debt.paid_amount).label('total_paid_debt')
        ).first()
        
        # حساب الربح الصافي
        total_revenue = orders_revenue[0] or 0
        total_expenses = (expenses_total[0] or 0) + (transport_total[0] or 0) + workers_salaries
        net_profit = total_revenue - total_expenses
        
        return jsonify({
            "success": True,
            "period": {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d")
            },
            "revenue": {
                "total_revenue": total_revenue,
                "total_paid": orders_revenue[1] or 0,
                "orders_count": orders_revenue[2] or 0
            },
            "expenses": {
                "purchases": expenses_total[0] or 0,
                "transport": transport_total[0] or 0,
                "salaries": workers_salaries,
                "total_expenses": total_expenses
            },
            "profit": {
                "net_profit": net_profit,
                "profit_margin": (net_profit / total_revenue * 100) if total_revenue > 0 else 0
            },
            "debts": {
                "total_debt": debts_total[0] or 0,
                "total_paid_debt": debts_total[1] or 0,
                "remaining_debt": (debts_total[0] or 0) - (debts_total[1] or 0)
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@reports_bp.route("/api/reports/workers")
def workers_report():
    """تقرير العمال"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        workers = Worker.query.filter_by(is_active=True).all()
        
        workers_data = []
        for worker in workers:
            # عدد الطلبيات المكتملة
            completed_orders = len([assignment for assignment in worker.order_assignments if not assignment.is_active])
            
            # إجمالي الراتب والمستحقات
            total_earnings = worker.total_salary
            total_deductions = worker.advances + (worker.absences * (worker.monthly_salary / 30))
            net_salary = total_earnings - total_deductions
            
            workers_data.append({
                "id": worker.id,
                "name": worker.name,
                "completed_orders": completed_orders,
                "total_earnings": total_earnings,
                "total_deductions": total_deductions,
                "net_salary": net_salary,
                "absences": worker.absences,
                "advances": worker.advances,
                "start_date": worker.start_date.strftime("%Y-%m-%d") if worker.start_date else "غير محدد"
            })
        
        return jsonify({
            "success": True,
            "workers": workers_data,
            "total_workers": len(workers),
            "total_salaries": sum(worker.total_salary for worker in workers)
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@reports_bp.route("/api/reports/orders")
def orders_report():
    """تقرير الطلبيات"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        status_filter = request.args.get('status', 'all')
        
        query = Order.query
        
        if date_from and date_to:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
            end_date = datetime.strptime(date_to, "%Y-%m-%d")
            query = query.filter(Order.created_at.between(start_date, end_date))
        
        if status_filter != 'all':
            if status_filter == 'paid':
                query = query.filter(Order.is_paid == True)
            elif status_filter == 'unpaid':
                query = query.filter(Order.is_paid == False)
        
        orders = query.all()
        
        orders_data = []
        for order in orders:
            # حساب التكاليف والربح
            total_costs = order.total_costs
            net_profit = order.total - total_costs
            profit_margin = (net_profit / order.total * 100) if order.total > 0 else 0
            
            orders_data.append({
                "id": order.id,
                "customer_name": order.name,
                "product": order.product,
                "total_amount": order.total,
                "paid_amount": order.paid,
                "remaining_amount": order.remaining,
                "total_costs": total_costs,
                "net_profit": net_profit,
                "profit_margin": profit_margin,
                "is_paid": order.is_paid,
                "created_date": order.created_at.strftime("%Y-%m-%d"),
                "wilaya": order.wilaya
            })
        
        # إحصائيات عامة
        total_orders = len(orders)
        total_revenue = sum(order.total for order in orders)
        total_profit = sum(order.total - order.total_costs for order in orders)
        paid_orders = len([order for order in orders if order.is_paid])
        
        return jsonify({
            "success": True,
            "orders": orders_data,
            "statistics": {
                "total_orders": total_orders,
                "total_revenue": total_revenue,
                "total_profit": total_profit,
                "paid_orders": paid_orders,
                "unpaid_orders": total_orders - paid_orders,
                "average_profit_margin": (total_profit / total_revenue * 100) if total_revenue > 0 else 0
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@reports_bp.route("/api/reports/expenses")
def expenses_report():
    """تقرير المصاريف"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        category_filter = request.args.get('category', 'all')
        
        query = Expense.query
        
        if date_from and date_to:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
            end_date = datetime.strptime(date_to, "%Y-%m-%d")
            query = query.filter(Expense.purchase_date.between(start_date, end_date))
        
        if category_filter != 'all':
            query = query.filter(Expense.category_id == int(category_filter))
        
        expenses = query.all()
        
        # تجميع حسب التصنيف
        categories_summary = {}
        for expense in expenses:
            category_name = expense.category.name if expense.category else "عام"
            if category_name not in categories_summary:
                categories_summary[category_name] = {
                    "count": 0,
                    "total_amount": 0
                }
            categories_summary[category_name]["count"] += 1
            categories_summary[category_name]["total_amount"] += expense.total_amount
        
        return jsonify({
            "success": True,
            "expenses": [{
                "id": exp.id,
                "description": exp.description,
                "category": exp.category.name if exp.category else "عام",
                "amount": exp.total_amount,
                "date": exp.purchase_date.strftime("%Y-%m-%d"),
                "supplier": exp.supplier.name if exp.supplier else "غير معروف",
                "payment_status": exp.payment_status
            } for exp in expenses],
            "summary": {
                "total_expenses": sum(exp.total_amount for exp in expenses),
                "categories_summary": categories_summary,
                "expenses_count": len(expenses)
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})