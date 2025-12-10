/**
 * JUNA Chatbot Application Logic
 * Encapsulates chat functionality, API communication, and UI state.
 */

class ChatApp {
    constructor() {
        // DOM Elements
        this.messagesDiv = document.getElementById('messages');
        this.userInput = document.getElementById('userInput');
        this.typingIndicator = document.getElementById('typing');
        this.languageSelect = document.getElementById('languageSelect');
        this.sendBtn = document.getElementById('sendBtn');
        this.imageInput = document.getElementById('imageInput');
        this.imagePreview = document.getElementById('imagePreview');
        this.previewImg = document.getElementById('previewImg');
        this.imageName = document.getElementById('imageName');

        // State
        this.conversationHistory = this.restoreConversation() || [];
        this.isGenerating = false;
        this.abortController = null;
        this.recognition = null;
        this.isListening = false;
        this.isMuted = true;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupSpeechRecognition();
        this.fetchTrendingTopics();
        this.startTrendingPoller();
        this.setupNetworkMonitoring();
        this.renderConversations(); // Load sidebar history

        // Restore UI
        if (this.conversationHistory.length > 0) {
            this.messagesDiv.innerHTML = '';
            this.conversationHistory.forEach(msg => {
                this.addMessage(msg.content, msg.role === 'assistant' ? 'bot' : 'user', msg.role === 'assistant');
            });
        }

        // Theme init
        this.initTheme();
    }

    setupNetworkMonitoring() {
        const updateStatus = () => {
            const indicator = document.querySelector('.status-indicator');
            const dot = document.querySelector('.status-dot');
            if (indicator && dot) {
                const textNode = Array.from(indicator.childNodes).find(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0);

                if (navigator.onLine) {
                    if (textNode) textNode.textContent = ' Online';
                    dot.style.background = '#48bb78';
                    dot.style.boxShadow = '0 0 0 2px rgba(72, 187, 120, 0.2)';
                } else {
                    if (textNode) textNode.textContent = ' Offline';
                    dot.style.background = '#e53e3e';
                    dot.style.boxShadow = '0 0 0 2px rgba(229, 62, 62, 0.2)';
                }
            }
        };

        window.addEventListener('online', updateStatus);
        window.addEventListener('offline', updateStatus);
        updateStatus(); // Initial check
    }

    setupEventListeners() {
        const addKeyboardAccessibility = (selector) => {
            document.querySelectorAll(selector).forEach(item => {
                item.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        item.click();
                    }
                });
            });
        };
        addKeyboardAccessibility('.history-label');
        addKeyboardAccessibility('.language-option');
        addKeyboardAccessibility('.language-btn');

        this.sendBtn.addEventListener('click', () => this.handleSendClick());

        this.userInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendMessage();
        });

        this.imageInput.addEventListener('change', (e) => this.handleImageSelect(e));

        document.addEventListener('paste', (e) => this.handlePasteImage(e));
        this.userInput.addEventListener('paste', (e) => this.handlePasteImage(e));

        document.querySelector('.mobile-nav-toggle')?.addEventListener('click', () => this.toggleSidebar());
        document.querySelector('.new-chat-btn')?.addEventListener('click', () => this.startNewChat());

        document.addEventListener('click', (e) => {
            const dropdown = document.getElementById('languageDropdown');
            const menu = document.getElementById('languageMenu');
            const btn = dropdown.querySelector('.language-btn');

            if (e.target.closest('.language-btn')) {
                const expanded = btn.getAttribute('aria-expanded') === 'true';
                btn.setAttribute('aria-expanded', !expanded);
                menu.classList.toggle('show');
            }
            else if (dropdown && !dropdown.contains(e.target)) {
                btn?.setAttribute('aria-expanded', 'false');
                menu.classList.remove('show');
            }
        });

        document.querySelectorAll('.language-option').forEach(option => {
            option.addEventListener('click', (e) => {
                const value = e.target.dataset.value;
                const text = e.target.textContent;
                this.languageSelect.value = value;
                document.getElementById('selectedLang').textContent = text;
                document.getElementById('languageMenu').classList.remove('show');
                document.querySelector('.language-btn').setAttribute('aria-expanded', 'false');
                this.userInput.focus();
            });
        });

        document.getElementById('supportBtn')?.addEventListener('click', () => this.toggleSupportModal());
        document.querySelector('.close-modal')?.addEventListener('click', () => this.toggleSupportModal());

        document.getElementById('emailOptionBtn')?.addEventListener('click', () => this.selectSupportOption('email'));
        document.getElementById('callOptionBtn')?.addEventListener('click', () => this.selectSupportOption('call'));

        document.querySelector('#emailForm .submit-btn')?.addEventListener('click', () => this.submitSupportRequest());

        const successModalClose = document.querySelector('#successModal .close-modal');
        const successModalBtn = document.querySelector('#successModal .submit-btn');
        if (successModalClose) successModalClose.onclick = () => this.closeSuccessModal();
        if (successModalBtn) successModalBtn.onclick = () => this.closeSuccessModal();

        window.onclick = (event) => {
            if (event.target == document.getElementById('supportModal')) this.toggleSupportModal();
            if (event.target == document.getElementById('successModal')) this.closeSuccessModal();
        };

        document.getElementById('muteBtn')?.addEventListener('click', () => this.toggleMute());
        document.getElementById('micBtn')?.addEventListener('click', () => this.toggleVoice());

        document.querySelector('#imagePreview button')?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.removeImage();
            this.imageInput.value = '';
            this.userInput.focus();
        });
    }

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

    clearConversation() {
        sessionStorage.removeItem('current_conversation_history');
        this.conversationHistory = [];
    }

    startNewChat() {
        this.clearConversation();
        location.reload();
    }

    handleSendClick() {
        if (this.isGenerating) {
            this.stopGeneration();
        } else {
            this.sendMessage();
        }
    }

    stopGeneration() {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
        if (window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }
        this.isGenerating = false;
        this.updateSendButtonState();
        this.addMessage('Generation stopped by user.', 'bot');
        this.typingIndicator.style.display = 'none';
    }

    updateSendButtonState() {
        if (this.isGenerating) {
            this.sendBtn.innerHTML = 'Stop <i class="fas fa-stop" style="margin-left: 5px;"></i>';
            this.sendBtn.classList.add('stop-btn');
            this.sendBtn.style.backgroundColor = '#e53e3e';
        } else {
            this.sendBtn.innerHTML = 'Send <i class="fas fa-paper-plane" style="margin-left: 5px;"></i>';
            this.sendBtn.classList.remove('stop-btn');
            this.sendBtn.style.backgroundColor = '';
        }
    }

    async sendMessage() {
        const text = this.userInput.value.trim();
        const file = this.imageInput.files[0];

        if (!text && !file) return;

        this.addMessage(text, 'user', false, file);
        this.userInput.value = '';
        if (file) this.removeImage();

        this.conversationHistory.push({ role: "user", content: text });

        this.typingIndicator.style.display = 'block';
        this.messagesDiv.scrollTop = this.messagesDiv.scrollHeight;

        try {
            const formData = new FormData();
            formData.append('user_message', text || " ");
            formData.append('conversation_history', JSON.stringify(this.conversationHistory));
            formData.append('language', this.languageSelect.value);
            if (file) formData.append('file', file);

            this.abortController = new AbortController();
            this.isGenerating = true;
            this.updateSendButtonState();

            const response = await fetch('/api/v1/chat', {
                method: 'POST',
                body: formData,
                signal: this.abortController.signal
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            const botContentDiv = this.addMessage('', 'bot');
            let botText = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                botText += chunk;

                let displayText = botText.replace(/<<SUGGESTIONS>>.*$/s, '').trim();
                displayText = displayText.replace(/<>.*$/s, '').trim();
                botContentDiv.innerHTML = marked.parse(displayText);
                this.messagesDiv.scrollTop = this.messagesDiv.scrollHeight;
            }

            const suggestionsMatch = botText.match(/<<SUGGESTIONS>>(.+)$/s);
            if (suggestionsMatch) {
                const suggestions = suggestionsMatch[1].split('|').map(s => s.trim()).filter(s => s);
                if (suggestions.length > 0) {
                    this.renderSuggestions(botContentDiv.closest('.message-wrapper'), suggestions);
                }
            }

            const cleanBotText = botText.replace(/<<SUGGESTIONS>>.*$/s, '').trim();
            this.conversationHistory.push({ role: "assistant", content: cleanBotText });
            this.saveConversation();

            // Speak (Non-critical)
            if (!this.isMuted) {
                try {
                    this.speak(cleanBotText);
                } catch (e) {
                    console.warn('TTS Error:', e);
                }
            }

            // Persist to Backend and Storage (Non-critical)
            try {
                if (this.conversationHistory.length === 2) {
                    this.saveConversationToHistory(text);
                } else if (this.conversationHistory.length > 2) {
                    this.updateSavedConversation();
                }
            } catch (e) {
                console.error('History Save Error:', e);
            }

        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Error:', error);
                // Only show connection error if we haven't received any text yet
                if (!botText) {
                    this.addMessage('Error connecting to server.', 'bot');
                } else {
                    this.addMessage('Error finishing response.', 'bot');
                }
            }
        } finally {
            if (this.isGenerating) {
                this.isGenerating = false;
                this.abortController = null;
                this.updateSendButtonState();
                this.typingIndicator.style.display = 'none';
            }
        }
    }

    addMessage(text, sender, isMarkdown = false, imageFile = null) {
        const wrapper = document.createElement('div');
        wrapper.className = `message-wrapper ${sender}`;

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender === 'user' ? 'user-message' : 'bot-message'}`;

        const textContentDiv = document.createElement('div');
        textContentDiv.className = 'message-content';
        messageDiv.appendChild(textContentDiv);

        // Display uploaded image in chat message
        if (imageFile) {
            const img = document.createElement('img');
            img.src = URL.createObjectURL(imageFile);
            img.style.maxWidth = '300px';
            img.style.maxHeight = '300px';
            img.style.borderRadius = '12px';
            img.style.marginBottom = '12px';
            img.style.display = 'block';
            img.style.objectFit = 'cover';
            textContentDiv.appendChild(img);
        }

        if (text) {
            const textNode = document.createElement('div');
            if (isMarkdown) {
                textNode.innerHTML = marked.parse(text);
            } else {
                textNode.textContent = text;
            }
            textContentDiv.appendChild(textNode);
        }

        wrapper.appendChild(messageDiv);

        if (sender === 'bot') {
            const actionsRow = document.createElement('div');
            actionsRow.className = 'actions-row';
            const feedbackDiv = document.createElement('div');
            feedbackDiv.className = 'feedback-buttons';

            const msgId = Date.now().toString();

            const upBtn = document.createElement('button');
            upBtn.className = 'feedback-btn';
            upBtn.innerHTML = '<i class="fas fa-thumbs-up"></i>';
            upBtn.onclick = () => this.sendFeedback(msgId, 'up', upBtn, downBtn);

            const downBtn = document.createElement('button');
            downBtn.className = 'feedback-btn';
            downBtn.innerHTML = '<i class="fas fa-thumbs-down"></i>';
            downBtn.onclick = () => this.sendFeedback(msgId, 'down', downBtn, upBtn);

            feedbackDiv.appendChild(upBtn);
            feedbackDiv.appendChild(downBtn);
            actionsRow.appendChild(feedbackDiv);
            wrapper.appendChild(actionsRow);
        }

        this.messagesDiv.appendChild(wrapper);
        this.messagesDiv.scrollTop = this.messagesDiv.scrollHeight;
        return textContentDiv;
    }

    handleImageSelect(event) {
        const file = event.target.files[0];
        if (file) this.showImagePreview(file);
    }

    handlePasteImage(event) {
        const items = event.clipboardData?.items;
        if (!items) return;

        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                event.preventDefault();
                const blob = items[i].getAsFile();
                const file = new File([blob], `pasted-image-${Date.now()}.png`, { type: blob.type });

                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                this.imageInput.files = dataTransfer.files;

                this.showImagePreview(file);
                break;
            }
        }
    }

    showImagePreview(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            this.previewImg.src = e.target.result;
            this.imageName.textContent = file.name;
            this.imagePreview.style.display = 'flex';
        };
        reader.readAsDataURL(file);
    }

    removeImage() {
        this.imageInput.value = '';
        this.imagePreview.style.display = 'none';
        this.previewImg.src = '';
        this.imageName.textContent = '';
    }

    renderSuggestions(wrapper, suggestions) {
        let container = wrapper.querySelector('.suggestions-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'suggestions-container';
            wrapper.querySelector('.actions-row').appendChild(container);
        }

        suggestions.forEach(suggestion => {
            const chip = document.createElement('button');
            chip.className = 'suggestion-chip';

            if (suggestion.toLowerCase().startsWith('call support')) {
                chip.className += ' call-chip';
                chip.innerHTML = '<i class="fas fa-phone"></i> Call Support';
                chip.onclick = () => this.toggleSupportModal();
            } else {
                chip.innerHTML = `<i class="fas fa-lightbulb"></i> ${suggestion}`;
                chip.onclick = () => {
                    this.userInput.value = suggestion;
                    this.sendMessage();
                };
            }
            container.appendChild(chip);
        });
    }

    async sendFeedback(msgId, rating, btn, otherBtn) {
        btn.classList.add(rating === 'up' ? 'active-up' : 'active-down');
        otherBtn.classList.remove('active-up', 'active-down');

        try {
            await fetch('/api/v1/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message_id: msgId, rating: rating })
            });
        } catch (e) { console.error('Feedback failed', e); }
    }

    async fetchTrendingTopics() {
        const list = document.getElementById('trendingList');
        if (list && list.innerHTML.includes('Loading')) {
            // Keep loading state
        }

        try {
            const response = await fetch('/api/v1/trending');
            if (!response.ok) throw new Error('Failed to fetch trending topics');
            const data = await response.json();
            if (data.topics) this.renderTrendingList(data.topics);
        } catch (e) {
            console.error("Error fetching trending:", e);
            if (list) list.innerHTML = '<div class="history-item" style="opacity: 0.7;">Failed to load topics</div>';
        }
    }

    renderConversations() {
        const list = document.getElementById('conversationsList');
        const conversations = JSON.parse(localStorage.getItem('conversation_history_list') || '[]');

        if (conversations.length === 0) {
            list.innerHTML = '<div class="history-item" style="cursor: default; opacity: 0.7; font-size: 0.9em;">No conversations yet</div>';
            return;
        }

        list.innerHTML = '';
        conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'history-item';
            item.setAttribute('role', 'button');
            item.setAttribute('tabindex', '0');

            const date = new Date(conv.timestamp);
            const timeStr = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
            const iconColor = '#48bb78';

            item.innerHTML = `<i class="fas fa-comment" style="color: ${iconColor};"></i> ${conv.firstMessage}...`;
            item.title = `Started at ${timeStr}`;

            const load = () => this.loadConversation(conv.id);
            item.onclick = load;
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); load(); }
            });

            list.appendChild(item);
        });
    }

    loadConversation(id) {
        const conversations = JSON.parse(localStorage.getItem('conversation_history_list') || '[]');
        const conv = conversations.find(c => c.id === id);

        if (!conv) {
            alert('Conversation not found.');
            return;
        }

        if (conv.history && Array.isArray(conv.history) && conv.history.length > 0) {
            sessionStorage.setItem('current_conversation_history', JSON.stringify(conv.history));
            sessionStorage.setItem('current_conversation_id', conv.id);
            location.reload();
        } else {
            const updated = conversations.filter(c => c.id !== id);
            localStorage.setItem('conversation_history_list', JSON.stringify(updated));
            alert('Old conversation removed. New ones will work correctly.');
            this.renderConversations();
        }
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
        this.renderConversations();
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
            this.renderConversations();
        }
    }

    async startInboundCall() {
        const btn = document.querySelector('#callInfo .submit-btn');
        const originalText = btn.textContent;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>Connecting...';

        try {
            // Use "Unknown" to pass backend validation (Web Caller is not a valid phone number)
            const response = await fetch('/api/v1/support/call-inbound', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone: "Unknown",
                    conversation_history: this.conversationHistory
                })
            });

            if (response.ok) {
                const data = await response.json();
                this.toggleSupportModal();
                this.showSuccessModal(data.ticket_id);
                window.location.href = 'tel:+15551234567';
            } else {
                const err = await response.json();
                console.error("Inbound Call Failed:", err);
                alert(`Error: ${err.detail || 'Failed to initiate call ticket'}`);
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error initiating call connection.');
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }

    renderTrendingList(topics) {
        const list = document.getElementById('trendingList');
        if (!list || !topics.length) return;
        list.innerHTML = '';
        topics.forEach(topic => {
            const item = document.createElement('div');
            item.className = 'history-item';
            item.innerHTML = `<i class="fas fa-bolt" style="color: #e53e3e;"></i> ${topic.prompt}`;
            item.onclick = () => {
                this.userInput.value = topic.prompt;
                this.sendMessage();
            };
            list.appendChild(item);
        });
    }

    startTrendingPoller() {
        setInterval(() => this.fetchTrendingTopics(), 10000);
    }

    toggleSupportModal() {
        const modal = document.getElementById('supportModal');
        const isClosed = window.getComputedStyle(modal).display === 'none';

        if (isClosed) {
            modal.style.display = 'block';
            const focusable = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
            if (focusable.length) focusable[0].focus();
        } else {
            modal.style.display = 'none';
            document.getElementById('supportBtn').focus();
        }
    }

    selectSupportOption(type) {
        document.querySelectorAll('.modal-option-btn').forEach(b => b.classList.remove('active'));
        if (type === 'email') {
            document.getElementById('emailOptionBtn').classList.add('active');
            document.getElementById('emailForm').style.display = 'block';
            document.getElementById('callInfo').style.display = 'none';
        } else {
            document.getElementById('callOptionBtn').classList.add('active');
            document.getElementById('emailForm').style.display = 'none';
            document.getElementById('callInfo').style.display = 'block';
        }
    }

    async submitSupportRequest() {
        const name = document.getElementById('supportName').value;
        const business = document.getElementById('supportBusiness').value;
        const summary = document.getElementById('supportSummary').value;

        if (!name || !business || !summary) { alert('Please fill all fields'); return; }

        try {
            const res = await fetch('/api/v1/support/email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, business, summary, conversation_history: this.conversationHistory })
            });
            if (res.ok) {
                const data = await res.json();
                this.toggleSupportModal();
                this.showSuccessModal(data.ticket_id);
            } else {
                const err = await res.json();
                console.error("Support Request Failed:", err);
                let msg = 'Failed to submit request';
                if (err.detail) {
                    if (typeof err.detail === 'string') {
                        msg = err.detail;
                    } else if (Array.isArray(err.detail)) {
                        // Pydantic validation error list
                        msg = err.detail.map(e => `${e.loc.join('.')} - ${e.msg}`).join('\n');
                    } else {
                        msg = JSON.stringify(err.detail);
                    }
                }
                alert(`Error: ${msg}`);
            }
        } catch (e) {
            console.error(e);
            alert('Error connecting to support service.');
        }
    }

    showSuccessModal(ticketId) {
        document.getElementById('successTicketId').textContent = '#' + ticketId;
        const modal = document.getElementById('successModal');
        modal.style.display = 'block';
        const btn = modal.querySelector('.submit-btn');
        if (btn) btn.focus();
    }

    closeSuccessModal() {
        document.getElementById('successModal').style.display = 'none';
        document.getElementById('supportBtn').focus();
    }

    setupSpeechRecognition() {
        if ('webkitSpeechRecognition' in window) {
            this.recognition = new webkitSpeechRecognition();
            this.recognition.continuous = false;
            this.recognition.interimResults = false;
            this.recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                this.userInput.value = transcript;
                this.sendMessage();
            };
            this.recognition.onend = () => {
                this.isListening = false;
                document.getElementById('micBtn').style.color = '#718096';
            };
        }
    }

    toggleVoice() {
        if (!this.recognition) { alert('Speech not supported'); return; }
        if (this.isListening) {
            this.recognition.stop();
        } else {
            this.recognition.start();
            this.isListening = true;
            document.getElementById('micBtn').style.color = '#e53e3e';
        }
    }

    speak(text) {
        if (this.isMuted || !window.speechSynthesis) return;
        const utterance = new SpeechSynthesisUtterance(text);
        window.speechSynthesis.speak(utterance);
    }

    toggleMute() {
        this.isMuted = !this.isMuted;
        const btn = document.getElementById('muteBtn');
        if (this.isMuted) {
            btn.innerHTML = '<i class="fas fa-volume-mute" style="color: #e53e3e;"></i>';
            if (window.speechSynthesis) window.speechSynthesis.cancel();
        } else {
            btn.innerHTML = '<i class="fas fa-volume-up" style="color: #48bb78;"></i>';
        }
    }

    initTheme() {
        const toggleSwitch = document.querySelector('#theme-toggle');
        const theme = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', theme);
        if (toggleSwitch) {
            toggleSwitch.checked = theme === 'dark';
            toggleSwitch.addEventListener('change', (e) => {
                const newTheme = e.target.checked ? 'dark' : 'light';
                document.documentElement.setAttribute('data-theme', newTheme);
                localStorage.setItem('theme', newTheme);
            });
        }
    }

    toggleSidebar() {
        document.getElementById('sidebar').classList.toggle('active');
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});
