from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from models_worker import db, WorkerSession, WorkerNotification, WorkerLocationLog, WorkerOrderProgress
from datetime import datetime, timedelta
import requests
import math
import json

app = Flask(__name__)
app.secret_key = "worker_secret_key_2024"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///worker_data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# إعدادات الورشة (إحداثيات موقع الورشة)
WORKSHOP_COORDINATES = {
    'lat': 36.7525,  # سيتم ضبطها حسب موقعك الفعلي
    'lng': 3.0420,
    'radius': 300  # نصف القالمسموح به بالمتر
}

# رابط API مشروع الإدارة
ADMIN_API_BASE = "http://localhost:5000"

def calculate_distance(lat1, lng1, lat2, lng2):
    """حساب المسافة بين نقطتين باستخدام Haversine formula"""
    R = 6371000  # نصف قطر الأرض بالمتر
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat/2) * math.sin(delta_lat/2) + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * 
         math.sin(delta_lng/2) * math.sin(delta_lng/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def is_within_workshop(lat, lng):
    """التحقق إذا كان الموقع ضمن نطاق الورشة"""
    distance = calculate_distance(lat, lng, WORKSHOP_COORDINATES['lat'], WORKSHOP_COORDINATES['lng'])
    return distance <= WORKSHOP_COORDINATES['radius']

# ==================== APIs للربط مع مشروع الإدارة ====================

def get_worker_orders(worker_id):
    """جلب الطلبيات المعينة للعامل"""
    try:
        response = requests.get(f"{ADMIN_API_BASE}/api/workers/{worker_id}/assigned-orders",
                              headers={'Authorization': 'Bearer worker_app'})
        if response.status_code == 200:
            return response.json().get('orders', [])
        return []
    except:
        return []

def get_worker_salary_info(worker_id):
    """جلب معلومات الراتب للعامل"""
    try:
        response = requests.get(f"{ADMIN_API_BASE}/api/workers/{worker_id}/salary-info",
                              headers={'Authorization': 'Bearer worker_app'})
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def update_order_status(order_id, status, worker_id):
    """تحديث حالة الطلبية"""
    try:
        data = {
            'status': status,
            'worker_id': worker_id,
            'completed_at': datetime.utcnow().isoformat() if status == 'completed' else None
        }
        response = requests.put(f"{ADMIN_API_BASE}/api/orders/{order_id}/status",
                              json=data,
                              headers={'Authorization': 'Bearer worker_app'})
        return response.status_code == 200
    except:
        return False

def record_attendance_to_admin(worker_id, attendance_data):
    """تسجيل الحضور لمشروع الإدارة"""
    try:
        response = requests.post(f"{ADMIN_API_BASE}/api/workers/{worker_id}/attendance",
                               json=attendance_data,
                               headers={'Authorization': 'Bearer worker_app'})
        return response.status_code == 200
    except:
        return False

# ==================== مسارات التطبيق ====================

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # التحقق من بيانات الدخول مع مشروع الإدارة
        try:
            response = requests.post(f"{ADMIN_API_BASE}/api/workers/login",
                                   json={'username': username, 'password': password},
                                   headers={'Authorization': 'Bearer worker_app'})
            
            if response.status_code == 200:
                worker_data = response.json()
                session['worker_id'] = worker_data['id']
                session['worker_name'] = worker_data['name']
                session['worker_phone'] = worker_data.get('phone', '')
                
                # إنشاء إشعار ترحيب
                welcome_notification = WorkerNotification(
                    worker_id=worker_data['id'],
                    title='مرحباً بعودتك!',
                    message='تم تسجيل الدخول بنجاح إلى تطبيق العمال',
                    notification_type='welcome'
                )
                db.session.add(welcome_notification)
                db.session.commit()
                
                return redirect(url_for('dashboard'))
            else:
                return render_template('login_worker.html', error='بيانات الدخول غير صحيحة')
                
        except Exception as e:
            return render_template('login_worker.html', error='خطأ في الاتصال بالخادم')
    
    return render_template('login_worker.html')

@app.route('/dashboard')
def dashboard():
    if 'worker_id' not in session:
        return redirect(url_for('login'))
    
    worker_id = session['worker_id']
    
    # جلب الإشعارات غير المقروءة
    notifications = WorkerNotification.query.filter_by(
        worker_id=worker_id, 
        is_read=False
    ).order_by(WorkerNotification.created_at.desc()).limit(10).all()
    
    # جلب الطلبيات النشطة
    orders = get_worker_orders(worker_id)
    
    # جلب معلومات الراتب
    salary_info = get_worker_salary_info(worker_id)
    
    # جلب حالة الحضور اليوم
    today_session = WorkerSession.query.filter_by(
        worker_id=worker_id,
        date=datetime.utcnow().date()
    ).first()
    
    return render_template('dashboard_worker.html',
                         notifications=notifications,
                         orders=orders,
                         salary_info=salary_info,
                         today_session=today_session,
                         now=datetime.utcnow())

@app.route('/notifications')
def notifications():
    if 'worker_id' not in session:
        return redirect(url_for('login'))
    
    worker_id = session['worker_id']
    notifications_list = WorkerNotification.query.filter_by(
        worker_id=worker_id
    ).order_by(WorkerNotification.created_at.desc()).all()
    
    return render_template('notifications_worker.html', notifications=notifications_list)

@app.route('/notifications/mark-read/<int:notification_id>')
def mark_notification_read(notification_id):
    if 'worker_id' not in session:
        return jsonify({'success': False})
    
    notification = WorkerNotification.query.get_or_404(notification_id)
    if notification.worker_id != session['worker_id']:
        return jsonify({'success': False})
    
    notification.is_read = True
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/orders')
def orders():
    if 'worker_id' not in session:
        return redirect(url_for('login'))
    
    worker_id = session['worker_id']
    orders_list = get_worker_orders(worker_id)
    
    # تحديث تقدم الطلبيات المحلي
    for order in orders_list:
        progress = WorkerOrderProgress.query.filter_by(
            worker_id=worker_id,
            order_id=order['id']
        ).first()
        
        if progress:
            order['progress_percentage'] = progress.progress_percentage
            order['days_remaining'] = progress.days_remaining
            order['local_status'] = progress.status
        else:
            # إنشاء تقدم جديد إذا لم يكن موجوداً
            new_progress = WorkerOrderProgress(
                worker_id=worker_id,
                order_id=order['id'],
                progress_percentage=0,
                days_remaining=order.get('days_remaining', 7),
                expected_completion_date=datetime.utcnow().date() + timedelta(days=order.get('days_remaining', 7))
            )
            db.session.add(new_progress)
            db.session.commit()
    
    db.session.commit()
    
    return render_template('orders_worker.html', orders=orders_list)

@app.route('/orders/complete/<int:order_id>', methods=['POST'])
def complete_order(order_id):
    if 'worker_id' not in session:
        return jsonify({'success': False, 'message': 'غير مصرح'})
    
    worker_id = session['worker_id']
    
    # تحديث حالة الطلبية في مشروع الإدارة
    success = update_order_status(order_id, 'completed', worker_id)
    
    if success:
        # تحديث التقدم المحلي
        progress = WorkerOrderProgress.query.filter_by(
            worker_id=worker_id,
            order_id=order_id
        ).first()
        
        if progress:
            progress.status = 'completed'
            progress.progress_percentage = 100
            progress.actual_completion_date = datetime.utcnow()
        
        # إنشاء إشعار
        notification = WorkerNotification(
            worker_id=worker_id,
            title='تم إنجاز الطلبية',
            message=f'تم تأكيد إنجاز الطلبية #{order_id} بنجاح',
            notification_type='order_completed',
            related_order_id=order_id
        )
        db.session.add(notification)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم إنجاز الطلبية بنجاح'})
    else:
        return jsonify({'success': False, 'message': 'خطأ في تحديث حالة الطلبية'})

@app.route('/salary')
def salary():
    if 'worker_id' not in session:
        return redirect(url_for('login'))
    
    worker_id = session['worker_id']
    salary_info = get_worker_salary_info(worker_id)
    
    # جلب سجل الحضور لهذا الشهر
    current_month = datetime.utcnow().replace(day=1)
    attendance_sessions = WorkerSession.query.filter(
        WorkerSession.worker_id == worker_id,
        WorkerSession.date >= current_month
    ).order_by(WorkerSession.date.desc()).all()
    
    return render_template('salary_worker.html', 
                         salary_info=salary_info,
                         attendance_sessions=attendance_sessions)

@app.route('/attendance/checkin', methods=['POST'])
def attendance_checkin():
    if 'worker_id' not in session:
        return jsonify({'success': False, 'message': 'غير مصرح'})
    
    worker_id = session['worker_id']
    data = request.get_json()
    
    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({'success': False, 'message': 'الموقع مطلوب'})
    
    lat = data['latitude']
    lng = data['longitude']
    
    # التحقق من الموقع
    within_workshop = is_within_workshop(lat, lng)
    
    if not within_workshop:
        return jsonify({'success': False, 'message': 'أنت خارج نطاق الورشة'})
    
    # تسجيل الموقع
    location_log = WorkerLocationLog(
        worker_id=worker_id,
        latitude=lat,
        longitude=lng,
        is_within_workshop=True
    )
    db.session.add(location_log)
    
    # إدارة جلسة العمل
    now = datetime.utcnow()
    today = now.date()
    current_time = now.time()
    
    # البحث عن جلسة اليوم
    session_today = WorkerSession.query.filter_by(
        worker_id=worker_id,
        date=today
    ).first()
    
    if not session_today:
        session_today = WorkerSession(
            worker_id=worker_id,
            date=today,
            location_verified=True
        )
        db.session.add(session_today)
    
    # تحديد نوع التسجيل حسب الوقت
    if current_time < datetime.strptime('12:00', '%H:%M').time():
        if not session_today.check_in_morning:
            session_today.check_in_morning = now
    elif current_time < datetime.strptime('13:00', '%H:%M').time():
        if not session_today.check_out_morning:
            session_today.check_out_morning = now
    elif current_time < datetime.strptime('16:30', '%H:%M').time():
        if not session_today.check_in_afternoon:
            session_today.check_in_afternoon = now
    else:
        if not session_today.check_out_afternoon:
            session_today.check_out_afternoon = now
    
    # حساب ساعات العمل
    calculate_work_hours(session_today)
    
    db.session.commit()
    
    # إرسال بيانات الحضور لمشروع الإدارة
    attendance_data = {
        'date': today.isoformat(),
        'check_in_morning': session_today.check_in_morning.isoformat() if session_today.check_in_morning else None,
        'check_out_morning': session_today.check_out_morning.isoformat() if session_today.check_out_morning else None,
        'check_in_afternoon': session_today.check_in_afternoon.isoformat() if session_today.check_in_afternoon else None,
        'check_out_afternoon': session_today.check_out_afternoon.isoformat() if session_today.check_out_afternoon else None,
        'total_hours': session_today.total_hours,
        'absence_hours': session_today.absence_hours,
        'location_verified': True
    }
    
    record_attendance_to_admin(worker_id, attendance_data)
    
    # إنشاء إشعار
    notification = WorkerNotification(
        worker_id=worker_id,
        title='تم تسجيل الحضور',
        message='تم تسجيل حضورك بنجاح في النظام',
        notification_type='attendance'
    )
    db.session.add(notification)
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': 'تم تسجيل الحضور بنجاح',
        'session': {
            'check_in_morning': session_today.check_in_morning.isoformat() if session_today.check_in_morning else None,
            'check_out_morning': session_today.check_out_morning.isoformat() if session_today.check_out_morning else None,
            'check_in_afternoon': session_today.check_in_afternoon.isoformat() if session_today.check_in_afternoon else None,
            'check_out_afternoon': session_today.check_out_afternoon.isoformat() if session_today.check_out_afternoon else None
        }
    })

def calculate_work_hours(session):
    """حساب ساعات العمل والغياب"""
    total_hours = 0.0
    absence_hours = 0.0
    
    # الصباح: 8:00 - 12:00
    if session.check_in_morning and session.check_out_morning:
        morning_hours = (session.check_out_morning - session.check_in_morning).total_seconds() / 3600
        total_hours += morning_hours
    elif session.check_in_morning:
        # إذا سجل الحضور فقط
        end_morning = datetime.combine(session.date, datetime.strptime('12:00', '%H:%M').time())
        morning_hours = (end_morning - session.check_in_morning).total_seconds() / 3600
        total_hours += morning_hours
        absence_hours += 0.5  # نصف يوم غياب
    else:
        absence_hours += 0.5  # غياب صباحي كامل
    
    # المساء: 13:00 - 16:30
    if session.check_in_afternoon and session.check_out_afternoon:
        afternoon_hours = (session.check_out_afternoon - session.check_in_afternoon).total_seconds() / 3600
        total_hours += afternoon_hours
    elif session.check_in_afternoon:
        # إذا سجل الحضور فقط
        end_afternoon = datetime.combine(session.date, datetime.strptime('16:30', '%H:%M').time())
        afternoon_hours = (end_afternoon - session.check_in_afternoon).total_seconds() / 3600
        total_hours += afternoon_hours
        absence_hours += 0.5  # نصف يوم غياب
    else:
        absence_hours += 0.5  # غياب مسائي كامل
    
    session.total_hours = total_hours
    session.absence_hours = absence_hours

@app.route('/orders/update-progress/<int:order_id>', methods=['POST'])
def update_order_progress(order_id):
    if 'worker_id' not in session:
        return jsonify({'success': False})
    
    worker_id = session['worker_id']
    data = request.get_json()
    progress_percentage = data.get('progress', 0)
    
    progress = WorkerOrderProgress.query.filter_by(
        worker_id=worker_id,
        order_id=order_id
    ).first()
    
    if progress:
        progress.progress_percentage = progress_percentage
        progress.updated_at = datetime.utcnow()
        
        # حساب الأيام المتبقية تلقائياً
        if progress.expected_completion_date:
            days_remaining = (progress.expected_completion_date - datetime.utcnow().date()).days
            progress.days_remaining = max(0, days_remaining)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم تحديث التقدم'})
    
    return jsonify({'success': False, 'message': 'لم يتم العثور على الطلبية'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5001)