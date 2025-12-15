/**
 * JUNA Deal Assistant Application Logic
 * Structured workflow for building merchant deal battle cards
 */

class DealApp {
    constructor() {
        // State
        this.currentStep = 'context';
        this.context = {};
        this.conversationHistory = [];
        this.questions = [];
        this.currentQuestionIndex = 0;
        this.battleCard = null;
        this.battleCardData = null;  // Store parsed battle card data
        this.spokenScenario = null;   // Deterministic spoken-first scenario
        this.isProcessing = false;
        this.activeRunId = 0; // For request gating

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupNetworkMonitoring();
        this.setupModalHandlers();
        this.setupQuickLaunch();
    }

    setupEventListeners() {
        // Start questions button
        document.getElementById('startQuestionsBtn')?.addEventListener('click', () => this.startQuestions());

        // Reset button
        document.getElementById('resetBtn')?.addEventListener('click', () => this.resetWorkflow());

        // Mobile nav toggle
        document.querySelector('.mobile-nav-toggle')?.addEventListener('click', () => this.toggleSidebar());

        // New Deal button
        document.querySelector('.new-chat-btn')?.addEventListener('click', () => this.resetWorkflow());
    }

    setupQuickLaunch() {
        document.querySelectorAll('.quick-launch-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const vertical = btn.dataset.vertical;
                document.getElementById('vertical').value = vertical;

                // Show visual feedback
                this.showToast(`${vertical.charAt(0).toUpperCase() + vertical.slice(1)} deal selected`);

                // Scroll to context if on mobile
                if (window.innerWidth < 768) {
                    document.getElementById('contextCard')?.scrollIntoView({ behavior: 'smooth' });
                }
            });
        });
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
        updateStatus();
    }

    setupModalHandlers() {
        // Support modal handlers
        document.querySelector('#supportModal .close-modal')?.addEventListener('click', () => this.toggleSupportModal());
        document.getElementById('emailOptionBtn')?.addEventListener('click', () => this.selectSupportOption('email'));
        document.getElementById('callOptionBtn')?.addEventListener('click', () => this.selectSupportOption('call'));
        document.querySelector('#emailForm .submit-btn')?.addEventListener('click', () => this.submitSupportRequest());

        // Success modal handlers
        const successModalClose = document.querySelector('#successModal .close-modal');
        const successModalBtn = document.querySelector('#successModal .submit-btn');
        if (successModalClose) successModalClose.onclick = () => this.closeSuccessModal();
        if (successModalBtn) successModalBtn.onclick = () => this.closeSuccessModal();

        // Click outside to close
        window.onclick = (event) => {
            if (event.target == document.getElementById('supportModal')) this.toggleSupportModal();
            if (event.target == document.getElementById('successModal')) this.closeSuccessModal();
        };
    }

    // WORKFLOW METHODS

    async startQuestions() {
        // Validate context
        const vertical = document.getElementById('vertical').value;
        if (!vertical) {
            this.showToast('Please select a vertical', 'error');
            return;
        }

        // Collect context
        this.context = {
            vertical: vertical,
            state: document.getElementById('state').value || '',
            currentProvider: document.getElementById('currentProvider').value || '',
            volume: document.getElementById('volume').value || '',
            features: {
                tips: document.getElementById('toggleTips').checked,
                memberships: document.getElementById('toggleMemberships').checked,
                ecommerce: document.getElementById('toggleEcommerce').checked
            }
        };

        // Update UI
        this.updateStepIndicator('questions');
        this.currentStep = 'questions';

        // Disable context form
        document.getElementById('startQuestionsBtn').disabled = true;
        document.getElementById('startQuestionsBtn').textContent = 'Questions Started';

        // Start guided questions via API
        await this.fetchFirstQuestion();
    }

    async fetchFirstQuestion() {
        this.isProcessing = true;
        this.showQuestionsLoading();

        try {
            const formData = new FormData();
            formData.append('user_message', `Start guided questions. Context: ${JSON.stringify(this.context)}`);
            formData.append('conversation_history', JSON.stringify(this.conversationHistory));
            formData.append('language', 'en-US');
            formData.append('mode', 'deal');

            const response = await fetch('/api/v1/chat', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullResponse = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                fullResponse += decoder.decode(value, { stream: true });
            }

            // Add to history
            this.conversationHistory.push({
                role: 'assistant',
                content: fullResponse
            });

            // Render question
            this.renderQuestion(fullResponse, 0);

        } catch (error) {
            console.error('Error fetching question:', error);
            this.showToast('Error starting questions. Please try again.', 'error');
            this.renderQuestionsError();
        } finally {
            this.isProcessing = false;
        }
    }

    renderQuestion(questionText, index) {
        const questionsContent = document.getElementById('questionsContent');
        questionsContent.innerHTML = '';

        // Update counter
        document.getElementById('questionCount').textContent = `(${index + 1})`;

        // Create question card
        const questionCard = document.createElement('div');
        questionCard.className = 'question-item active';

        questionCard.innerHTML = `
            <div class="question-text">${questionText}</div>
            <div class="form-field" style="margin-top: 16px;">
                <textarea id="currentAnswer" placeholder="Your answer..." rows="3"></textarea>
            </div>
            <div style="display: flex; gap: 8px; margin-top: 12px;">
                <button class="submit-btn" id="submitAnswerBtn" style="flex: 1;">
                    Next Question <i class="fas fa-arrow-right" style="margin-left: 6px;"></i>
                </button>
            </div>
        `;

        questionsContent.appendChild(questionCard);

        // Add event listener
        document.getElementById('submitAnswerBtn')?.addEventListener('click', () => this.submitAnswer());

        // Allow Enter to submit
        document.getElementById('currentAnswer')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.submitAnswer();
            }
        });
    }

    async submitAnswer() {
        const answer = document.getElementById('currentAnswer')?.value.trim();
        if (!answer) {
            this.showToast('Please provide an answer', 'error');
            return;
        }

        // Save answer
        this.conversationHistory.push({
            role: 'user',
            content: answer
        });

        // Show loading
        this.isProcessing = true;
        document.getElementById('submitAnswerBtn').disabled = true;
        document.getElementById('submitAnswerBtn').innerHTML = '<span class="spinner"></span>Processing...';

        try {
            const formData = new FormData();
            formData.append('user_message', answer);
            formData.append('conversation_history', JSON.stringify(this.conversationHistory));
            formData.append('language', 'en-US');
            formData.append('mode', 'deal');

            const response = await fetch('/api/v1/chat', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullResponse = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                fullResponse += decoder.decode(value, { stream: true });
            }

            // Add to history
            this.conversationHistory.push({
                role: 'assistant',
                content: fullResponse
            });

            // Check if ready for battle card
            if (fullResponse.toLowerCase().includes('i have what i need') ||
                fullResponse.toLowerCase().includes('ready for battle card') ||
                fullResponse.toLowerCase().includes('ready to generate') ||
                fullResponse.startsWith('{') || // Catches if AI returns JSON directly
                this.conversationHistory.filter(m => m.role === 'user').length >= 5) {
                // Show generate battle card button
                this.showGenerateBattleCardButton();
            } else {
                // Show next question
                this.currentQuestionIndex++;
                this.renderQuestion(fullResponse, this.currentQuestionIndex);
            }

        } catch (error) {
            console.error('Error submitting answer:', error);
            this.showToast('Error processing answer. Please try again.', 'error');
        } finally {
            this.isProcessing = false;
        }
    }

    showGenerateBattleCardButton() {
        const questionsContent = document.getElementById('questionsContent');
        questionsContent.innerHTML = `
            <div style="text-align: center; padding: 40px 20px;">
                <i class="fas fa-check-circle" style="font-size: 3em; color: #48bb78; margin-bottom: 16px;"></i>
                <h4 style="margin: 0 0 8px 0; color: var(--text-color);">Discovery Complete</h4>
                <p style="color: var(--text-secondary); margin-bottom: 24px;">Ready to generate your battle card.</p>
                <button class="submit-btn" id="generateBattleCardBtn" style="padding: 12px 32px;">
                    <i class="fas fa-file-alt" style="margin-right: 8px;"></i>
                    Generate Battle Card
                </button>
            </div>
        `;

        document.getElementById('generateBattleCardBtn')?.addEventListener('click', () => this.generateBattleCard());
    }

    resetGenerateButton() {
        const generateBtn = document.getElementById('generateBattleCardBtn');
        if (generateBtn) {
            generateBtn.disabled = false;
            generateBtn.innerHTML = '<i class="fas fa-file-alt" style="margin-right: 8px;"></i>Generate Battle Card';
        }
    }

    async generateBattleCard() {
        // Increment run ID for request gating
        const runId = ++this.activeRunId;
        this.isProcessing = true;
        this.updateStepIndicator('battlecard');
        this.currentStep = 'battlecard';

        // Store timeout handle for cleanup
        let stage2Timeout = null;

        // Show Stage 1: Analyzing
        const battlecardContent = document.getElementById('battlecardContent');
        const setStage = (stage, message, subtitle) => {
            // Only update if this is still the active run
            if (this.activeRunId !== runId) return;

            battlecardContent.innerHTML = `
                <div style="text-align: center; padding: 60px 20px;">
                    <div class="spinner" style="width: 40px; height: 40px; margin: 0 auto 20px;"></div>
                    <p style="color: var(--text-color); font-weight: 500; margin-bottom: 8px;">${message}</p>
                    <p style="color: var(--text-secondary); font-size: 0.9em;">${subtitle}</p>
                </div>
            `;

            const generateBtn = document.getElementById('generateBattleCardBtn');
            if (generateBtn) {
                generateBtn.disabled = true;
                generateBtn.innerHTML = `<span class="spinner"></span>${stage}...`;
            }
        };

        // Stage 1: Analyzing
        setStage('Analyzing', 'Analyzing deal context...', 'Reviewing merchant needs and priorities');

        try {
            const formData = new FormData();
            formData.append('user_message', 'Generate complete battle card with all sections');
            formData.append('conversation_history', JSON.stringify(this.conversationHistory));
            formData.append('language', 'en-US');
            formData.append('mode', 'deal');

            // Stage 2: Building recommendations (after 800ms, gated by runId)
            stage2Timeout = setTimeout(() => {
                if (this.activeRunId === runId) {
                    setStage('Building', 'Building recommendations...', 'Crafting your battle card strategy');
                }
            }, 800);

            const response = await fetch('/api/v1/chat', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) throw new Error('Network response was not ok');

            // Stage 3: Finalizing (gated by runId)
            if (this.activeRunId === runId) {
                setStage('Finalizing', 'Finalizing battle card...', 'Almost ready');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullResponse = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                fullResponse += decoder.decode(value, { stream: true });
            }

            // Only render if this is still the active run
            if (this.activeRunId !== runId) {
                console.log('[DEAL] Skipping render - newer request in progress');
                return;
            }

            // Try to parse as JSON first, fallback to markdown
            console.log('[DEAL] Battle card response received, length:', fullResponse.length);
            console.log('[DEAL] First 200 chars:', fullResponse.substring(0, 200));

            try {
                const battleCardData = JSON.parse(fullResponse);
                console.log('[DEAL] Successfully parsed as JSON');
                this.renderBattleCardFromJSON(battleCardData);
            } catch (jsonError) {
                console.warn('[DEAL] JSON parse failed, trying markdown fallback');
                console.error('[DEAL] JSON parse error:', jsonError.message);
                // Fallback to markdown parsing
                this.renderBattleCardFromMarkdown(fullResponse);
            }

            // Show copy buttons (only if still active run)
            if (this.activeRunId === runId) {
                document.getElementById('copyAllBtn').style.display = 'inline-block';
                document.getElementById('copyTalkTrackBtn').style.display = 'inline-block';
                document.getElementById('copyObjectionsBtn').style.display = 'inline-block';
            }

        } catch (error) {
            console.error('Error generating battle card:', error);

            // Only show error if this is still the active run
            if (this.activeRunId === runId) {
                battlecardContent.innerHTML = `
                    <div style="text-align: center; padding: 40px 20px; color: #e53e3e;">
                        <i class="fas fa-exclamation-triangle" style="font-size: 2em; margin-bottom: 12px;"></i>
                        <p>Error generating battle card. Please try again.</p>
                    </div>
                `;
            }
        } finally {
            // Always cleanup timeout
            if (stage2Timeout) {
                clearTimeout(stage2Timeout);
            }

            // Only reset state if this is still the active run
            if (this.activeRunId === runId) {
                this.isProcessing = false;
                this.resetGenerateButton();
            }
        }
    }

    renderBattleCardFromJSON(data) {
        const content = document.getElementById('battlecardContent');

        // Store battle card data for copy functions
        this.battleCardData = data;

        // Create spoken-first scenario ONCE (deterministic - Refinement #1)
        if (data.scenario) {
            this.spokenScenario = this.createSpokenScenario(data.scenario);
        }

        let html = '';

        // Scenario
        if (data.scenario) {
            html += `
                <div class="battlecard-section" data-section="scenario">
                    <h4>Scenario <button class="copy-section" onclick="window.dealApp.copySection('scenario')"><i class="fas fa-copy"></i></button></h4>
                    <p>${data.scenario}</p>
                </div>
            `;
        }

        // Recommended Stack
        if (data.recommended_stack && data.recommended_stack.length) {
            html += `
                <div class="battlecard-section" data-section="stack">
                    <h4>Recommended Stack <button class="copy-section" onclick="window.dealApp.copySection('stack')"><i class="fas fa-copy"></i></button></h4>
                    <ul>
                        ${data.recommended_stack.map(item => `<li>${item}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        // Why This Wins
        if (data.why_this_wins && data.why_this_wins.length) {
            html += `
                <div class="battlecard-section" data-section="wins">
                    <h4>Why This Wins <button class="copy-section" onclick="window.dealApp.copySection('wins')"><i class="fas fa-copy"></i></button></h4>
                    <ul>
                        ${data.why_this_wins.map(item => {
                if (typeof item === 'object') {
                    return `<li><strong>${item.title}:</strong> ${item.detail}</li>`;
                }
                return `<li>${item}</li>`;
            }).join('')}
                    </ul>
                </div>
            `;
        }

        // Pricing Framework
        if (data.pricing_framework) {
            const pricing = Array.isArray(data.pricing_framework) ? data.pricing_framework.join(' ') : data.pricing_framework;
            html += `
                <div class="battlecard-section" data-section="pricing">
                    <h4>Pricing Framework</h4>
                    <p>${pricing}</p>
                </div>
            `;
        }

        // Likely Objections
        if (data.likely_objections && data.likely_objections.length) {
            html += `
                <div class="battlecard-section" data-section="objections">
                    <h4>Likely Objections <button class="copy-section" onclick="window.dealApp.copySection('objections')"><i class="fas fa-copy"></i></button></h4>
                    <table class="objections-table">
                        ${data.likely_objections.map(obj => `
                            <tr>
                                <td><strong>${obj.objection}</strong></td>
                                <td>${obj.response}</td>
                            </tr>
                        `).join('')}
                    </table>
                </div>
            `;
        }

        // Next Steps
        if (data.next_steps && data.next_steps.length) {
            html += `
                <div class="battlecard-section" data-section="next-steps">
                    <h4>Next Steps</h4>
                    <ol>
                        ${data.next_steps.map(step => `<li>${step}</li>`).join('')}
                    </ol>
                </div>
            `;
        }

        // Compliance Disclaimer
        const disclaimer = data.compliance_disclaimer || 'This battle card is for internal sales use only. Do not share with merchants. All pricing subject to underwriting and final approval.';
        html += `
            <div class="compliance-banner">
                <i class="fas fa-exclamation-triangle"></i>
                <p>${disclaimer}</p>
            </div>
        `;

        content.innerHTML = html;
    }

    renderBattleCardFromMarkdown(markdown) {
        console.log('[DEAL] Using markdown fallback parser');

        // Fallback: parse markdown with flexible section headers
        const sections = {
            scenario: this.extractSection(markdown, 'Scenario') || this.extractFirstParagraph(markdown),
            stack: this.extractSection(markdown, 'Recommended Stack|Stack|Products'),
            wins: this.extractSection(markdown, 'Why This Wins|Why|Benefits'),
            pricing: this.extractSection(markdown, 'Pricing Framework|Pricing'),
            objections: this.extractSection(markdown, 'Likely Objections|Objections'),
            nextSteps: this.extractSection(markdown, 'Next Steps|Action Items'),
            disclaimer: this.extractSection(markdown, 'Compliance Disclaimer|Disclaimer') ||
                'This battle card is for internal sales use only. Do not share with merchants. All pricing subject to underwriting and final approval.'
        };

        console.log('[DEAL] Extracted sections:', {
            scenario: sections.scenario ? sections.scenario.substring(0, 50) + '...' : 'MISSING',
            stack: sections.stack ? 'found' : 'MISSING',
            wins: sections.wins ? 'found' : 'MISSING',
            pricing: sections.pricing ? 'found' : 'MISSING'
        });

        // Convert to JSON-like structure and render
        const data = {
            scenario: sections.scenario || 'Deal context not available.',
            recommended_stack: sections.stack ? this.parseListItems(sections.stack) : ['Recommended products will be determined based on merchant needs.'],
            why_this_wins: sections.wins ? this.parseListItems(sections.wins) : [],
            pricing_framework: sections.pricing || 'Pricing will be customized based on merchant volume and requirements.',
            likely_objections: [], // Would need more complex parsing
            next_steps: sections.nextSteps ? this.parseListItems(sections.nextSteps) : ['Follow up with merchant', 'Send detailed proposal', 'Schedule next meeting'],
            disclaimer: sections.disclaimer
        };

        this.renderBattleCardFromJSON(data);
    }

    extractSection(text, headers) {
        // Try multiple header formats
        const headerVariants = headers.split('|');

        for (const header of headerVariants) {
            // Try **Header** format
            let regex = new RegExp(`\\*\\*${header.trim()}\\*\\*\\s*([\\s\\S]*?)(?=\\*\\*|$)`, 'i');
            let match = text.match(regex);
            if (match && match[1].trim()) return match[1].trim();

            // Try ## Header format
            regex = new RegExp(`##\\s*${header.trim()}\\s*([\\s\\S]*?)(?=##|$)`, 'i');
            match = text.match(regex);
            if (match && match[1].trim()) return match[1].trim();

            // Try plain Header: format
            regex = new RegExp(`${header.trim()}:\\s*([\\s\\S]*?)(?=\\n\\n|$)`, 'i');
            match = text.match(regex);
            if (match && match[1].trim()) return match[1].trim();
        }

        return '';
    }

    extractFirstParagraph(text) {
        // Extract first substantial paragraph as scenario fallback
        const paragraphs = text.split('\n\n');
        for (const para of paragraphs) {
            const cleaned = para.trim();
            if (cleaned.length > 50 && !cleaned.startsWith('**') && !cleaned.startsWith('##')) {
                return cleaned;
            }
        }
        return '';
    }

    parseListItems(text) {
        // Parse bullet points or numbered lists
        const lines = text.split('\n').filter(l => l.trim());
        const items = [];

        for (const line of lines) {
            // Remove bullets (-, *, •, 1., 2., etc.)
            const cleaned = line.replace(/^[\s-*•\d.]+/, '').trim();
            if (cleaned) {
                items.push(cleaned);
            }
        }

        return items.length > 0 ? items : [text.trim()];
    }

    copySection(sectionName) {
        const section = document.querySelector(`[data-section="${sectionName}"]`);
        if (!section) return;

        const text = section.innerText;
        navigator.clipboard.writeText(text).then(() => {
            this.showToast('Section copied to clipboard');
        }).catch(err => {
            console.error('Copy failed:', err);
            this.showToast('Copy failed', 'error');
        });
    }

    copyAll() {
        const content = document.getElementById('battlecardContent');
        if (!content) return;

        // Use clipboard utility with disclaimer included
        const text = this.getPlainTextForCopy(content, { includeDisclaimer: true });
        navigator.clipboard.writeText(text).then(() => {
            this.showToast('Battle card copied to clipboard');
        }).catch(err => {
            console.error('Copy failed:', err);
            this.showToast('Copy failed', 'error');
        });
    }

    // Task 2.1: Copy Talk Track (Primary Adoption Lever)
    copyTalkTrack() {
        if (!this.battleCardData) {
            this.showToast('No battle card available', 'error');
            return;
        }

        // Use stored spoken scenario (deterministic)
        const scenario = this.spokenScenario || this.battleCardData.scenario || '';
        const whyWins = this.battleCardData.why_this_wins || [];

        // Format talk track
        let text = 'Talk Track\n\n';
        // Strip pricing from scenario too
        text += this.stripPricing(scenario) + '\n\n';
        text += 'Why this wins:\n';

        whyWins.forEach(item => {
            if (typeof item === 'object' && item.title && item.detail) {
                // Strip pricing from detail
                const detail = this.stripPricing(item.detail);
                text += `- ${item.title}: ${detail}\n`;
            } else if (typeof item === 'string') {
                text += `- ${this.stripPricing(item)}\n`;
            }
        });

        // Copy to clipboard
        navigator.clipboard.writeText(text.trim()).then(() => {
            this.showToast('Talk track copied');
        }).catch(err => {
            console.error('Copy failed:', err);
            this.showToast('Copy failed', 'error');
        });
    }

    // Task 2.2: Copy Objections (Secondary Adoption Lever)
    copyObjections() {
        if (!this.battleCardData) {
            this.showToast('No battle card available', 'error');
            return;
        }

        const objections = this.battleCardData.objections || this.battleCardData.likely_objections || [];

        if (objections.length === 0) {
            this.showToast('No objections available', 'error');
            return;
        }

        // Format objections as Q&A
        let text = 'Common Objections & Responses\n\n';

        objections.forEach(obj => {
            if (typeof obj === 'object' && obj.objection && obj.response) {
                const objection = this.stripPricing(obj.objection);
                const response = this.stripPricing(obj.response);
                text += `"${objection}"\n→ ${response}\n\n`;
            }
        });

        // Copy to clipboard
        navigator.clipboard.writeText(text.trim()).then(() => {
            this.showToast('Objections copied');
        }).catch(err => {
            console.error('Copy failed:', err);
            this.showToast('Copy failed', 'error');
        });
    }

    // Task 2.3: Deterministic Clipboard Utility (Foundation)
    getPlainTextForCopy(source, options = {}) {
        const defaults = {
            includePricing: false,
            includeDisclaimer: false,
            stripMarkup: true,
            normalizeWhitespace: true,
            preserveBullets: true
        };

        const opts = { ...defaults, ...options };
        let text = '';

        // Extract text from DOM or use provided text
        if (typeof source === 'string') {
            text = source;
        } else if (source instanceof HTMLElement) {
            text = source.innerText;
        } else {
            text = JSON.stringify(source, null, 2);
        }

        // Strip pricing by default
        if (!opts.includePricing) {
            text = this.stripPricing(text);
        }

        // Strip disclaimer by default (keep only for Copy All)
        if (!opts.includeDisclaimer) {
            // Remove disclaimer section
            text = text.replace(/This battle card is for internal.*?(?=\n\n|\n$|$)/gs, '');
            text = text.replace(/Disclaimer.*?(?=\n\n|\n$|$)/gs, '');
        }

        // Normalize whitespace
        if (opts.normalizeWhitespace) {
            // Collapse multiple spaces
            text = text.replace(/[ \t]{2,}/g, ' ');
            // Max 2 consecutive line breaks
            text = text.replace(/\n{3,}/g, '\n\n');
            // Trim lines
            text = text.split('\n').map(line => line.trim()).join('\n');
        }

        return text.trim();
    }

    // Helper: Strip pricing from text
    stripPricing(text) {
        if (!text) return '';

        // Strip dollar amounts
        text = text.replace(/\$[\d,]+(\.\d{2})?/g, '[amount]');

        // Restore percentage-based pricing context (keep percentages)
        // But remove if it's clearly a fee percentage
        text = text.replace(/\[amount\](\.\d+)?%/g, '[rate]%');

        return text;
    }

    // Refinement #1: Create spoken-first scenario (deterministic)
    createSpokenScenario(fullScenario) {
        if (!fullScenario) return '';

        // Transform once: written → spoken
        let spoken = fullScenario
            .replace(/\bThe merchant is\b/g, "They're")
            .replace(/\bThe merchant\b/g, "They")
            .replace(/\bcurrently processing\b/g, "doing")
            .replace(/\bper month\b/g, "/month")
            .replace(/\btransaction volume\b/g, "volume");

        // Condense to first 2 sentences for brevity
        const sentences = spoken.split(/\.\s+/);
        if (sentences.length > 2) {
            spoken = sentences.slice(0, 2).join('. ').trim() + '.';
        }

        return spoken;
    }

    // UI HELPER METHODS

    updateStepIndicator(step) {
        const steps = document.querySelectorAll('.step');
        steps.forEach(s => {
            s.classList.remove('active', 'completed');
            if (s.dataset.step === step) {
                s.classList.add('active');
            } else if (this.getStepOrder(s.dataset.step) < this.getStepOrder(step)) {
                s.classList.add('completed');
            }
        });
    }

    getStepOrder(step) {
        const order = { context: 0, questions: 1, battlecard: 2 };
        return order[step] || 0;
    }

    showQuestionsLoading() {
        const questionsContent = document.getElementById('questionsContent');
        questionsContent.innerHTML = `
            <div style="text-align: center; padding: 40px 20px;">
                <div class="spinner" style="width: 30px; height: 30px; margin: 0 auto 16px;"></div>
                <p style="color: var(--text-secondary);">Preparing questions...</p>
            </div>
        `;
    }

    renderQuestionsError() {
        const questionsContent = document.getElementById('questionsContent');
        questionsContent.innerHTML = `
            <div style="text-align: center; padding: 40px 20px; color: #e53e3e;">
                <i class="fas fa-exclamation-triangle" style="font-size: 2em; margin-bottom: 12px;"></i>
                <p>Error loading questions. Please try again.</p>
                <button class="submit-btn" onclick="window.dealApp.resetWorkflow()" style="margin-top: 16px;">
                    Reset and Try Again
                </button>
            </div>
        `;
    }

    resetWorkflow() {
        if (this.conversationHistory.length > 0) {
            if (!confirm('Are you sure you want to start a new deal? Current progress will be lost.')) {
                return;
            }
        }

        // Reset state
        this.currentStep = 'context';
        this.context = {};
        this.conversationHistory = [];
        this.questions = [];
        this.currentQuestionIndex = 0;
        this.battleCard = null;

        // Reset UI
        document.getElementById('vertical').value = '';
        document.getElementById('state').value = '';
        document.getElementById('currentProvider').value = '';
        document.getElementById('volume').value = '';
        document.getElementById('toggleTips').checked = false;
        document.getElementById('toggleMemberships').checked = false;
        document.getElementById('toggleEcommerce').checked = false;

        document.getElementById('startQuestionsBtn').disabled = false;
        document.getElementById('startQuestionsBtn').textContent = 'Start Guided Questions';

        document.getElementById('questionsContent').innerHTML = `
            <div class="empty-state">
                <i class="fas fa-comments"></i>
                <p>Complete deal context to begin guided questions.</p>
            </div>
        `;

        document.getElementById('battlecardContent').innerHTML = `
            <div class="empty-state">
                <i class="fas fa-file-alt"></i>
                <p>Complete the guided questions to generate your battle card.</p>
            </div>
        `;

        document.getElementById('copyAllBtn').style.display = 'none';
        document.getElementById('copyTalkTrackBtn').style.display = 'none';
        document.getElementById('copyObjectionsBtn').style.display = 'none';
        document.getElementById('questionCount').textContent = '';

        this.updateStepIndicator('context');

        this.showToast('Workflow reset');
    }

    showToast(message, type = 'success') {
        // Simple toast implementation
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: ${type === 'error' ? '#e53e3e' : '#48bb78'};
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10000;
            animation: slideIn 0.3s ease;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    toggleSidebar() {
        document.getElementById('sidebar')?.classList.toggle('active');
    }

    // SUPPORT MODAL METHODS (from chatbot)

    toggleSupportModal() {
        const modal = document.getElementById('supportModal');
        const isClosed = window.getComputedStyle(modal).display === 'none';

        if (isClosed) {
            modal.style.display = 'block';
        } else {
            modal.style.display = 'none';
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

        if (!name || !business || !summary) {
            alert('Please fill all fields');
            return;
        }

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
                alert('Failed to submit request');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error submitting request');
        }
    }

    showSuccessModal(ticketId) {
        document.getElementById('successTicketId').textContent = `#${ticketId}`;
        document.getElementById('successModal').style.display = 'block';
    }

    closeSuccessModal() {
        document.getElementById('successModal').style.display = 'none';
    }

    async startInboundCall() {
        const btn = document.querySelector('#callInfo .submit-btn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>Connecting...';

        try {
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
                alert('Error initiating call');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error initiating call connection');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-phone"></i> Call Now';
        }
    }
}

// Initialize app
window.dealApp = new DealApp();

// Add copy button handlers
document.getElementById('copyAllBtn')?.addEventListener('click', () => window.dealApp.copyAll());
document.getElementById('copyTalkTrackBtn')?.addEventListener('click', () => window.dealApp.copyTalkTrack());
document.getElementById('copyObjectionsBtn')?.addEventListener('click', () => window.dealApp.copyObjections());
