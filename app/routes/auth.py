from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from models import User, Worker, db
from datetime import datetime, timezone

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        # 🔍 البحث في جدول المديرين
        admin_user = User.query.filter_by(username=username, is_active=True).first()
        
        if admin_user and admin_user.check_password(password):
            # ✅ تسجيل دخول مدير
            session["user"] = username
            session["role"] = admin_user.role
            session["user_id"] = admin_user.id
            session["user_type"] = "admin"
            
            admin_user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            
            print(f"✅ تسجيل دخول مدير ناجح: {username}")
            return redirect(url_for("dashboard.dashboard"))
        
        # 🔍 البحث في جدول العمال
        worker_user = Worker.query.filter_by(
            username=username, 
            is_login_active=True,
            is_active=True
        ).first()
        
        if worker_user and worker_user.check_password(password):
            # ✅ تسجيل دخول عامل
            session["user"] = username
            session["role"] = "worker"
            session["user_id"] = worker_user.id
            session["user_type"] = "worker"
            session["worker_name"] = worker_user.name
            
            worker_user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            
            print(f"✅ تسجيل دخول عامل ناجح: {username}")
            return redirect(url_for("worker.worker_dashboard"))
        
        return render_template("login.html", error="❌ اسم المستخدم أو كلمة المرور غير صحيحة")
    
    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    """تسجيل الخروج"""
    session.clear()
    return redirect(url_for("auth.login"))