/**
 * Voice Output System - FIXED & TESTED
 * Software jo bolta hai
 */

class VoiceOutput {
    constructor() {
        this.synth = window.speechSynthesis;
        this.enabled = localStorage.getItem('voice_output_enabled') === 'true';
        this.voice = null;
        this.voicesReady = false;
        
        if (!this.synth) {
            console.error('❌ Speech Synthesis not supported in this browser');
            return;
        }
        
        console.log('🎤 Initializing VoiceOutput...');
        console.log('   Enabled (from localStorage):', this.enabled);
        
        this.loadVoices();
        
        // ✅ Listen for voices loaded event
        if (this.synth.onvoiceschanged !== undefined) {
            this.synth.onvoiceschanged = () => {
                console.log('🔔 onvoiceschanged fired');
                this.loadVoices();
            };
        }
        
        // ✅ Fallback: Retry loading voices after 500ms & 1500ms
        setTimeout(() => this.loadVoices(), 500);
        setTimeout(() => this.loadVoices(), 1500);
    }
    
    loadVoices() {
        if (!this.synth) return;
        
        const voices = this.synth.getVoices();
        
        if (voices.length === 0) {
            console.warn('⚠️ No voices available yet...');
            return;
        }
        
        // ✅ Priority order for best voice
        this.voice = 
            voices.find(v => v.lang === 'en-IN' && v.name.includes('Female')) ||
            voices.find(v => v.lang === 'en-IN') ||
            voices.find(v => v.lang === 'en-US' && v.name.includes('Google')) ||
            voices.find(v => v.lang === 'en-US') ||
            voices.find(v => v.lang === 'en-GB') ||
            voices.find(v => v.lang.startsWith('en')) ||
            voices[0];
        
        this.voicesReady = true;
        
        console.log('✅ Voice loaded successfully');
        console.log('   Name:', this.voice?.name);
        console.log('   Lang:', this.voice?.lang);
        console.log('   Total voices:', voices.length);
    }
    
    speak(text, options = {}) {
        // ✅ Check 1: Synthesis available?
        if (!this.synth) {
            console.warn('❌ Speech Synthesis not available');
            return false;
        }
        
        // ✅ Check 2: Enabled?
        if (!this.enabled) {
            console.log('🔇 Voice disabled - skipping speech');
            return false;
        }
        
        // ✅ Check 3: Voices loaded?
        if (!this.voicesReady) {
            console.warn('⚠️ Voices not ready yet - retrying in 300ms');
            setTimeout(() => this.speak(text, options), 300);
            return false;
        }
        
        // ✅ Cancel any ongoing speech
        try {
            this.synth.cancel();
        } catch (e) {
            console.warn('Cancel error:', e);
        }
        
        // ✅ Clean text
        const cleanText = this.cleanText(text);
        
        if (!cleanText) {
            console.log('⚠️ Empty text after cleaning');
            return false;
        }
        
        // ✅ Create utterance
        const utterance = new SpeechSynthesisUtterance(cleanText);
        
        // ✅ Set voice (CRITICAL!)
        if (this.voice) {
            utterance.voice = this.voice;
            utterance.lang = this.voice.lang;  // ✅ Match voice lang
        } else {
            utterance.lang = 'en-US';
        }
        
        // ✅ Voice settings
        utterance.rate = options.rate || 1.0;
        utterance.pitch = options.pitch || 1.0;
        utterance.volume = options.volume || 1.0;
        
        // ✅ Event handlers
        utterance.onstart = () => {
            console.log('▶️ Speech started:', cleanText.substring(0, 40) + '...');
        };
        
        utterance.onend = () => {
            console.log('⏹️ Speech ended');
            if (options.onEnd) options.onEnd();
        };
        
        utterance.onerror = (event) => {
            console.error('❌ Speech error:', event.error);
        };
        
        // ✅ Speak!
        try {
            this.synth.speak(utterance);
            console.log('🔊 Speaking:', cleanText.substring(0, 60) + '...');
            return true;
        } catch (e) {
            console.error('❌ Failed to speak:', e);
            return false;
        }
    }
    
    cleanText(text) {
        if (!text || typeof text !== 'string') return '';
        
        return text
            // Remove markdown
            .replace(/[*#_`]/g, '')
            // Remove bullets and boxes
            .replace(/[-•◆▶├└─━│]/g, '')
            // Remove emojis (comprehensive)
            .replace(/[\u{1F300}-\u{1F9FF}]/gu, '')
            .replace(/[\u{2600}-\u{26FF}]/gu, '')
            .replace(/[\u{2700}-\u{27BF}]/gu, '')
            .replace(/[\u{1F000}-\u{1F02F}]/gu, '')
            // Replace newlines with periods (pause)
            .replace(/\n+/g, '. ')
            // Remove extra spaces
            .replace(/\s+/g, ' ')
            // Trim
            .trim()
            // Limit length
            .substring(0, 500);
    }
    
    stop() {
        if (this.synth) {
            this.synth.cancel();
            console.log('⏹️ Speech stopped');
        }
    }
    
    enable() {
        this.enabled = true;
        localStorage.setItem('voice_output_enabled', 'true');
        console.log('🔊 Voice output ENABLED');
        
        // ✅ Wait a moment for settings to apply, then speak
        setTimeout(() => {
            this.speak('Voice output enabled');
        }, 200);
    }
    
    disable() {
        this.enabled = false;
        localStorage.setItem('voice_output_enabled', 'false');
        this.stop();
        console.log('🔇 Voice output DISABLED');
    }
    
    toggle() {
        if (this.enabled) {
            this.disable();
        } else {
            this.enable();
        }
        return this.enabled;
    }
    
    // ✅ Test method - Run from console
    test() {
        console.log('═══════════════════════════════');
        console.log('🧪 VOICE OUTPUT TEST');
        console.log('═══════════════════════════════');
        console.log('Synthesis supported:', !!this.synth);
        console.log('Enabled:', this.enabled);
        console.log('Voices ready:', this.voicesReady);
        console.log('Current voice:', this.voice?.name);
        console.log('Voice lang:', this.voice?.lang);
        console.log('Total voices:', this.synth?.getVoices().length || 0);
        console.log('═══════════════════════════════');
        
        if (!this.enabled) {
            console.log('⚠️ Enabling voice for test...');
            this.enabled = true;
        }
        
        this.speak('Testing voice output. If you can hear this, it is working perfectly.');
    }
}

// ✅ Global instance
window.voiceOutput = new VoiceOutput();

// ✅ Log status on page load
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(() => {
        console.log('═══════════════════════════════');
        console.log('✅ VoiceOutput Initialized');
        console.log('   Enabled:', window.voiceOutput.enabled);
        console.log('   Voices available:', window.voiceOutput.synth?.getVoices().length || 0);
        console.log('   Active voice:', window.voiceOutput.voice?.name || 'None');
        console.log('═══════════════════════════════');
    }, 1000);
});