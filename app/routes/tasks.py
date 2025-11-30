from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from models import Task, Worker, OrderAssignment, db
from models import generate_auto_tasks, get_urgent_tasks, complete_task, create_manual_task
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import joinedload

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route("/tasks")
def tasks():
    """صفحة إدارة المهام الكاملة"""
    if "user" not in session:
        return redirect(url_for("auth.login"))
    
    # توليد المهام التلقائية أولاً
    generate_auto_tasks()
    
    # معاملات الفلترة
    status_filter = request.args.get('status', 'all')
    priority_filter = request.args.get('priority', 'all')
    task_type_filter = request.args.get('type', 'all')
    date_filter = request.args.get('date_filter', 'all')
    
    # بناء الاستعلام
    query = Task.query
    
    if status_filter != 'all':
        query = query.filter(Task.status == status_filter)
    else:
        query = query.filter(Task.status != 'completed')
    
    if priority_filter != 'all':
        query = query.filter(Task.priority == priority_filter)
    
    if task_type_filter != 'all':
        query = query.filter(Task.task_type == task_type_filter)
    
    # فلترة التاريخ
    today = datetime.now(timezone.utc).date()
    if date_filter == 'today':
        query = query.filter(Task.due_date == today)
    elif date_filter == 'tomorrow':
        query = query.filter(Task.due_date == today + timedelta(days=1))
    elif date_filter == 'week':
        query = query.filter(Task.due_date.between(today, today + timedelta(days=7)))
    elif date_filter == 'overdue':
        query = query.filter(Task.due_date < today, Task.status.in_(['pending', 'in_progress']))
    elif date_filter == 'upcoming':
        query = query.filter(Task.due_date > today + timedelta(days=7))
    
    # الترتيب
    tasks_list = query.order_by(
        Task.priority.desc(),
        Task.due_date.asc(),
        Task.created_at.desc()
    ).all()
    
    # الإحصائيات
    stats = {
        'total': Task.query.count(),
        'pending': Task.query.filter_by(status='pending').count(),
        'in_progress': Task.query.filter_by(status='in_progress').count(),
        'completed': Task.query.filter_by(status='completed').count(),
        'urgent': Task.query.filter(Task.priority.in_(['high', 'critical']), Task.status.in_(['pending', 'in_progress'])).count()
    }
    
    return render_template("tasks.html", 
                         tasks=tasks_list,
                         status_filter=status_filter,
                         priority_filter=priority_filter,
                         task_type_filter=task_type_filter,
                         date_filter=date_filter,
                         stats=stats,
                         user=session["user"],
                         now=datetime.now(timezone.utc))

@tasks_bp.route("/tasks/add", methods=['POST'])
def add_task():
    """إضافة مهمة جديدة"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        title = request.form.get('title')
        description = request.form.get('description', '')
        priority = request.form.get('priority', 'medium')
        task_type = request.form.get('task_type', 'general')
        assigned_to = request.form.get('assigned_to', '')
        due_date_str = request.form.get('due_date')
        
        if not title:
            return jsonify({"success": False, "error": "عنوان المهمة مطلوب"})
        
        due_date = None
        if due_date_str:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        
        task = create_manual_task(
            title=title,
            description=description,
            priority=priority,
            task_type=task_type,
            assigned_to=assigned_to,
            due_date=due_date,
            user_name=session["user"]
        )
        
        return jsonify({
            "success": True,
            "message": "تم إضافة المهمة بنجاح",
            "task_id": task.id
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@tasks_bp.route("/api/tasks/urgent")
def api_urgent_tasks():
    """API لجلب المهام العاجلة للوحة التحكم"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        # توليد المهام التلقائية أولاً
        generate_auto_tasks()
        
        urgent_tasks = get_urgent_tasks(5)
        
        tasks_data = []
        for task in urgent_tasks:
            tasks_data.append({
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "priority": task.priority,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "is_overdue": task.is_overdue,
                "days_until_due": task.days_until_due,
                "assigned_to": task.assigned_to,
                "task_type": task.task_type,
                "related_entity_info": task.related_entity_info,
                "auto_generated": task.auto_generated
            })
        
        return jsonify({
            "success": True,
            "tasks": tasks_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@tasks_bp.route("/api/tasks/complete/<int:task_id>", methods=['POST'])
def api_complete_task(task_id):
    """إكمال مهمة"""
    if "user" not in session:
        return jsonify({"success": False, "error": "غير مصرح"})
    
    try:
        notes = request.form.get('notes', '')
        success = complete_task(task_id, session["user"], notes)
        
        if success:
            return jsonify({
                "success": True, 
                "message": "تم إكمال المهمة بنجاح"
            })
        else:
            return jsonify({"success": False, "error": "لم يتم العثور على المهمة"})
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@tasks_bp.route("/api/tasks/stats")
def api_tasks_stats():
    """إحصائيات المهام"""
    if "user" not in session:
        return jsonify({"error": "غير مصرح"})
    
    try:
        stats = {
            'total_tasks': Task.query.count(),
            'pending_tasks': Task.query.filter_by(status='pending').count(),
            'in_progress_tasks': Task.query.filter_by(status='in_progress').count(),
            'completed_tasks': Task.query.filter_by(status='completed').count(),
            'urgent_tasks': Task.query.filter(Task.priority.in_(['high', 'critical']), Task.status.in_(['pending', 'in_progress'])).count(),
            'overdue_tasks': Task.query.filter(
                Task.due_date < datetime.now(timezone.utc).date(),
                Task.status.in_(['pending', 'in_progress'])
            ).count()
        }
        
        return jsonify({"success": True, "stats": stats})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    
@tasks_bp.context_processor
def inject_functions():
    """جعل الدوال متاحة في قوالب المهام"""
    return dict(
        is_admin_user=is_admin_user,
        get_admin_users_list=get_admin_users_list
    )