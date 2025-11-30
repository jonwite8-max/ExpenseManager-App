import sys
import os

# إضافة المسار الحالي
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from __init__ import create_app

app = create_app()

@app.route("/")
def hello():
    return """
    <h1>✅ التطبيق يعمل بنجاح!</h1>
    <p><a href='/login'>تسجيل الدخول</a></p>
    <p><a href='/dashboard'>لوحة التحكم</a></p>
    """

if __name__ == "__main__":
    print("🚀 جاري التشغيل على http://localhost:5000")
    print("📊 يمكنك الآن زيارة:")
    print("   🔗 http://localhost:5000/")
    print("   🔗 http://localhost:5000/login")
    print("   🔗 http://localhost:5000/dashboard")
    app.run(debug=True, host='0.0.0.0', port=5000)