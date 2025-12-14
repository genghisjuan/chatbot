/**
 * JUNA Mobile - Chat Client
 * Phase 2: Full chat functionality with streaming
 */

class MobileChat {
    constructor() {
        this.conversationHistory = [];
        this.isGenerating = false;
        this.abortController = null;
        this.shouldStopStreaming = false; // Flag to break stream loop

        // Language and TTS state (ported from desktop)
        this.selectedLanguage = 'en-US'; // Default
        this.isMuted = true; // Default muted (desktop default)

        // Voice recognition state (ported from desktop)
        this.recognition = null;
        this.isListening = false;

        // Image upload state
        this.selectedFile = null;

        // DOM Elements
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.imagePreview = document.getElementById('mobileImagePreview');
        this.previewImg = document.getElementById('mobilePreviewImg');
        this.imageName = document.getElementById('mobileImageName');

        this.init();
    }

    init() {
        console.log('JUNA Mobile Chat initialized');

        // Load TTS voices (matching desktop)
        this.loadTTSVoices();

        // Setup voice recognition (desktop parity)
        this.setupVoiceRecognition();

        // Unified send/stop button click handler
        this.sendBtn.addEventListener('click', () => {
            if (this.isGenerating) {
                this.handleStop();
            } else {
                this.handleSend();
            }
        });

        // Enter key to send
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSend();
            }
        });

        // Microphone button (desktop parity)
        document.getElementById('micBtn')?.addEventListener('click', () => {
            this.toggleVoice();
        });

        // Menu button (hamburger) - no-op for now (no drawer implemented)
        document.getElementById('menuBtn')?.addEventListener('click', () => {
            // Placeholder for future menu/drawer functionality
            console.log('Menu button clicked');
        });

        // Setup action menu and handlers
        this.setupMenuListeners();
    }

    handleStop() {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
        // Cancel any ongoing speech (matching desktop)
        if (window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }
        this.isGenerating = false;
        this.toggleInputState(false);
        this.typingIndicator.style.display = 'none';
    }

    async handleSend() {
        const text = this.messageInput.value.trim();

        // Prevent empty sends or double-sends
        if (!text || this.isGenerating) return;

        // Clear input immediately
        this.messageInput.value = '';

        // Render user message
        this.addUserMessage(text, this.selectedFile);

        // Update conversation history
        this.conversationHistory.push({ role: "user", content: text });

        // Disable input during generation
        this.toggleInputState(true);

        // Show typing indicator
        this.typingIndicator.style.display = 'block';
        this.scrollToBottom();

        try {
            await this.sendMessage(text);
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Chat error:', error);
                this.addErrorMessage('Error connecting toserver. Please try again.');
            }
        } finally {
            // Re-enable input
            this.toggleInputState(false);
            this.typingIndicator.style.display = 'none';
            this.messageInput.focus();

            // Clear image after sending
            if (this.selectedFile) {
                this.clearImagePreview();
            }
        }
    }

    setupMenuListeners() {
        // Open main action menu
        document.getElementById('actionBtn').addEventListener('click', () => {
            document.getElementById('actionMenu').classList.add('show');
        });

        // Close main action menu
        document.querySelector('#actionMenu .menu-close').addEventListener('click', () => {
            this.closeActionMenu();
        });
        document.querySelector('#actionMenu .menu-backdrop').addEventListener('click', () => {
            this.closeActionMenu();
        });

        // Language menu item
        document.getElementById('menuLanguage').addEventListener('click', () => {
            this.openLanguageMenu();
        });

        // TTS toggle (ported from desktop)
        document.getElementById('menuTTS').addEventListener('click', () => {
            this.toggleMute();
        });

        // Upload file - wire change event (desktop pattern)
        document.getElementById('mobileImageInput').addEventListener('change', (e) => {
            this.handleImageSelect(e);
        });
        document.getElementById('menuUpload').addEventListener('click', () => {
            document.getElementById('mobileImageInput').click();
            // Don't close menu - wait for file selection
        });

        // Remove image button
        document.getElementById('removeImageBtn').addEventListener('click', () => {
            this.clearImagePreview();
        });

        // Support modal - Close Actions sheet first (desktop parity)
        document.getElementById('menuSupport').addEventListener('click', () => {
            // Close Actions sheet before opening modal
            this.closeActionMenu();

            // Wait for close animation (scaleIn is 0.15s), then open modal
            setTimeout(() => {
                this.toggleSupportModal();
            }, 150);
        });

        // Language sub-menu
        document.querySelector('#languageMenu .back-btn').addEventListener('click', () => {
            this.closeLanguageMenu();
        });
        document.querySelector('#languageMenu .menu-backdrop').addEventListener('click', () => {
            this.closeLanguageMenu();
        });

        // Language options
        document.querySelectorAll('.lang-option').forEach(option => {
            option.addEventListener('click', () => {
                this.selectLanguage(option.dataset.lang);
            });
        });

        // Support modal close
        document.querySelector('#mobileSupportModal .modal-close').addEventListener('click', () => {
            this.closeSupportModal();
        });
        document.querySelector('#mobileSupportModal .modal-backdrop').addEventListener('click', () => {
            this.closeSupportModal();
        });

        // Support options (ported from desktop pattern)
        document.getElementById('emailSupport').addEventListener('click', () => {
            this.selectSupportOption('email');
        });
        document.getElementById('callSupport').addEventListener('click', () => {
            this.selectSupportOption('call');
        });

        // Wire email submit button
        const submitBtn = document.getElementById('submitEmailBtn');
        if (submitBtn) {
            submitBtn.addEventListener('click', () => {
                this.submitSupportRequest();
            });
        }

        // Wire call button
        const callBtn = document.getElementById('callNowBtn');
        if (callBtn) {
            callBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.startInboundCall();
            });
        }

        // Success modal close
        document.getElementById('closeSuccessBtn').addEventListener('click', () => {
            this.closeSuccessModal();
        });
        document.querySelector('#mobileSuccessModal .modal-backdrop').addEventListener('click', () => {
            this.closeSuccessModal();
        });
    }

    closeActionMenu() {
        document.getElementById('actionMenu').classList.remove('show');
    }

    openLanguageMenu() {
        this.closeActionMenu();
        document.getElementById('languageMenu').classList.add('show');
        this.updateLanguageSelection();
    }

    closeLanguageMenu() {
        document.getElementById('languageMenu').classList.remove('show');
    }

    selectLanguage(lang) {
        this.selectedLanguage = lang;

        // Update display - complete language mapping (desktop parity)
        const langNames = {
            'en-US': 'English',
            'es-ES': 'Spanish',
            'fr-FR': 'French',
            'de-DE': 'German',
            'zh-CN': 'Chinese',
            'ko-KR': 'Korean',
            'ja-JP': 'Japanese',
            'pt-BR': 'Portuguese',
            'it-IT': 'Italian',
            'ru-RU': 'Russian',
            'ar-SA': 'Arabic',
            'hi-IN': 'Hindi',
            'vi-VN': 'Vietnamese',
            'pl-PL': 'Polish',
            'nl-NL': 'Dutch'
        };
        document.getElementById('currentLang').textContent = langNames[lang] || lang;

        this.updateLanguageSelection();
        this.closeLanguageMenu(); // Close language sub-menu
        // Main menu stays open (desktop parity)
    }

    updateLanguageSelection() {
        // Update checkmarks
        document.querySelectorAll('.lang-option').forEach(option => {
            if (option.dataset.lang === this.selectedLanguage) {
                option.classList.add('active');
            } else {
                option.classList.remove('active');
            }
        });
    }

    // TTS Toggle - Ported from desktop app.js line 905-914
    toggleMute() {
        this.isMuted = !this.isMuted;
        const label = document.getElementById('ttsLabel');
        const icon = document.getElementById('ttsIcon');

        if (this.isMuted) {
            label.textContent = 'Unmute TTS';
            icon.className = 'fas fa-volume-mute';
            icon.style.color = '#e53e3e';
            if (window.speechSynthesis) window.speechSynthesis.cancel();
        } else {
            label.textContent = 'Mute TTS';
            icon.className = 'fas fa-volume-up';
            icon.style.color = '#48bb78';
        }

        // Menu stays open (desktop parity)
    }

    // TTS Functions - Ported from desktop app.js (lines 849-903)
    speak(text) {
        if (this.isMuted || !window.speechSynthesis) return;

        const utterance = new SpeechSynthesisUtterance(text);

        // Get selected language
        const selectedLang = this.selectedLanguage || 'en-US';

        // Get available voices
        const voices = window.speechSynthesis.getVoices();

        // Find the best voice for the selected language
        // Try to find a voice that matches the exact locale (e.g., es-ES)
        let voice = voices.find(v => v.lang === selectedLang);

        // If no exact match, try to find a voice matching the language code (e.g., es)
        if (!voice) {
            const langCode = selectedLang.split('-')[0];
            voice = voices.find(v => v.lang.startsWith(langCode));
        }

        // If still no match, try to find a voice with similar language in the name
        if (!voice) {
            const langCode = selectedLang.split('-')[0];
            voice = voices.find(v => v.name.toLowerCase().includes(langCode));
        }

        // Set the voice and language
        if (voice) {
            utterance.voice = voice;
        }
        utterance.lang = selectedLang;

        // Adjust speech parameters for better quality
        utterance.rate = 0.9; // Slightly slower for clarity
        utterance.pitch = 1.0;
        utterance.volume = 1.0;

        window.speechSynthesis.speak(utterance);
    }

    loadTTSVoices() {
        // Load voices - they may not be immediately available
        if (window.speechSynthesis) {
            // Trigger voice loading
            window.speechSynthesis.getVoices();

            // Chrome loads voices asynchronously
            if (window.speechSynthesis.onvoiceschanged !== undefined) {
                window.speechSynthesis.onvoiceschanged = () => {
                    window.speechSynthesis.getVoices();
                };
            }
        }
    }

    // Voice Recognition - Ported from desktop app.js (lines 821-847)
    setupVoiceRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            try {
                this.recognition = new SpeechRecognition();
                this.recognition.continuous = false;
                this.recognition.interimResults = false;
                this.recognition.onresult = (event) => {
                    const transcript = event.results[0][0].transcript;
                    this.messageInput.value = transcript;
                    // Desktop auto-sends after transcription
                    this.handleSend();
                };
                this.recognition.onend = () => {
                    this.isListening = false;
                    document.getElementById('micBtn').style.color = '#718096';
                };
            } catch (e) {
                console.warn('Speech recognition not available:', e);
            }
        }
    }

    toggleVoice() {
        if (!this.recognition) {
            alert('Speech recognition not supported on this device');
            return;
        }
        if (this.isListening) {
            this.recognition.stop();
        } else {
            try {
                this.recognition.start();
                this.isListening = true;
                document.getElementById('micBtn').style.color = '#e53e3e';
            } catch (e) {
                console.warn('Failed to start recognition:', e);
                this.isListening = false;
            }
        }
    }

    toggleSupportModal() {
        const modal = document.getElementById('mobileSupportModal');
        const isHidden = !modal.classList.contains('show');

        if (isHidden) {
            // ALWAYS reset to options view when opening
            const options = document.getElementById('mobileSupportOptions');
            const emailForm = document.getElementById('mobileEmailForm');
            const callInfo = document.getElementById('mobileCallInfo');

            // Safety check in case elements are missing
            if (options) options.style.display = 'block';
            if (emailForm) emailForm.style.display = 'none';
            if (callInfo) callInfo.style.display = 'none';

            modal.classList.add('show');
        } else {
            this.closeSupportModal();
        }
    }

    closeSupportModal() {
        document.getElementById('mobileSupportModal').classList.remove('show');
    }

    // Upload handlers - Ported from desktop app.js line 442-475
    handleImageSelect(event) {
        const file = event.target.files[0];
        if (file) {
            this.showImagePreview(file);
            this.closeActionMenu();
        }
    }

    showImagePreview(file) {
        // Port from desktop app.js line 467-475
        this.selectedFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            this.previewImg.src = e.target.result;
            this.imageName.textContent = file.name;
            this.imagePreview.style.display = 'flex';
        };
        reader.readAsDataURL(file);
    }

    clearImagePreview() {
        this.selectedFile = null;
        this.imagePreview.style.display = 'none';
        this.previewImg.src = '';
        this.imageName.textContent = '';
        document.getElementById('mobileImageInput').value = ''; // Reset input
    }

    // Support option selector - Ported from desktop app.js line 756-767
    selectSupportOption(type) {
        const selector = document.getElementById('mobileSupportOptions');
        const emailForm = document.getElementById('mobileEmailForm');
        const callInfo = document.getElementById('mobileCallInfo');

        selector.style.display = 'none';

        if (type === 'email') {
            emailForm.style.display = 'block';
            callInfo.style.display = 'none';
        } else {
            emailForm.style.display = 'none';
            callInfo.style.display = 'block';
        }
    }

    // Email Form Submission - Ported from desktop app.js line 769-806
    async submitSupportRequest() {
        const name = document.getElementById('mobileSupportName').value.trim();
        const email = document.getElementById('mobileSupportEmail').value.trim();
        const summary = document.getElementById('mobileSupportSummary').value.trim();

        if (!name || !email || !summary) {
            alert('Please fill in all fields');
            return;
        }

        // Basic email validation
        if (!email.includes('@')) {
            alert('Please enter a valid email address');
            return;
        }

        try {
            const res = await fetch('/api/v1/support/email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    business: email, // Mobile uses email field for business
                    summary,
                    conversation_history: this.conversationHistory
                })
            });

            if (res.ok) {
                const data = await res.json();
                this.clearEmailForm();
                this.closeSupportModal();
                this.showSuccessModal(data.ticket_id);
            } else {
                const err = await res.json();
                console.error('Support request failed:', err);
                let msg = 'Failed to submit request';
                if (err.detail) {
                    msg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
                }
                alert(`Error: ${msg}`);
            }
        } catch (e) {
            console.error('Support request error:', e);
            alert('Error connecting to support service. Please try again.');
        }
    }

    clearEmailForm() {
        document.getElementById('mobileSupportName').value = '';
        document.getElementById('mobileSupportEmail').value = '';
        document.getElementById('mobileSupportSummary').value = '';
    }

    // Inbound Call - Ported from desktop app.js line 686-720
    async startInboundCall() {
        const btn = document.getElementById('callNowBtn');
        const originalHTML = btn.innerHTML;
        btn.style.pointerEvents = 'none';
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Connecting...</span>';

        try {
            const res = await fetch('/api/v1/support/call-inbound', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone: "Unknown", // Desktop uses this for web callers
                    conversation_history: this.conversationHistory
                })
            });

            if (res.ok) {
                const data = await res.json();
                this.closeSupportModal();
                this.showSuccessModal(data.ticket_id);
                // Wait briefly then try to call
                setTimeout(() => {
                    window.location.href = 'tel:+15551234567';
                }, 1500);
            } else {
                const err = await res.json();
                console.error('Inbound call failed:', err);
                alert(`Error: ${err.detail || 'Failed to initiate call ticket'}`);
            }
        } catch (e) {
            console.error('Call error:', e);
            alert('Error initiating call connection.');
        } finally {
            btn.style.pointerEvents = '';
            btn.innerHTML = originalHTML;
        }
    }

    async sendMessage(text) {
        // Build FormData payload (matching desktop)
        const formData = new FormData();
        formData.append('user_message', text);
        formData.append('conversation_history', JSON.stringify(this.conversationHistory));
        formData.append('language', this.selectedLanguage); // Use selected language

        // Append file if selected
        if (this.selectedFile) {
            formData.append('file', this.selectedFile);
        }

        // Setup abort controller
        this.abortController = new AbortController();
        this.isGenerating = true;

        // API call
        const response = await fetch('/api/v1/chat', {
            method: 'POST',
            body: formData,
            signal: this.abortController.signal
        });

        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        // Handle streaming response
        await this.handleStream(response);

        this.isGenerating = false;
        this.abortController = null;
    }

    async handleStream(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        // Create bot message bubble
        const botElement = this.addBotMessage();
        let botText = '';

        // Read stream chunks
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            botText += chunk;

            // Strip suggestions marker (desktop does this)
            let displayText = botText.replace(/<<SUGGESTIONS>>.*$/s, '').trim();
            displayText = displayText.replace(/<<>.*$/s, '').trim();

            // Update bot message (plain text for Phase 2, no markdown yet)
            botElement.textContent = displayText;
            this.scrollToBottom();
        }

        // Clean final text
        const cleanBotText = botText.replace(/<<SUGGESTIONS>>.*$/s, '').trim();

        // Update conversation history
        this.conversationHistory.push({ role: "assistant", content: cleanBotText });

        // Speak (matching desktop timing - after full message)
        if (!this.isMuted) {
            try {
                this.speak(cleanBotText);
            } catch (e) {
                console.warn('TTS Error:', e);
            }
        }
    }

    addUserMessage(text, file = null) {
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper user';

        const message = document.createElement('div');
        message.className = 'message';

        // Add text if exists
        if (text) {
            const textSpan = document.createElement('div');
            textSpan.textContent = text;
            message.appendChild(textSpan);
        }

        // Add image if exists
        if (file) {
            const img = document.createElement('img');
            img.src = URL.createObjectURL(file);
            img.style.maxWidth = '100%';
            img.style.borderRadius = '8px';
            img.style.marginTop = text ? '8px' : '0';
            img.onload = () => this.scrollToBottom();
            message.appendChild(img);
        }

        wrapper.appendChild(message);
        this.chatMessages.appendChild(wrapper);
        this.scrollToBottom();
    }

    addBotMessage() {
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper bot';

        const message = document.createElement('div');
        message.className = 'message';
        message.textContent = ''; // Will be filled by streaming

        wrapper.appendChild(message);
        this.chatMessages.appendChild(wrapper);
        this.scrollToBottom();

        return message; // Return for streaming updates
    }

    addErrorMessage(text) {
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper bot';

        const message = document.createElement('div');
        message.className = 'message error';
        message.textContent = text;

        wrapper.appendChild(message);
        this.chatMessages.appendChild(wrapper);
        this.scrollToBottom();
    }

    toggleInputState(disabled) {
        this.messageInput.disabled = disabled;
        this.sendBtn.disabled = disabled;

        if (disabled) {
            this.messageInput.parentElement.classList.add('disabled');
        } else {
            this.messageInput.parentElement.classList.remove('disabled');
        }
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    showSuccessModal(ticketId = 'N/A') {
        document.getElementById('successTicketId').textContent = '#' + ticketId;
        const modal = document.getElementById('mobileSuccessModal');
        modal.classList.add('show');
    }

    closeSuccessModal() {
        document.getElementById('mobileSuccessModal').classList.remove('show');
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.mobileChat = new MobileChat();
});
