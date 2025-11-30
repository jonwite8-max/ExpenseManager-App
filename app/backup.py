# backup.py
import sqlite3
import datetime
import os

def backup_database():
    """إنشاء نسخة احتياطية من قاعدة البيانات"""
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup/data_backup_{timestamp}.db"
        
        os.makedirs("backup", exist_ok=True)
        
        # نسخ الملف
        with open('data.db', 'rb') as original:
            with open(backup_file, 'wb') as backup:
                backup.write(original.read())
        
        print(f"✅ تم إنشاء نسخة احتياطية: {backup_file}")
        return True
    except Exception as e:
        print(f"❌ خطأ في النسخ الاحتياطي: {e}")
        return False