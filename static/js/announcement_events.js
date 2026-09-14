/**
 * Announcement Events
 * Different events ko detect karke announce karo
 */

(function() {
    'use strict';
    
    console.log('📢 Announcement events initializing...');
    
    // ============================================
    // 1. ON PAGE LOAD - Welcome Message
    // ============================================
    document.addEventListener('DOMContentLoaded', function() {
        // Only on dashboard
        const isDashboard = window.location.pathname === '/' || 
                           window.location.pathname === '/dashboard/';
        
        if (isDashboard && window.ERP_USER_NAME && window.voiceAnnouncer) {
            setTimeout(() => {
                window.voiceAnnouncer.announceLogin(window.ERP_USER_NAME);
            }, 2000);
        }
        
        // ============================================
        // 2. AUTO CHECK FOR ALERTS (Every 60 sec)
        // ============================================
        setTimeout(() => {
            checkAndAnnounceAlerts();
        }, 5000);
        
        setInterval(() => {
            checkAndAnnounceAlerts();
        }, 60000); // 1 minute
    });
    
    // ============================================
    // CHECK FOR ALERTS
    // ============================================
    async function checkAndAnnounceAlerts() {
        if (!window.voiceAnnouncer || !window.voiceAnnouncer.enabled) return;
        
        try {
            // Get alerts from backend
            const response = await fetch('/api/announce-alerts/', {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                }
            });
            
            if (!response.ok) return;
            
            const data = await response.json();
            
            if (data.success && data.alerts && data.alerts.length > 0) {
                // Check which alerts we've already announced
                const announcedAlerts = JSON.parse(
                    localStorage.getItem('announced_alerts') || '[]'
                );
                
                data.alerts.forEach(alert => {
                    const alertKey = alert.id + '_' + alert.type;
                    
                    // Only announce new alerts
                    if (!announcedAlerts.includes(alertKey)) {
                        announceAlert(alert);
                        
                        // Mark as announced
                        announcedAlerts.push(alertKey);
                    }
                });
                
                // Keep only last 50 announced
                const trimmedAlerts = announcedAlerts.slice(-50);
                localStorage.setItem('announced_alerts', JSON.stringify(trimmedAlerts));
            }
        } catch (error) {
            console.error('Alert check error:', error);
        }
    }
    
    function announceAlert(alert) {
        if (!window.voiceAnnouncer) return;
        
        switch (alert.type) {
            case 'low_stock':
                window.voiceAnnouncer.announceLowStock(alert.product_name, alert.units);
                break;
            
            case 'overdue_task':
                window.voiceAnnouncer.announceOverdue(alert.count);
                break;
            
            case 'emi_due':
                window.voiceAnnouncer.announceEMIDue(alert.customer_name, alert.amount);
                break;
            
            case 'cash_low':
                window.voiceAnnouncer.announceCashLow(alert.balance);
                break;
            
            case 'whatsapp':
                window.voiceAnnouncer.announceWhatsApp(alert.count);
                break;
            
            case 'target_achieved':
                window.voiceAnnouncer.announceTargetAchieved(alert.target_name);
                break;
            
            default:
                window.voiceAnnouncer.announce(alert.message, {
                    type: alert.severity || 'info',
                    priority: alert.priority || 'medium'
                });
        }
    }
    
    // ============================================
    // SALE CREATED - Announce
    // ============================================
    window.announceSale = function(billNo, amount, customer) {
        if (window.voiceAnnouncer) {
            window.voiceAnnouncer.announceSale(billNo, amount, customer);
        }
    };
    
    // ============================================
    // PAYMENT RECEIVED - Announce
    // ============================================
    window.announcePayment = function(amount, fromWhom) {
        if (window.voiceAnnouncer) {
            window.voiceAnnouncer.announcePayment(amount, fromWhom);
        }
    };
    
    // ============================================
    // BUTTON TO TOGGLE ANNOUNCEMENTS
    // ============================================
    document.addEventListener('DOMContentLoaded', function() {
        // Add announcement toggle to topbar (optional)
        const topbar = document.querySelector('.user-menu');
        
        if (topbar && window.voiceAnnouncer) {
            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'announcement-toggle-btn';
            toggleBtn.innerHTML = window.voiceAnnouncer.enabled ? '🔊' : '🔇';
            toggleBtn.title = 'Voice Announcements';
            toggleBtn.style.cssText = `
                background: transparent;
                border: none;
                font-size: 1.3rem;
                cursor: pointer;
                padding: 5px;
                transition: transform 0.2s;
            `;
            
            toggleBtn.addEventListener('click', function() {
                const enabled = window.voiceAnnouncer.toggle();
                this.innerHTML = enabled ? '🔊' : '🔇';
                
                if (typeof showToast === 'function') {
                    showToast(
                        enabled ? '🔊 Announcements ON' : '🔇 Announcements OFF',
                        enabled ? 'success' : 'info'
                    );
                }
            });
            
            // Insert before notification bell
            const notificationBell = topbar.querySelector('.notification-bell');
            if (notificationBell) {
                notificationBell.parentElement.before(toggleBtn);
            } else {
                topbar.appendChild(toggleBtn);
            }
        }
    });
    
    console.log('✅ Announcement events loaded');
})();