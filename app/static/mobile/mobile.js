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

        // DOM Elements
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.typingIndicator = document.getElementById('typingIndicator');

        this.init();
    }

    init() {
        console.log('JUNA Mobile Chat initialized');

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
    }

    updateSendButton(isStreaming) {
        if (isStreaming) {
            // Show stop icon
            this.sendBtn.innerHTML = '<i class="fas fa-stop"></i>';
            this.sendBtn.classList.add('stop-active');
        } else {
            // Show send icon
            this.sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
            this.sendBtn.classList.remove('stop-active');
        }
    }

    handleStop() {
        if (this.abortController) {
            // Signal to break stream loop
            this.shouldStopStreaming = true;

            // Abort the request
            this.abortController.abort();

            // Immediately clean up UI (don't wait for error propagation)
            this.isGenerating = false;
            this.abortController = null;
            this.toggleInputState(false);
            this.typingIndicator.style.display = 'none';
            this.updateSendButton(false);
            this.messageInput.focus();
        }
    }

    async handleSend() {
        const text = this.messageInput.value.trim();

        // Prevent empty sends or double-sends
        if (!text || this.isGenerating) return;

        // Clear input immediately
        this.messageInput.value = '';

        // Render user message
        this.addUserMessage(text);

        // Update conversation history
        this.conversationHistory.push({ role: "user", content: text });

        // Reset streaming flag
        this.shouldStopStreaming = false;

        // Set generating state BEFORE showing stop button
        this.isGenerating = true;

        // Disable input during generation
        this.toggleInputState(true);

        // Show stop button
        this.updateSendButton(true);

        // Show typing indicator
        this.typingIndicator.style.display = 'block';
        this.scrollToBottom();

        try {
            await this.sendMessage(text);
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Chat error:', error);
                this.addErrorMessage('Error connecting to server. Please try again.');
            }
        } finally {
            // Reset state (only if not already reset by handleStop)
            if (this.isGenerating) {
                this.isGenerating = false;
                this.toggleInputState(false);
                this.typingIndicator.style.display = 'none';
                this.updateSendButton(false);
                this.messageInput.focus();
            }
        }
    }

    async sendMessage(text) {
        // Build FormData payload (matching desktop)
        const formData = new FormData();
        formData.append('user_message', text);
        formData.append('conversation_history', JSON.stringify(this.conversationHistory));
        formData.append('language', 'en-US'); // Default for Phase 2

        // Setup abort controller
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
        await this.handleStream(response);

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
            // Check if user stopped streaming
            if (this.shouldStopStreaming) {
                break;
            }

            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            botText += chunk;

            // Strip suggestions marker (desktop does this)
            let displayText = botText.replace(/<<SUGGESTIONS>>.*$/s, '').trim();
            displayText = displayText.replace(/<>.*$/s, '').trim();

            // Update bot message (plain text for Phase 2, no markdown yet)
            botElement.textContent = displayText;
            this.scrollToBottom();
        }

        // Clean final text
        const cleanBotText = botText.replace(/<<SUGGESTIONS>>.*$/s, '').trim();

        // Update conversation history
        this.conversationHistory.push({ role: "assistant", content: cleanBotText });
    }

    addUserMessage(text) {
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper user';

        const message = document.createElement('div');
        message.className = 'message';
        message.textContent = text;

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
        // DON'T disable send button - it needs to work as stop button during streaming

        if (disabled) {
            this.messageInput.parentElement.classList.add('disabled');
        } else {
            this.messageInput.parentElement.classList.remove('disabled');
        }
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.mobileChat = new MobileChat();
});
