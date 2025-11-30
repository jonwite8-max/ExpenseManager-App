// تطبيق العمال - الجافاسكريبت الرئيسي
class WorkerApp {
    constructor() {
        this.currentLocation = null;
        this.locationWatchId = null;
        this.autoCheckInEnabled = false;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.startLocationTracking();
        this.checkNotifications();
        this.updateCurrentTime();
    }

    setupEventListeners() {
        // تحديث التوقيت الحالي كل دقيقة
        setInterval(() => this.updateCurrentTime(), 60000);
        
        // التحقق من الإشعارات الجديدة كل 30 ثانية
        setInterval(() => this.checkNotifications(), 30000);
        
        // إعداد أزرار التفاعل
        this.setupActionButtons();
    }

    async startLocationTracking() {
        if (!navigator.geolocation) {
            this.showError('المتصفح لا يدخدم خدمة الموقع');
            return;
        }

        this.locationWatchId = navigator.geolocation.watchPosition(
            (position) => {
                this.currentLocation = {
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy
                };
                this.handleLocationUpdate();
            },
            (error) => {
                console.error('خطأ في الموقع:', error);
                this.showError('تعذر الحصول على الموقع');
            },
            {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 60000
            }
        );
    }

    handleLocationUpdate() {
        // التحقق إذا كان العامل خارج نطاق الورشة
        if (this.currentLocation && !this.isWithinWorkshop()) {
            this.showWarning('أنت خارج نطاق الورشة!');
            this.recordAbsence();
        }
    }

    isWithinWorkshop() {
        if (!this.currentLocation) return false;
        
        const workshopLat = 36.7525; // إحداثيات الورشة
        const workshopLng = 3.0420;
        const allowedRadius = 300; // نصف القطر المسموح به بالمتر
        
        const distance = this.calculateDistance(
            this.currentLocation.latitude,
            this.currentLocation.longitude,
            workshopLat,
            workshopLng
        );
        
        return distance <= allowedRadius;
    }

    calculateDistance(lat1, lng1, lat2, lng2) {
        const R = 6371000; // نصف قطر الأرض بالمتر
        const dLat = this.toRad(lat2 - lat1);
        const dLng = this.toRad(lng2 - lng1);
        
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                 Math.cos(this.toRad(lat1)) * Math.cos(this.toRad(lat2)) *
                 Math.sin(dLng/2) * Math.sin(dLng/2);
        
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return R * c;
    }

    toRad(degrees) {
        return degrees * (Math.PI/180);
    }

    async checkIn() {
        if (!this.currentLocation) {
            this.showError('جاري الحصول على الموقع...');
            return;
        }

        try {
            const response = await fetch('/attendance/checkin', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(this.currentLocation)
            });

            const data = await response.json();
            
            if (data.success) {
                this.showSuccess('تم تسجيل الحضور بنجاح');
                this.updateAttendanceDisplay(data.session);
            } else {
                this.showError(data.message);
            }
        } catch (error) {
            this.showError('خطأ في الاتصال بالخادم');
        }
    }

    async updateOrderProgress(orderId, progress) {
        try {
            const response = await fetch(`/orders/update-progress/${orderId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ progress: progress })
            });

            const data = await response.json();
            
            if (data.success) {
                this.showSuccess('تم تحديث تقدم العمل');
                this.updateProgressBar(orderId, progress);
            } else {
                this.showError(data.message);
            }
        } catch (error) {
            this.showError('خطأ في تحديث التقدم');
        }
    }

    async completeOrder(orderId) {
        if (!confirm('هل أنت متأكد من إكمال هذه الطلبية؟')) {
            return;
        }

        try {
            const response = await fetch(`/orders/complete/${orderId}`, {
                method: 'POST'
            });

            const data = await response.json();
            
            if (data.success) {
                this.showSuccess('تم إكمال الطلبية بنجاح');
                setTimeout(() => location.reload(), 1500);
            } else {
                this.showError(data.message);
            }
        } catch (error) {
            this.showError('خطأ في إكمال الطلبية');
        }
    }

    async markNotificationAsRead(notificationId) {
        try {
            const response = await fetch(`/notifications/mark-read/${notificationId}`);
            const data = await response.json();
            
            if (data.success) {
                document.querySelector(`[data-notification="${notificationId}"]`).remove();
                this.updateNotificationCount();
            }
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
    }

    updateProgressBar(orderId, progress) {
        const progressBar = document.querySelector(`[data-order="${orderId}"] .progress-fill`);
        const progressText = document.querySelector(`[data-order="${orderId}"] .progress-text`);
        
        if (progressBar && progressText) {
            progressBar.style.width = `${progress}%`;
            progressBar.className = `progress-fill ${
                progress < 30 ? 'progress-low' :
                progress < 70 ? 'progress-medium' : 'progress-high'
            }`;
            progressText.textContent = `${progress}%`;
        }
    }

    updateAttendanceDisplay(session) {
        // تحديث عرض حالة الحضور
        const attendanceElement = document.getElementById('attendance-status');
        if (attendanceElement && session) {
            let statusHtml = '<div class="space-y-2">';
            
            if (session.check_in_morning) {
                statusHtml += `<div>الحضور الصباحي: ${this.formatTime(session.check_in_morning)}</div>`;
            }
            if (session.check_out_morning) {
                statusHtml += `<div>الانصراف الصباحي: ${this.formatTime(session.check_out_morning)}</div>`;
            }
            if (session.check_in_afternoon) {
                statusHtml += `<div>الحضور المسائي: ${this.formatTime(session.check_in_afternoon)}</div>`;
            }
            if (session.check_out_afternoon) {
                statusHtml += `<div>الانصراف المسائي: ${this.formatTime(session.check_out_afternoon)}</div>`;
            }
            
            statusHtml += '</div>';
            attendanceElement.innerHTML = statusHtml;
        }
    }

    formatTime(dateTimeString) {
        const date = new Date(dateTimeString);
        return date.toLocaleTimeString('ar-EG', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
    }

    updateCurrentTime() {
        const now = new Date();
        const timeElement = document.getElementById('current-time');
        if (timeElement) {
            timeElement.textContent = now.toLocaleTimeString('ar-EG', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        }
        
        const dateElement = document.getElementById('current-date');
        if (dateElement) {
            dateElement.textContent = now.toLocaleDateString('ar-EG', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });
        }
    }

    async checkNotifications() {
        try {
            const response = await fetch('/notifications?unread_only=true');
            const notifications = await response.json();
            
            this.updateNotificationBadge(notifications.length);
            
            // إشعارات push بسيطة
            if (notifications.length > 0) {
                this.showNewNotifications(notifications);
            }
        } catch (error) {
            console.error('Error checking notifications:', error);
        }
    }

    updateNotificationBadge(count) {
        const badge = document.querySelector('.notification-badge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }
        }
    }

    showNewNotifications(notifications) {
        // عرض إشعارات جديدة (يمكن تطويره لإشعارات المتصفح)
        notifications.forEach(notification => {
            this.showToast(notification.title, notification.message);
        });
    }

    showToast(title, message) {
        const toast = document.createElement('div');
        toast.className = 'fixed top-4 left-4 bg-white border-l-4 border-blue-500 shadow-lg rounded-lg p-4 max-w-sm z-50 slide-in';
        toast.innerHTML = `
            <div class="font-semibold text-gray-900">${title}</div>
            <div class="text-sm text-gray-600 mt-1">${message}</div>
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }

    showSuccess(message) {
        this.showToast('✅ نجح', message);
    }

    showError(message) {
        this.showToast('❌ خطأ', message);
    }

    showWarning(message) {
        this.showToast('⚠️ تحذير', message);
    }

    setupActionButtons() {
        // إعداد أزرار تفاعلية
        document.addEventListener('click', (e) => {
            if (e.target.closest('[data-action="checkin"]')) {
                this.checkIn();
            }
            
            if (e.target.closest('[data-action="update-progress"]')) {
                const button = e.target.closest('[data-action="update-progress"]');
                const orderId = button.dataset.orderId;
                const progress = parseInt(button.dataset.progress);
                this.updateOrderProgress(orderId, progress);
            }
            
            if (e.target.closest('[data-action="complete-order"]')) {
                const button = e.target.closest('[data-action="complete-order"]');
                const orderId = button.dataset.orderId;
                this.completeOrder(orderId);
            }
            
            if (e.target.closest('[data-action="mark-read"]')) {
                const button = e.target.closest('[data-action="mark-read"]');
                const notificationId = button.dataset.notificationId;
                this.markNotificationAsRead(notificationId);
            }
        });
    }

    // دالة لبدء التتبع التلقائي للحضور
    enableAutoCheckIn() {
        this.autoCheckInEnabled = true;
        this.showSuccess('تم تفعيل التسجيل التلقائي للحضور');
    }

    // دالة لإيقاف التتبع التلقائي
    disableAutoCheckIn() {
        this.autoCheckInEnabled = false;
        this.showSuccess('تم إيقاف التسجيل التلقائي للحضور');
    }

    recordAbsence() {
        // تسجيل غياب تلقائي عندما يبتعد العامل
        if (this.autoCheckInEnabled) {
            console.log('تم تسجيل غياب تلقائي بسبب الابتعاد عن الورشة');
            // يمكن إضافة طلب API لتسجيل الغياب
        }
    }
}

// تهيئة التطبيق عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    window.workerApp = new WorkerApp();
    
    // خدمة Worker لمعالجة المهام في الخلفية
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js')
            .then(registration => {
                console.log('Service Worker registered successfully');
            })
            .catch(error => {
                console.log('Service Worker registration failed:', error);
            });
    }
});

// دوال مساعدة عالمية
function formatCurrency(amount) {
    return new Intl.NumberFormat('ar-DZ', {
        style: 'currency',
        currency: 'DZD'
    }).format(amount);
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('ar-EG', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

function calculateDaysRemaining(endDate) {
    const end = new Date(endDate);
    const now = new Date();
    const diffTime = end - now;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return Math.max(0, diffDays);
}