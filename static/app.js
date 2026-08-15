document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('themeToggle');
    themeToggle.addEventListener('click', () => {
        const theme = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', theme);
    });

    const urlInput = document.getElementById('urlInput');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const mediaDetails = document.getElementById('mediaDetails');
    const mediaThumb = document.getElementById('mediaThumb');
    const mediaTitle = document.getElementById('mediaTitle');
    const qualitySelect = document.getElementById('qualitySelect');
    const audioFormatSelect = document.getElementById('audioFormatSelect');
    const downloadBtn = document.getElementById('downloadBtn');
    const progressCard = document.getElementById('progressCard');
    const progressBar = document.getElementById('progressBar');
    const statusText = document.getElementById('statusText');
    const percentText = document.getElementById('percentText');

    const tabDownloader = document.getElementById('tabDownloader');
    const tabWA = document.getElementById('tabWA');
    const downloaderSection = document.getElementById('downloaderSection');
    const waSection = document.getElementById('waSection');

    let currentMode = 'video';

    tabDownloader.addEventListener('click', () => {
        tabDownloader.classList.add('active'); tabWA.classList.remove('active');
        downloaderSection.classList.remove('hidden'); waSection.classList.add('hidden');
    });

    tabWA.addEventListener('click', () => {
        tabWA.classList.add('active'); tabDownloader.classList.remove('active');
        waSection.classList.remove('hidden'); downloaderSection.classList.add('hidden');
    });

    const urlParams = new URLSearchParams(window.location.search);
    const sharedUrl = urlParams.get('url');
    if (sharedUrl) {
        urlInput.value = sharedUrl;
        if (urlParams.get('auto') === 'true') triggerDownload(sharedUrl, 'video', 'Best Available', 'mp3');
        else analyzeUrl(sharedUrl);
    }

    async function analyzeUrl(url) {
        analyzeBtn.textContent = 'Analyzing...';
        try {
            const res = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            const data = await res.json();
            if (!data.success) throw new Error(data.error);

            mediaTitle.textContent = data.title;
            if (data.thumbnail) mediaThumb.src = data.thumbnail;
            qualitySelect.innerHTML = '';
            data.qualities.forEach(q => {
                const opt = document.createElement('option'); opt.value = q; opt.textContent = q;
                qualitySelect.appendChild(opt);
            });
            mediaDetails.classList.remove('hidden');
        } catch (err) { alert(err.message); }
        finally { analyzeBtn.textContent = 'Analyze Link'; }
    }

    analyzeBtn.addEventListener('click', () => analyzeUrl(urlInput.value.trim()));

    async function triggerDownload(url, mode, quality, audioFormat) {
        try {
            const res = await fetch('/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, mode, quality, audio_format: audioFormat })
            });
            const data = await res.json();
            if (!data.success) throw new Error(data.error);

            mediaDetails.classList.add('hidden');
            progressCard.classList.remove('hidden');
            pollProgress(data.job_id);
        } catch (err) { alert(err.message); }
    }

    downloadBtn.addEventListener('click', () => triggerDownload(urlInput.value.trim(), currentMode, qualitySelect.value, audioFormatSelect.value));

    function pollProgress(jobId) {
        const interval = setInterval(async () => {
            const res = await fetch(`/api/progress/${jobId}`);
            const data = await res.json();
            if (!data.success) return;

            statusText.textContent = data.message;
            percentText.textContent = `${data.progress}%`;
            progressBar.style.width = `${data.progress}%`;

            if (data.status === 'completed') {
                clearInterval(interval);
                window.location.href = `/api/files/${data.filename}`;
                setTimeout(() => progressCard.classList.add('hidden'), 2000);
            }
        }, 1000);
    }
});

