from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json

db = SQLAlchemy()

class WorkerSession(db.Model):
    __tablename__ = 'worker_session'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow().date())
    check_in_morning = db.Column(db.DateTime)
    check_out_morning = db.Column(db.DateTime)
    check_in_afternoon = db.Column(db.DateTime)
    check_out_afternoon = db.Column(db.DateTime)
    total_hours = db.Column(db.Float, default=0.0)
    absence_hours = db.Column(db.Float, default=0.0)
    location_verified = db.Column(db.Boolean, default=False)
    is_travel_assignment = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WorkerNotification(db.Model):
    __tablename__ = 'worker_notification'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50))  # assignment, delay, advance, salary_reminder, etc.
    is_read = db.Column(db.Boolean, default=False)
    related_order_id = db.Column(db.Integer)
    related_amount = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WorkerLocationLog(db.Model):
    __tablename__ = 'worker_location_log'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_within_workshop = db.Column(db.Boolean, default=False)

class WorkerOrderProgress(db.Model):
    __tablename__ = 'worker_order_progress'
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, nullable=False)
    order_id = db.Column(db.Integer, nullable=False)
    progress_percentage = db.Column(db.Integer, default=0)
    days_remaining = db.Column(db.Integer)
    expected_completion_date = db.Column(db.Date)
    actual_completion_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='in_progress')  # in_progress, completed, returned
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)