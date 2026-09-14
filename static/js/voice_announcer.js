/**
 * Voice Announcer System
 * System khud bol kar events batayega
 */

class VoiceAnnouncer {
    constructor() {
        this.synth = window.speechSynthesis;
        this.enabled = localStorage.getItem('voice_announcer_enabled') !== 'false';
        this.volume = parseFloat(localStorage.getItem('voice_announcer_volume') || '0.8');
        this.queue = [];
        this.isSpeaking = false;
        this.voice = null;
        
        // Rate aur pitch
        this.rate = parseFloat(localStorage.getItem('voice_announcer_rate') || '0.95');
        this.pitch = parseFloat(localStorage.getItem('voice_announcer_pitch') || '1.0');
        
        // Priority levels
        this.PRIORITIES = {
            critical: 3,
            high: 2,
            medium: 1,
            low: 0
        };
        
        if (this.synth) {
            this.loadVoices();
            this.synth.onvoiceschanged = () => this.loadVoices();
        }
        
        console.log('🔊 Voice Announcer initialized');
        console.log('   Enabled:', this.enabled);
    }
    
    loadVoices() {
        const voices = this.synth.getVoices();
        if (voices.length === 0) return;
        
        // Best voice choose karo
        this.voice = 
            voices.find(v => v.lang === 'en-IN' && v.name.includes('Female')) ||
            voices.find(v => v.lang === 'en-IN') ||
            voices.find(v => v.lang === 'en-US') ||
            voices.find(v => v.lang.startsWith('en')) ||
            voices[0];
        
        console.log('🔊 Voice loaded:', this.voice?.name);
    }
    
    /**
     * Main method - Announce karo
     */
    announce(message, options = {}) {
        if (!this.enabled || !this.synth) {
            console.log('🔇 Voice announcer disabled');
            return false;
        }
        
        const priority = options.priority || 'medium';
        const type = options.type || 'info';
        const prefix = this.getPrefix(type);
        
        const fullMessage = prefix + message;
        
        // Queue mein add karo
        this.queue.push({
            message: fullMessage,
            priority: this.PRIORITIES[priority] || 1,
            timestamp: Date.now()
        });
        
        // Queue sort by priority
        this.queue.sort((a, b) => b.priority - a.priority);
        
        // Process karo
        this.processQueue();
        
        return true;
    }
    
    getPrefix(type) {
        const prefixes = {
            sale: '💰 ',
            payment: '✅ ',
            stock: '📦 ',
            warning: '⚠️ ',
            danger: '🚨 ',
            success: '🎉 ',
            info: '',
            alert: '🔔 ',
            login: '👋 ',
            logout: '👋 ',
            whatsapp: '📱 ',
            emi: '📅 ',
            target: '🎯 '
        };
        return prefixes[type] || '';
    }
    
    processQueue() {
        if (this.isSpeaking || this.queue.length === 0) return;
        
        const item = this.queue.shift();
        this.speak(item.message);
    }
    
    speak(text) {
        if (!this.synth) return;
        
        try {
            this.synth.cancel();
        } catch(e) {}
        
        // Clean text
        const cleanText = this.cleanText(text);
        if (!cleanText) return;
        
        const utterance = new SpeechSynthesisUtterance(cleanText);
        
        if (this.voice) {
            utterance.voice = this.voice;
            utterance.lang = this.voice.lang;
        } else {
            utterance.lang = 'en-US';
        }
        
        utterance.rate = this.rate;
        utterance.pitch = this.pitch;
        utterance.volume = this.volume;
        
        utterance.onstart = () => {
            this.isSpeaking = true;
            console.log('🔊 Announcing:', cleanText);
        };
        
        utterance.onend = () => {
            this.isSpeaking = false;
            // Next item in queue
            setTimeout(() => this.processQueue(), 300);
        };
        
        utterance.onerror = (e) => {
            this.isSpeaking = false;
            console.error('❌ Announce error:', e.error);
        };
        
        // Android fix
        if (/Android/i.test(navigator.userAgent)) {
            this.synth.cancel();
            this.synth.resume();
        }
        
        this.synth.speak(utterance);
    }
    
    cleanText(text) {
        if (!text) return '';
        return text
            .replace(/[*#_`]/g, '')
            .replace(/[-•◆▶├└─━│]/g, '')
            .replace(/[\u{1F300}-\u{1F9FF}]/gu, '')
            .replace(/[\u{2600}-\u{26FF}]/gu, '')
            .replace(/\n+/g, '. ')
            .replace(/\s+/g, ' ')
            .trim()
            .substring(0, 400);
    }
    
    /**
     * Enable/Disable
     */
    enable() {
        this.enabled = true;
        localStorage.setItem('voice_announcer_enabled', 'true');
        console.log('🔊 Voice announcer ENABLED');
        this.speak('Voice announcements enabled');
    }
    
    disable() {
        this.enabled = false;
        localStorage.setItem('voice_announcer_enabled', 'false');
        this.stop();
        console.log('🔇 Voice announcer DISABLED');
    }
    
    toggle() {
        if (this.enabled) this.disable();
        else this.enable();
        return this.enabled;
    }
    
    stop() {
        if (this.synth) this.synth.cancel();
        this.isSpeaking = false;
        this.queue = [];
    }
    
    setVolume(value) {
        this.volume = Math.max(0, Math.min(1, value));
        localStorage.setItem('voice_announcer_volume', this.volume.toString());
    }
    
    setRate(value) {
        this.rate = Math.max(0.5, Math.min(2, value));
        localStorage.setItem('voice_announcer_rate', this.rate.toString());
    }
    
    setPitch(value) {
        this.pitch = Math.max(0.5, Math.min(2, value));
        localStorage.setItem('voice_announcer_pitch', this.pitch.toString());
    }
    
    /**
     * Shortcut methods
     */
    announceSale(billNo, amount, customer) {
        this.announce(
            `New sale ${billNo}. Amount rupees ${this.formatAmount(amount)}. Customer ${customer}`,
            { type: 'sale', priority: 'medium' }
        );
    }
    
    announcePayment(amount, fromWhom) {
        this.announce(
            `Payment received. Rupees ${this.formatAmount(amount)} from ${fromWhom}`,
            { type: 'payment', priority: 'high' }
        );
    }
    
    announceLowStock(productName, units) {
        this.announce(
            `Warning. Low stock alert. ${productName} has only ${units} units left`,
            { type: 'warning', priority: 'high' }
        );
    }
    
    announceOverdue(count) {
        this.announce(
            `Alert. ${count} tasks are overdue. Please check your dashboard`,
            { type: 'danger', priority: 'critical' }
        );
    }
    
    announceEMIDue(customerName, amount) {
        this.announce(
            `Reminder. EMI payment due. ${customerName} owes rupees ${this.formatAmount(amount)}`,
            { type: 'emi', priority: 'medium' }
        );
    }
    
    announceTargetAchieved(targetName) {
        this.announce(
            `Congratulations. ${targetName} target achieved`,
            { type: 'success', priority: 'high' }
        );
    }
    
    announceLogin(userName) {
        this.announce(
            `Welcome back ${userName}`,
            { type: 'login', priority: 'low' }
        );
    }
    
    announceWhatsApp(count) {
        this.announce(
            `You have ${count} new WhatsApp messages`,
            { type: 'whatsapp', priority: 'medium' }
        );
    }
    
    announceCashLow(balance) {
        this.announce(
            `Warning. Cash balance is low. Available rupees ${this.formatAmount(balance)}`,
            { type: 'warning', priority: 'high' }
        );
    }
    
    formatAmount(amount) {
        // Convert number to readable format
        const num = parseFloat(amount);
        if (isNaN(num)) return amount;
        
        if (num >= 10000000) {
            return `${(num / 10000000).toFixed(2)} crore`;
        } else if (num >= 100000) {
            return `${(num / 100000).toFixed(2)} lakh`;
        } else if (num >= 1000) {
            return `${(num / 1000).toFixed(2)} thousand`;
        }
        return num.toFixed(0);
    }
    
    /**
     * Test karo
     */
    test() {
        console.log('🧪 Testing voice announcer...');
        this.announce('This is a test announcement from your ERP system', { priority: 'medium' });
    }
}

// Global instance
window.voiceAnnouncer = new VoiceAnnouncer();