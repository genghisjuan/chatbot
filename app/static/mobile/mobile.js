/**
 * JUNA Mobile - Chat Client
 * Phase 2: Full chat functionality with streaming
 */

class MobileChat {
    constructor() {
        this.conversationHistory = this.restoreConversation() || [];
        this.isGenerating = false;
        this.abortController = null;
        this.shouldStopStreaming = false; // Flag to break stream loop
        this.hasReceivedAnyTokens = false; // Track if any bot response arrived

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
            console.log('📤 Send button clicked');
            console.log('isGenerating:', this.isGenerating);
            if (this.isGenerating) {
                console.log('🛑 Calling handleStop');
                this.handleStop();
            } else {
                console.log('📨 Calling handleSend');
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

        // Menu button (hamburger) - open drawer
        document.getElementById('menuBtn')?.addEventListener('click', () => {
            this.toggleDrawer();
        });

        // Restore conversation UI if there's an active conversation (desktop parity)
        if (this.conversationHistory.length > 0) {
            this.chatMessages.innerHTML = '';
            this.conversationHistory.forEach(msg => {
                if (msg.role === 'user') {
                    this.addUserMessage(msg.content);
                } else if (msg.role === 'assistant') {
                    this.addBotMessage(msg.content, msg.id);
                }
            });
            this.scrollToBottom();
        }

        // Stop speech on page unload/refresh (desktop parity)
        window.addEventListener('beforeunload', () => {
            if (window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
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

        // SET GENERATION STATE
        this.isGenerating = true;
        console.log('✅ SET isGenerating = true');
        this.hasReceivedAnyTokens = false;  // Reset token tracker
        this.shouldStopStreaming = false;   // Reset stop flag

        // UPDATE BUTTON UI
        this.updateSendButton();

        // Render user message
        this.addUserMessage(text, this.selectedFile);

        // Update conversation history
        this.conversationHistory.push({ role: "user", content: text });

        // Save to sessionStorage (desktop parity)
        this.saveConversation();

        // If this is the first USER message, create conversation in history (desktop parity)
        const currentId = sessionStorage.getItem('current_conversation_id');
        const userMessageCount = this.conversationHistory.filter(m => m.role === 'user').length;
        if (!currentId && userMessageCount === 1) {
            this.saveConversationToHistory(text);
        }

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
                this.addErrorMessage('Network error — please try again.');
            }
            // AbortError = user stopped, no error message needed
        } finally {
            // RESET GENERATION STATE
            this.isGenerating = false;
            console.log('❌ SET isGenerating = false (finally)');
            this.hasReceivedAnyTokens = false;

            // CLEAR ABORT CONTROLLER
            this.abortController = null;

            // UPDATE BUTTON UI
            this.updateSendButton();

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

    updateSendButton() {
        const icon = this.sendBtn.querySelector('i');

        if (this.isGenerating) {
            // Show Stop icon
            icon.className = 'fas fa-stop';
            this.sendBtn.setAttribute('aria-label', 'Stop');
            this.sendBtn.classList.add('stop-mode');
        } else {
            // Show Send icon
            icon.className = 'fas fa-paper-plane';
            this.sendBtn.setAttribute('aria-label', 'Send');
            this.sendBtn.classList.remove('stop-mode');
        }
    }

    handleStop() {
        console.log('🛑 Stop requested by user');

        // Set flag to break stream loop
        this.shouldStopStreaming = true;

        // Abort ongoing request
        if (this.abortController) {
            console.log('🛑 Aborting controller');
            this.abortController.abort();
            // DON'T null it here - let finally block clean up
            // This allows stream loop to check signal.aborted
        }

        // Cancel TTS immediately
        if (window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }

        // If no tokens received, remove the empty bot message bubble
        if (!this.hasReceivedAnyTokens) {
            const botWrappers = document.querySelectorAll('.message-wrapper.bot');
            if (botWrappers.length > 0) {
                const lastBotWrapper = botWrappers[botWrappers.length - 1];
                const message = lastBotWrapper.querySelector('.message');
                if (!message || !message.textContent.trim()) {
                    lastBotWrapper.remove();
                }
            }
        }

        // Reset state
        this.isGenerating = false;
        console.log('❌ SET isGenerating = false (handleStop)');
        this.hasReceivedAnyTokens = false;
        this.shouldStopStreaming = false;

        // Update button UI
        this.updateSendButton();

        // Re-enable input
        this.toggleInputState(false);
        this.typingIndicator.style.display = 'none';
        this.messageInput.focus();
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

        // Setup abort controller (isGenerating already set in handleSend)
        this.abortController = new AbortController();

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
        await this.handleStream(response, text);

        // State cleanup happens in handleSend finally block
    }

    async handleStream(response, text) {
        console.log('🌊 handleStream started');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        // Create bot message bubble (pass text as userQuery context)
        const botElement = this.addBotMessage('', null, text);
        let botText = '';
        let chunkCount = 0;

        // Read stream chunks
        while (true) {


            // CHECK STOP FLAG AND ABORT SIGNAL BEFORE READ
            if (this.shouldStopStreaming || this.abortController?.signal.aborted) {
                console.log('🛑 Stream loop detected stop - breaking');
                console.log('shouldStopStreaming:', this.shouldStopStreaming);
                console.log('signal.aborted:', this.abortController?.signal.aborted);
                try {
                    reader.cancel(); // Cancel the reader
                    console.log('🛑 Reader cancelled successfully');
                } catch (e) {
                    console.log('Reader cancel error:', e);
                }
                break;
            }

            let chunk;
            try {
                const result = await reader.read();
                if (result.done) {
                    console.log(`Stream completed normally - received ${chunkCount} chunks`);
                    break;
                }
                chunk = result.value;
                chunkCount++;
                console.log(`📦 Chunk ${chunkCount} received, size: ${chunk.length} bytes`);
            } catch (error) {
                if (error.name === 'AbortError') {
                    console.log('🛑 Reader.read() aborted by signal');
                    break;
                }
                console.error('Stream read error:', error);
                throw error;
            }

            const chunkText = decoder.decode(chunk, { stream: true });



            botText += chunkText;

            // TRACK TOKEN ARRIVAL
            if (botText.trim().length > 0) {
                this.hasReceivedAnyTokens = true;
            }

            // Strip suggestions marker (desktop does this)
            let displayText = botText.replace(/<<SUGGESTIONS>>.*$/s, '').trim();
            displayText = displayText.replace(/<<>>.*$/s, '').trim();

            // Update bot message with markdown rendering (desktop parity)
            botElement.innerHTML = marked.parse(displayText);
            this.scrollToBottom();
        }

        // Clean final text
        const cleanBotText = botText.replace(/<<SUGGESTIONS>>.*$/s, '').trim();

        // ONLY ADD TO HISTORY IF WE HAVE CONTENT (not stopped before tokens)
        if (cleanBotText.length > 0) {
            // Update conversation history
            this.conversationHistory.push({ role: "assistant", content: cleanBotText });

            // Update dataset for feedback analytics (Desktop Parity)
            const wrapper = botElement.closest('.message-wrapper');
            if (wrapper) {
                // Remove suggestions for analytics purity
                wrapper.dataset.botResponse = cleanBotText;
                wrapper.dataset.userQuery = text || ''; // Ensure context is saved
            }

            // Save updated conversation (desktop parity)
            this.saveConversation();
            this.updateSavedConversation();
        }

        // Speak (matching desktop timing - after full message, only if not stopped and not muted)
        if (!this.isMuted && !this.shouldStopStreaming && cleanBotText.length > 0) {
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

    addBotMessage(content = '', id = null, userQuery = '') {
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper bot';

        const message = document.createElement('div');
        message.className = 'message';

        // Render markdown if content provided (restoration), empty for streaming (desktop parity)
        if (content) {
            message.innerHTML = marked.parse(content);
        } else {
            message.textContent = '';
        }

        // Store message ID (desktop parity)
        const msgId = id || Date.now().toString();
        wrapper.dataset.messageId = msgId;

        // Store context for analytics (Desktop Parity)
        if (content) wrapper.dataset.botResponse = content;

        // If userQuery provided, store it. If not, try to get from history (restoration case)
        if (userQuery) {
            wrapper.dataset.userQuery = userQuery;
        } else {
            const lastUserMsg = this.conversationHistory.filter(m => m.role === 'user').pop();
            if (lastUserMsg) {
                wrapper.dataset.userQuery = lastUserMsg.content;
            }
        }

        wrapper.appendChild(message);

        // Add rating controls (desktop parity)
        const actionsRow = document.createElement('div');
        actionsRow.className = 'actions-row';

        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'feedback-buttons';

        const upBtn = document.createElement('button');
        upBtn.className = 'feedback-btn';
        upBtn.innerHTML = '<i class="fas fa-thumbs-up"></i>';
        upBtn.onclick = () => this.sendFeedback(msgId, 'up', upBtn, downBtn, wrapper);

        const downBtn = document.createElement('button');
        downBtn.className = 'feedback-btn';
        downBtn.innerHTML = '<i class="fas fa-thumbs-down"></i>';
        downBtn.onclick = () => this.sendFeedback(msgId, 'down', downBtn, upBtn, wrapper);

        // Restore previous rating state if it exists (desktop parity)
        const existingRating = this.getRating(msgId);
        if (existingRating === 'up') {
            upBtn.classList.add('active-up');
        } else if (existingRating === 'down') {
            downBtn.classList.add('active-down');
        }

        feedbackDiv.appendChild(upBtn);
        feedbackDiv.appendChild(downBtn);
        actionsRow.appendChild(feedbackDiv);
        wrapper.appendChild(actionsRow);

        this.chatMessages.appendChild(wrapper);
        this.scrollToBottom();

        return message; // Return for streaming updates
    }

    addErrorMessage(text) {
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper bot';

        const message = document.createElement('div');
        message.className = 'message error-message';
        message.style.color = '#e53e3e';
        message.style.borderColor = '#e53e3e';
        message.textContent = text;

        wrapper.appendChild(message);
        this.chatMessages.appendChild(wrapper);
        this.scrollToBottom();
    }

    toggleInputState(disabled) {
        this.messageInput.disabled = disabled;
        // NEVER disable the send button, as it doubles as the Stop button
        this.sendBtn.disabled = false;

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

    // ============================================
    // Conversation Persistence Methods (Desktop Parity)
    // ============================================

    restoreConversation() {
        try {
            const raw = sessionStorage.getItem('current_conversation_history');
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            if (!Array.isArray(parsed)) return [];
            return parsed.filter(item =>
                item &&
                typeof item === 'object' &&
                typeof item.role === 'string' &&
                typeof item.content === 'string'
            );
        } catch (e) {
            console.error("Failed to restore conversation:", e);
            return [];
        }
    }

    saveConversation() {
        sessionStorage.setItem('current_conversation_history', JSON.stringify(this.conversationHistory));
    }

    saveConversationToHistory(firstMessage) {
        const conversations = JSON.parse(localStorage.getItem('conversation_history_list') || '[]');
        const newConv = {
            id: Date.now(),
            firstMessage: firstMessage.substring(0, 50),
            timestamp: new Date().toISOString(),
            history: this.conversationHistory
        };

        conversations.unshift(newConv);
        if (conversations.length > 5) conversations.splice(5);

        localStorage.setItem('conversation_history_list', JSON.stringify(conversations));
        sessionStorage.setItem('current_conversation_id', newConv.id);
    }

    updateSavedConversation() {
        const currentId = sessionStorage.getItem('current_conversation_id');
        if (!currentId) return;

        const conversations = JSON.parse(localStorage.getItem('conversation_history_list') || '[]');
        const index = conversations.findIndex(c => c.id == currentId);

        if (index !== -1) {
            conversations[index].history = this.conversationHistory;
            conversations[index].timestamp = new Date().toISOString();
            localStorage.setItem('conversation_history_list', JSON.stringify(conversations));
        }
    }

    // ============================================
    // Message Rating Methods (Desktop Parity)
    // ============================================

    loadRatings() {
        try {
            const stored = sessionStorage.getItem('message_ratings');
            return stored ? JSON.parse(stored) : {};
        } catch (e) {
            console.error('Failed to load ratings:', e);
            return {};
        }
    }

    saveRating(msgId, rating) {
        const ratings = this.loadRatings();
        ratings[msgId] = rating;
        sessionStorage.setItem('message_ratings', JSON.stringify(ratings));
    }

    getRating(msgId) {
        const ratings = this.loadRatings();
        return ratings[msgId] || null;
    }

    async sendFeedback(msgId, rating, btn, otherBtn, wrapper) {
        // Toggle Logic (exact desktop behavior)
        const isActive = btn.classList.contains('active-up') || btn.classList.contains('active-down');

        let newRating = rating;

        if (isActive) {
            // Toggle Off
            btn.classList.remove('active-up', 'active-down');
            newRating = 'none';

            // Remove from storage
            const ratings = this.loadRatings();
            if (ratings[msgId]) {
                delete ratings[msgId];
                sessionStorage.setItem('message_ratings', JSON.stringify(ratings));
            }
        } else {
            // Toggle On or Switch
            btn.classList.add(rating === 'up' ? 'active-up' : 'active-down');
            otherBtn.classList.remove('active-up', 'active-down');

            // Save new rating
            this.saveRating(msgId, rating);
        }

        try {
            const payload = {
                message_id: msgId,
                rating: newRating,
                user_query: wrapper.dataset.userQuery || '',
                bot_response: wrapper.dataset.botResponse || ''
            };

            await fetch('/api/v1/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (e) {
            console.error('Feedback failed', e);
        }
    }

    // ============================================
    // Mobile Drawer Methods (Desktop Parity)
    // ============================================

    toggleDrawer() {
        const drawer = document.getElementById('mobileDrawer');
        const backdrop = document.getElementById('drawerBackdrop');
        const isOpen = drawer.classList.contains('active');

        if (isOpen) {
            this.closeDrawer();
        } else {
            this.openDrawer();
        }
    }

    openDrawer() {
        const drawer = document.getElementById('mobileDrawer');
        const backdrop = document.getElementById('drawerBackdrop');

        drawer.classList.add('active');
        backdrop.classList.add('active');
        document.body.classList.add('drawer-open');

        // Setup drawer event listeners if not already done
        if (!this.drawerListenersInitialized) {
            this.setupDrawerListeners();
            this.drawerListenersInitialized = true;
        }

        // Populate drawer content
        this.renderDrawerTrendingTopics();
        this.renderDrawerConversations();
    }

    closeDrawer() {
        const drawer = document.getElementById('mobileDrawer');
        const backdrop = document.getElementById('drawerBackdrop');

        drawer.classList.remove('active');
        backdrop.classList.remove('active');
        document.body.classList.remove('drawer-open');
    }

    setupDrawerListeners() {
        // Close button
        document.getElementById('drawerCloseBtn')?.addEventListener('click', () => {
            this.closeDrawer();
        });

        // Backdrop click
        document.getElementById('drawerBackdrop')?.addEventListener('click', () => {
            this.closeDrawer();
        });

        // New Chat button
        document.getElementById('drawerNewChatBtn')?.addEventListener('click', () => {
            this.drawerNewChat();
        });

        // Trending Topics toggle
        document.getElementById('drawerTrendingToggle')?.addEventListener('click', () => {
            this.toggleDrawerSection('drawerTrendingList', 'drawerTrendingToggle');
        });

        // Conversations toggle
        document.getElementById('drawerConversationsToggle')?.addEventListener('click', () => {
            this.toggleDrawerSection('drawerConversationsList', 'drawerConversationsToggle');
        });
    }

    toggleDrawerSection(listId, toggleId) {
        const list = document.getElementById(listId);
        const toggle = document.getElementById(toggleId);

        if (list && toggle) {
            const isExpanded = toggle.getAttribute('aria-expanded') === 'true';
            toggle.setAttribute('aria-expanded', !isExpanded);
            list.classList.toggle('hidden');
        }
    }

    // Desktop Parity: New Chat (uses same logic as desktop startNewChat)
    drawerNewChat() {
        // Stop any ongoing speech
        if (window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }
        this.clearConversation();
        this.closeDrawer();
        location.reload();
    }

    clearConversation() {
        sessionStorage.removeItem('current_conversation_history');
        sessionStorage.removeItem('current_conversation_id');
        sessionStorage.removeItem('message_ratings');
        this.conversationHistory = [];
    }

    // Desktop Parity: Render Trending Topics (uses same logic as desktop renderTrendingList)
    renderDrawerTrendingTopics() {
        const list = document.getElementById('drawerTrendingList');
        if (!list) return;

        // Fetch from API
        fetch('/api/v1/trending')
            .then(response => {
                if (!response.ok) throw new Error('Failed to fetch trending');
                return response.json();
            })
            .then(data => {
                if (data.topics && data.topics.length > 0) {
                    list.innerHTML = '';
                    data.topics.forEach(topic => {
                        const item = document.createElement('div');
                        item.className = 'drawer-list-item';
                        item.innerHTML = `<i class="fas fa-bolt" style="color: #e53e3e;"></i> ${topic.prompt}`;
                        item.onclick = () => {
                            this.messageInput.value = topic.prompt;
                            this.closeDrawer();
                            this.handleSend();
                        };
                        list.appendChild(item);
                    });
                } else {
                    list.innerHTML = '<div class="drawer-list-item" style="opacity: 0.7; cursor: default;">No Trending Topics</div>';
                }
            })
            .catch(error => {
                console.error('Error fetching trending:', error);
                list.innerHTML = '<div class="drawer-list-item" style="opacity: 0.7; cursor: default;">Failed to load</div>';
            });
    }

    // Desktop Parity: Render Conversations (uses same logic as desktop renderConversations)
    renderDrawerConversations() {
        const list = document.getElementById('drawerConversationsList');
        if (!list) return;

        const conversations = JSON.parse(localStorage.getItem('conversation_history_list') || '[]');

        if (conversations.length === 0) {
            list.innerHTML = '<div class="drawer-list-item" style="opacity: 0.7; cursor: default;">No conversations yet</div>';
            return;
        }

        list.innerHTML = '';
        conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'drawer-list-item';
            item.setAttribute('role', 'button');
            item.setAttribute('tabindex', '0');

            const date = new Date(conv.timestamp);
            const timeStr = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
            const iconColor = '#48bb78';

            item.innerHTML = `<i class="fas fa-comment" style="color: ${iconColor};"></i> ${conv.firstMessage}...`;
            item.title = `Started at ${timeStr}`;

            const load = () => this.drawerLoadConversation(conv.id);
            item.onclick = load;
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    load();
                }
            });

            list.appendChild(item);
        });
    }

    // Desktop Parity: Load Conversation (uses same logic as desktop loadConversation)
    drawerLoadConversation(id) {
        const conversations = JSON.parse(localStorage.getItem('conversation_history_list') || '[]');
        const conv = conversations.find(c => c.id === id);

        if (!conv) {
            alert('Conversation not found.');
            return;
        }

        if (conv.history && Array.isArray(conv.history) && conv.history.length > 0) {
            // Stop any ongoing speech
            if (window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
            sessionStorage.setItem('current_conversation_history', JSON.stringify(conv.history));
            sessionStorage.setItem('current_conversation_id', conv.id);
            this.closeDrawer();
            location.reload();
        } else {
            const updated = conversations.filter(c => c.id !== id);
            localStorage.setItem('conversation_history_list', JSON.stringify(updated));
            alert('Old conversation removed. New ones will work correctly.');
            this.renderDrawerConversations();
        }
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.mobileChat = new MobileChat();
});
