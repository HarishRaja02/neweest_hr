document.addEventListener('DOMContentLoaded', () => {
            const jobDescription = document.getElementById('jobDescription');
            const fetchButton = document.getElementById('fetchButton');
            const daysFilter = document.getElementById('daysFilter');
            const statusMessage = document.getElementById('statusMessage');
            const resultsContainer = document.getElementById('resultsContainer');
            const initialPrompt = document.getElementById('initialPrompt');
            const resultsCount = document.getElementById('resultsCount');
            const countValue = document.getElementById('countValue');
            
            const cachedJobDesc = localStorage.getItem('jobDescription');
            if (cachedJobDesc) {
                jobDescription.value = cachedJobDesc;
            }

            fetchButton.addEventListener('click', async () => {
                const jdValue = jobDescription.value.trim();
                const daysValue = daysFilter.value;
                
                if (!jdValue) {
                    statusMessage.innerHTML = '<div class="bg-red-50 text-red-700 p-3 rounded-lg"><i class="fas fa-exclamation-circle mr-2"></i> Please enter a job description to continue.</div>';
                    return;
                }

                localStorage.setItem('jobDescription', jdValue);

                initialPrompt.classList.add('hidden');
                resultsContainer.innerHTML = '';
                resultsCount.classList.add('hidden');
                
                statusMessage.innerHTML = `
                    <div class="flex items-center justify-center gap-3 bg-blue-50 text-blue-700 p-4 rounded-lg">
                        <div class="loading-spinner"></div>
                        <span>Fetching and analyzing resumes...</span>
                    </div>
                `;

                try {
                    const response = await fetch('/fetch_resumes', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ job_description: jdValue, days_filter: parseInt(daysValue) })
                    });

                    if (response.status === 401) {
                        statusMessage.innerHTML = '<div class="bg-red-50 text-red-700 p-3 rounded-lg"><i class="fas fa-exclamation-triangle mr-2"></i> Authentication required. Please click "Re-authenticate" to log in with Google.</div>';
                        return;
                    }

                    const data = await response.json();

                    if (data.message) {
                        statusMessage.innerHTML = `<div class="bg-yellow-50 text-yellow-700 p-3 rounded-lg"><i class="fas fa-info-circle mr-2"></i> ${data.message}</div>`;
                    } else if (data.candidates && data.candidates.length > 0) {
                        renderCandidates(data.candidates);
                        countValue.textContent = data.candidates.length;
                        resultsCount.classList.remove('hidden');
                        statusMessage.innerHTML = `<div class="bg-green-50 text-green-700 p-3 rounded-lg"><i class="fas fa-check-circle mr-2"></i> Successfully analyzed ${data.candidates.length} resumes.</div>`;
                    } else {
                        statusMessage.innerHTML = '<div class="bg-red-50 text-red-700 p-3 rounded-lg"><i class="fas fa-exclamation-triangle mr-2"></i> No suitable resumes found or an error occurred during processing.</div>';
                    }

                } catch (error) {
                    console.error("Error fetching resumes:", error);
                    statusMessage.innerHTML = '<div class="bg-red-50 text-red-700 p-3 rounded-lg"><i class="fas fa-exclamation-triangle mr-2"></i> Error connecting to the backend service. Please check your connection and try again.</div>';
                }
            });

            async function sendEmail(emailType, candidate) {
                statusMessage.innerHTML = `
                    <div class="flex items-center justify-center gap-3 bg-blue-50 text-blue-700 p-4 rounded-lg">
                        <div class="loading-spinner"></div>
                        <span>Sending ${emailType === 'accept' ? 'acceptance' : 'rejection'} email to ${candidate.name || candidate.email}...</span>
                    </div>
                `;

                try {
                    const jdValue = jobDescription.value.trim();
                    const response = await fetch('/send_email', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            email: candidate.email,
                            name: candidate.name,
                            job_description: jdValue,
                            type: emailType
                        })
                    });
                    const data = await response.json();
                    if (data.success) {
                        statusMessage.innerHTML = `<div class="bg-green-50 text-green-700 p-3 rounded-lg"><i class="fas fa-check-circle mr-2"></i> ${data.message}</div>`;
                    } else {
                        statusMessage.innerHTML = `<div class="bg-red-50 text-red-700 p-3 rounded-lg"><i class="fas fa-exclamation-circle mr-2"></i> ${data.message}</div>`;
                    }
                } catch (error) {
                    statusMessage.innerHTML = `<div class="bg-red-50 text-red-700 p-3 rounded-lg"><i class="fas fa-exclamation-circle mr-2"></i> Failed to send email. Please check your network connection and try again.</div>`;
                }
            }

            function formatTextWithMarkdown(text) {
                if (!text) return '';
                
                // Convert bold text
                text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                
                // Convert lists
                text = text.replace(/^-\s+(.*)$/gm, '<li>$1</li>');
                text = text.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
                
                // Convert line breaks
                text = text.replace(/\n/g, '<br>');
                
                return text;
            }

            function parseInterviewQuestions(text) {
                if (!text) return '';
                
                const questions = text.split(/\d+\.\s/).filter(q => q.trim() !== '');
                let html = '';
                
                questions.forEach((question, index) => {
                    const parts = question.split('**Match level:**');
                    const questionText = parts[0].trim();
                    let matchLevel = '';
                    let explanation = '';
                    
                    if (parts.length > 1) {
                        const matchParts = parts[1].split('**Explanation:**');
                        matchLevel = matchParts[0].trim();
                        explanation = matchParts.length > 1 ? matchParts[1].trim() : '';
                    }
                    
                    html += `
                        <div class="question-item">
                            <p class="font-semibold text-slate-800">${index + 1}. ${questionText}</p>
                            ${matchLevel ? `
                                <div class="mt-2 flex items-center">
                                    <span class="match-indicator ${getMatchClass(matchLevel)}"></span>
                                    <span class="text-sm font-medium">${matchLevel}</span>
                                </div>
                            ` : ''}
                            ${explanation ? `
                                <div class="mt-2 text-sm text-slate-600">
                                    <strong>Explanation:</strong> ${explanation}
                                </div>
                            ` : ''}
                        </div>
                    `;
                });
                
                return html;
            }
            
            function getMatchClass(level) {
                if (level.toLowerCase().includes('clear')) return 'match-clear';
                if (level.toLowerCase().includes('partial')) return 'match-partial';
                if (level.toLowerCase().includes('none')) return 'match-none';
                return '';
            }

            function renderCandidates(candidates) {
                const container = document.getElementById('resultsContainer');
                container.innerHTML = '';
                
                candidates.forEach((candidate, index) => {
                    const card = document.createElement('div');
                    card.className = 'candidate-card card mb-6 fade-in';
                    card.style.animationDelay = `${index * 0.1}s`;
                    
                    // Header with expand/collapse functionality
                    const header = document.createElement('div');
                    header.className = 'candidate-header cursor-pointer flex justify-between items-center';
                    header.innerHTML = `
                        <div class="flex items-center">
                            <div class="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center mr-4">
                                <i class="fas fa-user text-blue-600"></i>
                            </div>
                            <div>
                                <h3 class="text-lg font-semibold text-slate-800">${candidate.filename}</h3>
                                <p class="text-slate-500 text-sm">
                                    ${candidate.name || 'Unknown Name'} • ${candidate.email || 'No email'} • ${candidate.phone || 'No phone'}
                                </p>
                            </div>
                        </div>
                        <div class="flex items-center">
                            ${candidate.sections.ats_score !== null ? `
                                <div class="mr-4 text-center">
                                    <div class="text-xs text-slate-500 font-medium">ATS Score</div>
                                    <div class="text-lg font-bold text-blue-600">${candidate.sections.ats_score}/100</div>
                                </div>
                            ` : ''}
                            ${candidate.sections.hr_score !== null ? `
                                <div class="mr-4 text-center">
                                    <div class="text-xs text-slate-500 font-medium">HR Score</div>
                                    <div class="text-lg font-bold text-green-600">${candidate.sections.hr_score}/10</div>
                                </div>
                            ` : ''}
                            <span class="text-slate-400 transition-transform duration-300">
                                <i class="fas fa-chevron-down"></i>
                            </span>
                        </div>
                    `;
                    card.appendChild(header);

                    // Details section (initially hidden)
                    const details = document.createElement('div');
                    details.className = 'p-6 space-y-6 hidden';
                    
                    // Tab container
                    const tabContainer = document.createElement('div');
                    const tabList = document.createElement('div');
                    tabList.className = 'flex overflow-x-auto border-b border-slate-200';
                    tabContainer.appendChild(tabList);

                    const tabContent = document.createElement('div');
                    tabContent.className = 'mt-4';
                    tabContainer.appendChild(tabContent);

                    // Define tabs
                    const tabs = [
                        { id: 'info', title: 'Basic Info', icon: 'user', content: `
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <h4 class="text-slate-700 font-medium mb-2">Candidate Details</h4>
                                    <p><strong>Name:</strong> ${candidate.name || 'Not available'}</p>
                                    <p><strong>Email:</strong> ${candidate.email || 'Not available'}</p>
                                    <p><strong>Phone:</strong> ${candidate.phone || 'Not available'}</p>
                                </div>
                                <div>
                                    <h4 class="text-slate-700 font-medium mb-2">Email Metadata</h4>
                                    <p><strong>Sender:</strong> ${candidate.sender || 'Unknown'}</p>
                                    <p><strong>Subject:</strong> ${candidate.subject || 'N/A'}</p>
                                    <p><strong>Filename:</strong> ${candidate.filename}</p>
                                </div>
                            </div>
                            <div class="mt-4 prose">${formatTextWithMarkdown(candidate.sections.basic_info)}</div>
                        ` },
                        { id: 'strengths', title: 'Strengths & Weaknesses', icon: 'chart-bar', content: `
                            <div class="evaluation-section">
                                <h4 class="text-slate-800 font-semibold mb-4">Strengths</h4>
                                ${candidate.sections.strengths_weaknesses.includes('- **Strength:**') ? 
                                    candidate.sections.strengths_weaknesses.split('- **Strength:**').slice(1).map(strength => {
                                        const cleanStrength = strength.split('- **Weakness:**')[0].trim();
                                        return `
                                            <div class="strength-item">
                                                <div class="strength-icon"><i class="fas fa-plus-circle"></i></div>
                                                <div>${cleanStrength}</div>
                                            </div>
                                        `;
                                    }).join('') : 
                                    `<div class="prose">${formatTextWithMarkdown(candidate.sections.strengths_weaknesses)}</div>`
                                }
                                
                                <h4 class="text-slate-800 font-semibold mb-4 mt-6">Weaknesses</h4>
                                ${candidate.sections.strengths_weaknesses.includes('- **Weakness:**') ? 
                                    candidate.sections.strengths_weaknesses.split('- **Weakness:**').slice(1).map(weakness => {
                                        const cleanWeakness = weakness.split('- **Strength:**')[0].trim();
                                        return `
                                            <div class="weakness-item">
                                                <div class="weakness-icon"><i class="fas fa-minus-circle"></i></div>
                                                <div>${cleanWeakness}</div>
                                            </div>
                                        `;
                                    }).join('') : 
                                    `<div class="prose">${formatTextWithMarkdown(candidate.sections.strengths_weaknesses)}</div>`
                                }
                            </div>
                        ` },
                        { id: 'summary', title: 'Summary & Justification', icon: 'file-alt', content: `
                            <div class="justification-section">
                                <h4 class="text-slate-800 font-semibold mb-4">HR Summary</h4>
                                <div class="prose">${formatTextWithMarkdown(candidate.sections.hr_summary)}</div>
                                
                                <h4 class="text-slate-800 font-semibold mb-4 mt-6">Justification</h4>
                                <div class="prose">${formatTextWithMarkdown(candidate.sections.justification)}</div>
                            </div>
                        ` },
                        { id: 'recommendation', title: 'Recommendation', icon: 'star', content: `
                            <div class="recommendation-section">
                                <div class="prose">${formatTextWithMarkdown(candidate.sections.recommendation)}</div>
                            </div>
                        ` },
                        { id: 'ats', title: 'Scores', icon: 'calculator', content: `
                            <div class="flex flex-col md:flex-row gap-6 text-center">
                                <div class="p-6 rounded-lg bg-slate-50 flex-1 flex flex-col items-center">
                                    <div class="score-badge ats-score mb-4">
                                        ${candidate.sections.ats_score !== null ? candidate.sections.ats_score : '-'}
                                    </div>
                                    <p class="text-xl font-bold text-slate-800">ATS Score</p>
                                    <p class="text-slate-500 mt-2">Out of 100 points</p>
                                    <div class="skill-meter w-full mt-4">
                                        <div class="skill-level ${candidate.sections.ats_score >= 80 ? 'skill-high' : candidate.sections.ats_score >= 60 ? 'skill-medium' : 'skill-low'}" style="width: ${candidate.sections.ats_score}%"></div>
                                    </div>
                                    <p class="text-sm text-slate-500 mt-4">Measures keyword matching and resume structure</p>
                                </div>
                                <div class="p-6 rounded-lg bg-slate-50 flex-1 flex flex-col items-center">
                                    <div class="score-badge hr-score mb-4">
                                        ${candidate.sections.hr_score !== null ? candidate.sections.hr_score : '-'}
                                    </div>
                                    <p class="text-xl font-bold text-slate-800">HR Score</p>
                                    <p class="text-slate-500 mt-2">Out of 10 points</p>
                                    <div class="skill-meter w-full mt-4">
                                        <div class="skill-level ${candidate.sections.hr_score >= 8 ? 'skill-high' : candidate.sections.hr_score >= 6 ? 'skill-medium' : 'skill-low'}" style="width: ${candidate.sections.hr_score * 10}%"></div>
                                    </div>
                                    <p class="text-sm text-slate-500 mt-4">Measures cultural fit and experience relevance</p>
                                </div>
                            </div>
                        ` },
                        { id: 'interview', title: 'Interview Qs', icon: 'question-circle', content: `
                            ${parseInterviewQuestions(candidate.sections.interview_questions)}
                        ` }
                    ];

                    // Create tabs
                    tabs.forEach((tab, tabIndex) => {
                        const tabButton = document.createElement('div');
                        tabButton.className = `tab-button ${tabIndex === 0 ? 'active' : ''}`;
                        tabButton.innerHTML = `
                            <i class="fas fa-${tab.icon} mr-2"></i>
                            ${tab.title}
                        `;
                        tabButton.onclick = () => {
                            // Deactivate all tabs
                            Array.from(tabList.children).forEach(child => {
                                child.classList.remove('active');
                            });
                            
                            // Hide all tab content
                            Array.from(tabContent.children).forEach(child => {
                                child.classList.add('hidden');
                            });
                            
                            // Activate current tab
                            tabButton.classList.add('active');
                            tabContent.children[tabIndex].classList.remove('hidden');
                        };
                        tabList.appendChild(tabButton);
                        
                        // Create tab content
                        const tabSection = document.createElement('div');
                        tabSection.className = `p-4 ${tabIndex === 0 ? '' : 'hidden'}`;
                        tabSection.innerHTML = tab.content;
                        tabContent.appendChild(tabSection);
                    });

                    details.appendChild(tabContainer);

                    // Action buttons
                    const actions = document.createElement('div');
                    actions.className = 'mt-6 flex flex-col sm:flex-row gap-4';
                    
                    const acceptBtn = document.createElement('button');
                    acceptBtn.className = 'btn-primary flex-1 flex items-center justify-center gap-2';
                    acceptBtn.innerHTML = '<i class="fas fa-check-circle"></i> Send Acceptance Email';
                    acceptBtn.onclick = () => sendEmail('accept', candidate);
                    
                    const rejectBtn = document.createElement('button');
                    rejectBtn.className = 'btn-secondary flex-1 flex items-center justify-center gap-2';
                    rejectBtn.innerHTML = '<i class="fas fa-times-circle"></i> Send Rejection Email';
                    rejectBtn.onclick = () => sendEmail('reject', candidate);
                    
                    actions.appendChild(acceptBtn);
                    actions.appendChild(rejectBtn);
                    details.appendChild(actions);

                    // Toggle details on header click
                    header.addEventListener('click', () => {
                        details.classList.toggle('hidden');
                        const icon = header.querySelector('.fa-chevron-down');
                        icon.classList.toggle('rotate-180');
                    });
                    
                    card.appendChild(details);
                    container.appendChild(card);
                });
            }
        });