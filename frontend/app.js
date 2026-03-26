document.addEventListener('DOMContentLoaded', () => {
    const runBtn = document.getElementById('run-btn');
    const stopBtn = document.getElementById('stop-btn');
    const taskInput = document.getElementById('task-input');
    const executionView = document.getElementById('execution-view');
    const logList = document.getElementById('log-list');
    const historyList = document.getElementById('history-list');
    const currentTaskName = document.getElementById('current-task-name');
    const progressBar = document.getElementById('progress-bar');
    const stepCounter = document.getElementById('step-counter');
    const statusBadge = document.getElementById('current-status-badge');

    let currentSessionId = null;
    let pollInterval = null;
    let lastLogCount = 0;

    taskInput.placeholder = '描述你要执行的任务...例如："打开计算器应用并计算 100 + 200"';

    loadHistory();
    checkStatusOnStartup();

    async function checkStatusOnStartup() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            if (data.status === 'running') {
                currentSessionId = data.session_id;
                taskInput.value = data.task_name;
                
                executionView.classList.remove('hidden');
                stopBtn.classList.remove('hidden');
                currentTaskName.textContent = data.task_name;
                logList.innerHTML = '';
                statusBadge.textContent = 'Running';
                statusBadge.className = 'badge running';
                
                startPolling();
                runBtn.disabled = true;
                runBtn.querySelector('.btn-text').textContent = 'Running...';
            }
        } catch (err) {
            console.error('Startup status check error:', err);
        }
    }

    runBtn.addEventListener('click', async () => {
        const task = taskInput.value.trim();
        if (!task) {
            taskInput.focus();
            taskInput.style.borderColor = '#ff4444';
            setTimeout(() => taskInput.style.borderColor = '', 2000);
            return;
        }

        runBtn.disabled = true;
        runBtn.querySelector('.btn-text').textContent = 'Starting...';
        lastLogCount = 0;
        
        try {
            const response = await fetch('/api/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Failed to start task');
            }
            
            const data = await response.json();
            currentSessionId = data.session_id;
            
            executionView.classList.remove('hidden');
            stopBtn.classList.remove('hidden');
            currentTaskName.textContent = task;
            logList.innerHTML = '';
            if (progressBar) progressBar.style.width = '0%';
            stepCounter.textContent = 'Step 0';
            statusBadge.textContent = 'Running';
            statusBadge.className = 'badge running';
            
            startPolling();
            setTimeout(loadHistory, 1000);
        } catch (err) {
            alert('Error: ' + err.message);
            runBtn.disabled = false;
            runBtn.querySelector('.btn-text').textContent = 'Execute Task';
        }
    });

    stopBtn.addEventListener('click', async () => {
        stopBtn.disabled = true;
        stopBtn.textContent = 'Stopping...';
        try {
            await fetch('/api/stop', { method: 'POST' });
        } catch (err) {
            console.error('Stop error:', err);
        }
    });

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            await updateLogs();
            await updateStatus();
        }, 1500);
    }

    async function updateStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            if (data.status === 'completed' || data.status === 'failed' || data.status === 'stopped') {
                clearInterval(pollInterval);
                runBtn.disabled = false;
                runBtn.querySelector('.btn-text').textContent = 'Execute Task';
                
                stopBtn.classList.add('hidden');
                stopBtn.disabled = false;
                stopBtn.innerHTML = 'Stop';

                statusBadge.textContent = data.status;
                statusBadge.className = `badge ${data.status}`;
                if (data.status === 'completed' && progressBar) progressBar.style.width = '100%';
                
                await updateLogs();
                loadHistory(); 
            }
        } catch (err) {
            console.error('Status poll error:', err);
        }
    }

    async function updateLogs() {
        if (!currentSessionId) return;
        
        try {
            const response = await fetch(`/api/sessions/${currentSessionId}`);
            if (!response.ok) return;
            const logs = await response.json();
            
            const currentLogCount = logs.length;
            if (currentLogCount === lastLogCount) return;
            lastLogCount = currentLogCount;
            
            renderLogs(logs, logList, true);
            
            const steps = logs.length - 1; 
            if (steps > 0) {
                stepCounter.textContent = `Step ${steps}`;
                if (progressBar) progressBar.style.width = `${Math.min(steps * 2.5, 95)}%`;
            }
        } catch (err) {
            console.error('Log poll error:', err);
        }
    }

    function renderLogs(logs, container, reverse = false) {
        let actionLogs = logs.slice(1);
        
        if (reverse) {
            actionLogs = [...actionLogs].reverse();
        }
        
        container.innerHTML = '';
        actionLogs.forEach((log, index) => {
            const msg = log.message;
            const item = document.createElement('div');
            item.className = 'log-item fade-in';
            
            const action = msg.action || {};
            const env = msg.environment || {};
            
            const stepNum = reverse ? (actionLogs.length - index) : (index + 1);

            let beforeImageHtml = '';
            let afterImageHtml = '';
            
            if (env.image_url) {
                beforeImageHtml = `
                    <div class="screenshot-container">
                        <div class="screenshot-label">Before</div>
                        <img src="${env.image_url}" class="screenshot-preview" onclick="window.open('${env.image_url}')">
                    </div>
                `;
            }
            
            if (msg.after_image_url) {
                afterImageHtml = `
                    <div class="screenshot-container">
                        <div class="screenshot-label">After</div>
                        <img src="${msg.after_image_url}" class="screenshot-preview" onclick="window.open('${msg.after_image_url}')">
                    </div>
                `;
            }

            const screenshotsHtml = beforeImageHtml || afterImageHtml ? `
                <div class="screenshots-wrapper">
                    ${beforeImageHtml}
                    ${afterImageHtml}
                </div>
            ` : '';

            item.innerHTML = `
                <div class="log-item-header">
                    <span class="step-num">#${stepNum}</span>
                    <span class="action-type">${action.action_type || 'THINK'}</span>
                    <span class="timestamp">${log.timestamp.split(' ')[1]}</span>
                </div>
                <div class="log-content">
                    ${screenshotsHtml}
                    <div class="text-info">
                        <div class="explanation">${action.explain || 'Analyzing state...'}</div>
                        <div class="summary">${action.summary || ''}</div>
                    </div>
                </div>
            `;
            container.appendChild(item);
        });
        
        if (container.children.length > 0) {
            container.scrollTop = 0;
        }
    }

    async function loadHistory() {
        try {
            const response = await fetch('/api/sessions');
            const sessions = await response.json();
            
            historyList.innerHTML = '';
            sessions.forEach(session => {
                const item = document.createElement('div');
                item.className = 'history-item';
                item.innerHTML = `
                    <h4 title="${session.task}">${session.task.substring(0, 50)}${session.task.length > 50 ? '...' : ''}</h4>
                    <div class="date">${session.timestamp}</div>
                `;
                item.addEventListener('click', () => showSessionDetails(session.session_id));
                historyList.appendChild(item);
            });
        } catch (err) {
            console.error('History load error:', err);
        }
    }

    const modal = document.getElementById('session-modal');
    const modalBody = document.getElementById('modal-body');
    const modalTitle = document.getElementById('modal-title');
    const closeModal = document.getElementById('close-modal');

    async function showSessionDetails(sessionId) {
        modal.classList.remove('hidden');
        modalBody.innerHTML = '<div class="loading-spinner"></div>';
        
        try {
            const response = await fetch(`/api/sessions/${sessionId}`);
            const logs = await response.json();
            
            const config = logs[0].message;
            modalTitle.textContent = config.task;
            
            modalBody.innerHTML = '<div class="log-list"></div>';
            renderLogs(logs, modalBody.querySelector('.log-list'));
        } catch (err) {
            modalBody.innerHTML = '<div class="error-message">Error loading details: ' + err.message + '</div>';
        }
    }

    closeModal.onclick = () => modal.classList.add('hidden');
    window.onclick = (e) => { if (e.target === modal) modal.classList.add('hidden'); };
});
