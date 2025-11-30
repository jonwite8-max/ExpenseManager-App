from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from models import Debt, db
from datetime import datetime, timezone

debts_bp = Blueprint('debts', __name__)

@debts_bp.route("/debts")
def debts():
    """صفحة إدارة الديون"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    status_filter = request.args.get('status', 'all')
    
    if status_filter == 'paid':
        debts_list = Debt.query.filter_by(status="paid").order_by(Debt.created_at.desc()).all()
    elif status_filter == 'unpaid':
        debts_list = Debt.query.filter_by(status="unpaid").order_by(Debt.created_at.desc()).all()
    else:
        debts_list = Debt.query.order_by(Debt.created_at.desc()).all()
    
    total_debt = sum(debt.remaining_amount for debt in debts_list if debt.status == 'unpaid')
    total_paid = sum(debt.paid_amount for debt in debts_list)
    
    return render_template("debts.html", 
                         debts=debts_list,
                         status_filter=status_filter,
                         total_debt=total_debt,
                         total_paid=total_paid)

@debts_bp.route("/debts/add", methods=["POST"])
def add_debt():
    """إضافة دين جديد"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        debt = Debt(
            name=request.form.get("name"),
            phone=request.form.get("phone", ""),
            address=request.form.get("address", ""),
            debt_amount=float(request.form.get("debt_amount", 0)),
            paid_amount=float(request.form.get("paid_amount", 0)),
            start_date=datetime.strptime(request.form.get("start_date"), "%Y-%m-%d"),
            due_date=datetime.strptime(request.form.get("due_date"), "%Y-%m-%d") if request.form.get("due_date") else None,
            status="unpaid" if float(request.form.get("paid_amount", 0)) < float(request.form.get("debt_amount", 0)) else "paid",
            description=request.form.get("description", ""),
            recorded_by=session["user"]
        )
        
        db.session.add(debt)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "تم إضافة الدين بنجاح",
            "debt_id": debt.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@debts_bp.route("/debts/payment/<int:id>", methods=["POST"])
def add_debt_payment(id):
    """إضافة دفعة على دين"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        debt = Debt.query.get_or_404(id)
        
        amount = float(request.form.get("amount", 0))
        payment_method = request.form.get("payment_method", "نقدي")
        notes = request.form.get("notes", "")
        
        if amount > debt.remaining_amount:
            return jsonify({"success": False, "error": f"المبلغ يتجاوز المتبقي ({debt.remaining_amount} دج)"})
        
        debt.paid_amount += amount
        debt.status = "paid" if debt.paid_amount >= debt.debt_amount else "unpaid"
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"تم إضافة دفعة بقيمة {amount} دج",
            "new_paid": debt.paid_amount,
            "new_remaining": debt.remaining_amount,
            "status": debt.status
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

@debts_bp.route("/debts/delete/<int:id>")
def delete_debt(id):
    """حذف دين"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    try:
        debt = Debt.query.get_or_404(id)
        db.session.delete(debt)
        db.session.commit()
        return redirect(url_for("debts.debts"))
    except Exception as e:
        db.session.rollback()
        return redirect(url_for("debts.debts"))
    
@debts_bp.context_processor
def inject_functions():
    """جعل الدوال متاحة في قوالب الديون"""
    return dict(
        is_admin_user=is_admin_user,
        total_debts=total_debts
    )