// YT Fast Downloader - Client-Side Controller
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('download-form');
    const input = document.getElementById('video-url-input');
    const clearBtn = document.getElementById('clear-btn');
    const pasteBtn = document.getElementById('paste-btn');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = document.getElementById('btn-text');
    const btnIcon = document.getElementById('btn-icon');
    const btnSpinner = document.getElementById('btn-spinner');
    const loadingState = document.getElementById('loading-state');
    const errorContainer = document.getElementById('error-container');
    const errorText = document.getElementById('error-text');
    const resultsSection = document.getElementById('results-section');

    let currentVideoData = null;
    let selectedFormat = 'mp4';
    let selectedVideoQuality = '720';
    let selectedAudioQuality = '192';
    let activePollInterval = null;

    // Regex to validate YouTube URLs
    const ytRegex = /^(https?:\/\/)?(www\.|m\.)?(youtube\.com\/(watch\?(.*&)?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([\w-]{11})(\S*)?$/i;

    function updateClearButton() {
        if (input.value.trim().length > 0) {
            clearBtn.classList.remove('hidden');
        } else {
            clearBtn.classList.add('hidden');
        }
    }

    input.addEventListener('input', updateClearButton);
    updateClearButton();

    clearBtn.addEventListener('click', () => {
        input.value = '';
        updateClearButton();
        input.focus();
        hideResults();
        hideError();
    });

    pasteBtn.addEventListener('click', async () => {
        try {
            const text = await navigator.clipboard.readText();
            if (text) {
                input.value = text.trim();
                updateClearButton();
                handleFetchMetadata();
            }
        } catch (err) {
            console.warn('Clipboard read error:', err);
            input.focus();
        }
    });

    document.querySelectorAll('.sample-link').forEach(btn => {
        btn.addEventListener('click', () => {
            const sampleUrl = btn.getAttribute('data-url');
            if (sampleUrl) {
                input.value = sampleUrl;
                updateClearButton();
                handleFetchMetadata();
            }
        });
    });

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        handleFetchMetadata();
    });

    async function handleFetchMetadata() {
        const url = input.value.trim();
        hideError();

        if (!url) {
            showError('Please enter a YouTube video URL.');
            input.focus();
            return;
        }

        if (!ytRegex.test(url)) {
            showError('Please enter a valid YouTube URL (e.g., https://www.youtube.com/watch?v=... or https://youtu.be/...)');
            input.focus();
            return;
        }

        setLoading(true);
        hideResults();

        try {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            const response = await fetch('/api/extract/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Failed to extract video information.');
            }

            currentVideoData = data.data;
            renderResults(currentVideoData);
        } catch (err) {
            showError(err.message || 'An unexpected error occurred while processing the video.');
        } finally {
            setLoading(false);
        }
    }

    function setLoading(isLoading) {
        if (isLoading) {
            submitBtn.disabled = true;
            btnText.textContent = 'Analyzing...';
            btnIcon.classList.add('hidden');
            btnSpinner.classList.remove('hidden');
            loadingState.classList.remove('hidden');
        } else {
            submitBtn.disabled = false;
            btnText.textContent = 'Get Download Links';
            btnIcon.classList.remove('hidden');
            btnSpinner.classList.add('hidden');
            loadingState.classList.add('hidden');
        }
    }

    function showError(msg) {
        errorText.textContent = msg;
        errorContainer.classList.remove('hidden');
        errorContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function hideError() {
        errorContainer.classList.add('hidden');
    }

    function hideResults() {
        resultsSection.classList.add('hidden');
    }

    function renderResults(meta) {
        document.getElementById('res-thumbnail').src = meta.thumbnail;
        document.getElementById('res-title').textContent = meta.title;
        document.getElementById('res-duration').textContent = meta.duration_formatted;
        document.getElementById('res-channel').textContent = meta.channel;
        document.getElementById('res-views').innerHTML = `
            <svg class="w-3.5 h-3.5 text-slate-500 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
            ${meta.views}
        `;

        selectFormat('mp4');
        resultsSection.classList.remove('hidden');
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    window.selectFormat = function(format) {
        selectedFormat = format;
        const tabMp4 = document.getElementById('tab-mp4');
        const tabMp3 = document.getElementById('tab-mp3');
        const qualityContainer = document.getElementById('quality-buttons');
        const qualityLabel = document.getElementById('quality-label');

        qualityContainer.innerHTML = '';

        if (format === 'mp4') {
            tabMp4.className = 'format-tab py-3 px-4 rounded-xl border border-red-500 bg-red-500/10 text-white font-bold text-sm flex items-center justify-center space-x-2 transition-all';
            tabMp3.className = 'format-tab py-3 px-4 rounded-xl border border-slate-800 bg-slate-900 text-slate-400 hover:text-white font-bold text-sm flex items-center justify-center space-x-2 transition-all';
            qualityLabel.textContent = 'Select Video Resolution:';

            const resList = (currentVideoData && currentVideoData.available_resolutions && currentVideoData.available_resolutions.length > 0)
                ? currentVideoData.available_resolutions
                : [1080, 720, 480, 360];

            selectedVideoQuality = String(resList[0]);

            resList.forEach((res, idx) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = `quality-pill px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    idx === 0 
                        ? 'bg-red-500/20 text-white border border-red-500' 
                        : 'bg-slate-900 text-slate-400 border border-slate-800 hover:border-slate-700 hover:text-slate-200'
                }`;
                btn.textContent = `${res}p ${res >= 720 ? 'HD' : ''}`;
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.quality-pill').forEach(p => {
                        p.className = 'quality-pill px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-slate-400 border border-slate-800 hover:border-slate-700 hover:text-slate-200 transition-all';
                    });
                    btn.className = 'quality-pill px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-red-500/20 text-white border border-red-500 transition-all';
                    selectedVideoQuality = String(res);
                });
                qualityContainer.appendChild(btn);
            });

        } else {
            tabMp3.className = 'format-tab py-3 px-4 rounded-xl border border-emerald-500 bg-emerald-500/10 text-white font-bold text-sm flex items-center justify-center space-x-2 transition-all';
            tabMp4.className = 'format-tab py-3 px-4 rounded-xl border border-slate-800 bg-slate-900 text-slate-400 hover:text-white font-bold text-sm flex items-center justify-center space-x-2 transition-all';
            qualityLabel.textContent = 'Select Audio Bitrate:';

            const bitrates = [
                { val: '320', label: '320 kbps (High Fidelity)' },
                { val: '192', label: '192 kbps (Standard)' },
                { val: '128', label: '128 kbps (Lightweight)' },
            ];

            selectedAudioQuality = '192';

            bitrates.forEach((bitrate, idx) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = `quality-pill px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    bitrate.val === '192' 
                        ? 'bg-emerald-500/20 text-white border border-emerald-500' 
                        : 'bg-slate-900 text-slate-400 border border-slate-800 hover:border-slate-700 hover:text-slate-200'
                }`;
                btn.textContent = bitrate.label;
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.quality-pill').forEach(p => {
                        p.className = 'quality-pill px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-slate-400 border border-slate-800 hover:border-slate-700 hover:text-slate-200 transition-all';
                    });
                    btn.className = 'quality-pill px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/20 text-white border border-emerald-500 transition-all';
                    selectedAudioQuality = bitrate.val;
                });
                qualityContainer.appendChild(btn);
            });
        }
    };

    // Trigger download with live progress tracking
    window.triggerDownload = async function(format) {
        if (!currentVideoData || !currentVideoData.url) {
            showError('Please extract a video before downloading.');
            return;
        }

        const formatType = format || selectedFormat;
        const qualityVal = (formatType === 'mp3') ? selectedAudioQuality : selectedVideoQuality;

        const modal = document.getElementById('download-progress-modal');
        const modalTitle = document.getElementById('download-modal-title');
        const modalMsg = document.getElementById('download-modal-msg');
        const percentEl = document.getElementById('progress-percent');
        const speedEl = document.getElementById('progress-speed');
        const barFill = document.getElementById('progress-bar-fill');
        const iconSpinner = document.getElementById('modal-icon-spinner');
        const iconSuccess = document.getElementById('modal-icon-success');
        const iconError = document.getElementById('modal-icon-error');
        const cancelBtn = document.getElementById('modal-cancel-btn');

        // Reset modal UI
        iconSpinner.classList.remove('hidden');
        iconSuccess.classList.add('hidden');
        iconError.classList.add('hidden');
        cancelBtn.textContent = 'Cancel';
        barFill.style.width = '0%';
        percentEl.textContent = '0%';
        speedEl.textContent = 'Connecting...';

        if (formatType === 'mp3') {
            modalTitle.textContent = 'Extracting Studio MP3 Audio';
            modalMsg.textContent = 'Connecting to YouTube and converting audio to MP3 with FFmpeg...';
        } else {
            modalTitle.textContent = 'Preparing High Definition MP4';
            modalMsg.textContent = 'Connecting to YouTube and preparing media streams...';
        }

        modal.classList.remove('hidden');

        try {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
            const startResp = await fetch('/api/prepare/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({
                    url: currentVideoData.url,
                    format: formatType,
                    quality: qualityVal,
                })
            });

            const startData = await startResp.json();
            if (!startResp.ok || !startData.success) {
                throw new Error(startData.error || 'Could not initiate download job.');
            }

            const jobId = startData.job_id;

            // Poll progress
            if (activePollInterval) clearInterval(activePollInterval);

            activePollInterval = setInterval(async () => {
                try {
                    const pollResp = await fetch(`/api/progress/${jobId}/`);
                    const pollData = await pollResp.json();

                    if (!pollResp.ok || !pollData.success) {
                        clearInterval(activePollInterval);
                        throw new Error(pollData.error || 'Error polling download progress.');
                    }

                    const job = pollData.job;

                    if (job.status === 'downloading') {
                        const pct = Math.min(Math.round(job.percent || 0), 96);
                        barFill.style.width = `${pct}%`;
                        percentEl.textContent = `${pct}%`;
                        speedEl.textContent = job.speed || 'Downloading...';
                        modalMsg.textContent = job.message || 'Downloading media from YouTube...';

                    } else if (job.status === 'processing') {
                        barFill.style.width = '98%';
                        percentEl.textContent = '98%';
                        speedEl.textContent = 'Processing';
                        modalMsg.textContent = job.message || 'Converting / encoding media with FFmpeg...';

                    } else if (job.status === 'ready') {
                        clearInterval(activePollInterval);
                        barFill.style.width = '100%';
                        percentEl.textContent = '100%';
                        speedEl.textContent = 'Complete';
                        modalMsg.textContent = 'File ready! Initiating browser download...';
                        iconSpinner.classList.add('hidden');
                        iconSuccess.classList.remove('hidden');
                        cancelBtn.textContent = 'Close';

                        // Trigger download stream
                        const downloadUrl = pollData.download_url;
                        const link = document.createElement('a');
                        link.href = downloadUrl;
                        link.style.display = 'none';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        setTimeout(() => {
                            closeDownloadModal();
                        }, 2500);

                    } else if (job.status === 'error') {
                        clearInterval(activePollInterval);
                        iconSpinner.classList.add('hidden');
                        iconError.classList.remove('hidden');
                        modalTitle.textContent = 'Download Failed';
                        modalMsg.textContent = job.error || 'An error occurred during media processing.';
                        cancelBtn.textContent = 'Close';
                    }
                } catch (pollErr) {
                    clearInterval(activePollInterval);
                    iconSpinner.classList.add('hidden');
                    iconError.classList.remove('hidden');
                    modalTitle.textContent = 'Download Error';
                    modalMsg.textContent = pollErr.message;
                    cancelBtn.textContent = 'Close';
                }
            }, 750);

        } catch (err) {
            iconSpinner.classList.add('hidden');
            iconError.classList.remove('hidden');
            modalTitle.textContent = 'Failed to Start Download';
            modalMsg.textContent = err.message;
            cancelBtn.textContent = 'Close';
        }
    };

    window.cancelDownloadJob = function() {
        if (activePollInterval) {
            clearInterval(activePollInterval);
            activePollInterval = null;
        }
        closeDownloadModal();
    };

    window.closeDownloadModal = function() {
        document.getElementById('download-progress-modal').classList.add('hidden');
    };
});
