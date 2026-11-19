/**
 * Unified Emotion Music Recommender Frontend Controller
 * Integrates HTML5 Audio Playback, DeepFace Emotion Capture, Multi-Provider Queuing & Licensing.
 */

class EmotionMusicApp {
    constructor() {
        this.csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
        
        // Audio playback state
        this.audio = document.getElementById('audioElement');
        this.queue = [];
        this.currentTrackIndex = -1;
        this.currentTrack = null;
        this.isPlaying = false;
        this.isMuted = false;
        this.previousVolume = 0.85;
        this.isShuffle = false;
        this.repeatMode = 'off'; // 'off' | 'all' | 'one'
        this.autoPlayNext = true;
        this.favoritesMap = new Map();
        this.likedTracks = new Set();
        this.dislikedTracks = new Set();
        this.retryAttempts = 0;

        // Camera & emotion state
        this.stream = null;
        this.video = document.getElementById('video');
        this.canvas = document.getElementById('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.isAutoCaptureRunning = false;
        this.autoCaptureTimer = null;
        this.songsPlayed = 0;
        this.songsBeforeRecheck = 3;
        this.autoCaptureIntervalSeconds = 30;
        this.currentEmotion = null;

        this.initDom();
        this.bindEvents();
        this.initPlayer();
        this.loadInitialData();
    }

    initDom() {
        // Camera & Emotion DOM
        this.cameraPlaceholder = document.getElementById('cameraPlaceholder');
        this.startCameraBtn = document.getElementById('startCamera');
        this.captureBtn = document.getElementById('captureBtn');
        this.autoCaptureBtn = document.getElementById('autoCapture');
        this.stopCameraBtn = document.getElementById('stopCamera');
        this.autoCaptureStatus = document.getElementById('autoCaptureStatus');
        this.loading = document.getElementById('loading');
        this.loadingMessage = document.getElementById('loadingMessage');
        this.emotionResultsCard = document.getElementById('emotionResultsCard');
        this.emotionResult = document.getElementById('emotionResult');
        this.emotionConfidence = document.getElementById('emotionConfidence');
        this.emotionScores = document.getElementById('emotionScores');
        
        // Recommendation settings DOM
        this.recModeSelect = document.getElementById('recModeSelect');
        this.modeDescription = document.getElementById('modeDescription');
        this.userMoodOverride = document.getElementById('userMoodOverride');
        this.genreFilter = document.getElementById('genreFilter');
        this.providerFilter = document.getElementById('providerFilter');
        this.refreshRecsBtn = document.getElementById('refreshRecsBtn');

        // Player DOM
        this.currentProviderBadge = document.getElementById('currentProviderBadge');
        this.trackArtwork = document.getElementById('trackArtwork');
        this.currentTrackTitle = document.getElementById('currentTrackTitle');
        this.currentTrackArtist = document.getElementById('currentTrackArtist');
        this.metaGenre = document.getElementById('metaGenre');
        this.metaBpm = document.getElementById('metaBpm');
        this.metaEnergy = document.getElementById('metaEnergy');
        this.licenseBadge = document.getElementById('licenseBadge');
        this.attributionText = document.getElementById('attributionText');
        this.currentTimeEl = document.getElementById('currentTime');
        this.totalDurationEl = document.getElementById('totalDuration');
        this.progressBar = document.getElementById('progressBar');
        this.playerAlert = document.getElementById('playerAlert');

        // Player Controls DOM
        this.shuffleBtn = document.getElementById('shuffleBtn');
        this.prevBtn = document.getElementById('prevBtn');
        this.playPauseBtn = document.getElementById('playPauseBtn');
        this.nextBtn = document.getElementById('nextBtn');
        this.repeatBtn = document.getElementById('repeatBtn');
        this.muteBtn = document.getElementById('muteBtn');
        this.volumeBar = document.getElementById('volumeBar');
        this.likeBtn = document.getElementById('likeBtn');
        this.dislikeBtn = document.getElementById('dislikeBtn');
        this.favBtn = document.getElementById('favBtn');

        // Tabs & Lists DOM
        this.tabBtns = document.querySelectorAll('.tab-btn');
        this.tabContents = document.querySelectorAll('.tab-content');
        this.queueCount = document.getElementById('queueCount');
        this.favCount = document.getElementById('favCount');
        this.historyCount = document.getElementById('historyCount');
        this.recProfileSummary = document.getElementById('recProfileSummary');
        this.queueList = document.getElementById('queueList');
        this.clearQueueBtn = document.getElementById('clearQueueBtn');
        this.searchInput = document.getElementById('searchInput');
        this.searchBtn = document.getElementById('searchBtn');
        this.searchResultsList = document.getElementById('searchResultsList');
        this.favoritesList = document.getElementById('favoritesList');
        this.refreshFavsBtn = document.getElementById('refreshFavsBtn');
        this.historyList = document.getElementById('historyList');
        this.refreshHistoryBtn = document.getElementById('refreshHistoryBtn');

        // Settings DOM
        this.songsBeforeRecheckInput = document.getElementById('songsBeforeRecheck');
        this.autoCaptureIntervalInput = document.getElementById('autoCaptureInterval');
        this.autoPlayNextCheckbox = document.getElementById('autoPlayNext');
        this.updateSettingsBtn = document.getElementById('updateSettings');
        this.resetCounterBtn = document.getElementById('resetCounter');
        this.songsCountEl = document.getElementById('songsCount');
        this.activeProvidersBadge = document.getElementById('activeProvidersBadge');
    }

    bindEvents() {
        // Camera controls
        this.startCameraBtn.addEventListener('click', () => this.startCamera());
        this.captureBtn.addEventListener('click', () => this.captureEmotion());
        this.autoCaptureBtn.addEventListener('click', () => this.toggleAutoCapture());
        this.stopCameraBtn.addEventListener('click', () => this.stopCamera());

        // Recommendation preference controls
        this.recModeSelect.addEventListener('change', () => this.onRecModeChange());
        this.refreshRecsBtn.addEventListener('click', () => this.fetchRecommendations());

        // Audio player controls
        this.playPauseBtn.addEventListener('click', () => this.togglePlayPause());
        this.prevBtn.addEventListener('click', () => this.playPrevious());
        this.nextBtn.addEventListener('click', () => this.playNext());
        this.shuffleBtn.addEventListener('click', () => this.toggleShuffle());
        this.repeatBtn.addEventListener('click', () => this.cycleRepeat());
        this.muteBtn.addEventListener('click', () => this.toggleMute());
        this.volumeBar.addEventListener('input', (e) => this.setVolume(parseFloat(e.target.value)));
        this.progressBar.addEventListener('input', (e) => this.seekAudio(parseFloat(e.target.value)));

        // Feedback & Favorite buttons
        this.likeBtn.addEventListener('click', () => this.toggleFeedback('like'));
        this.dislikeBtn.addEventListener('click', () => this.toggleFeedback('dislike'));
        this.favBtn.addEventListener('click', () => this.toggleCurrentFavorite());

        // Audio element lifecycle events
        this.audio.addEventListener('timeupdate', () => this.onAudioTimeUpdate());
        this.audio.addEventListener('loadedmetadata', () => this.onAudioLoadedMetadata());
        this.audio.addEventListener('ended', () => this.onAudioEnded());
        this.audio.addEventListener('error', (e) => this.onAudioError(e));

        // Tab navigation
        this.tabBtns.forEach(btn => {
            btn.addEventListener('click', () => this.switchTab(btn.dataset.tab));
        });

        // Tab list buttons
        this.clearQueueBtn.addEventListener('click', () => this.clearQueue());
        this.searchBtn.addEventListener('click', () => this.performSearch());
        this.searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.performSearch();
        });
        this.refreshFavsBtn.addEventListener('click', () => this.loadFavorites());
        this.refreshHistoryBtn.addEventListener('click', () => this.loadHistory());

        // Settings buttons
        this.updateSettingsBtn.addEventListener('click', () => this.saveSettings());
        this.resetCounterBtn.addEventListener('click', () => this.resetCounter());
        this.autoPlayNextCheckbox.addEventListener('change', (e) => {
            this.autoPlayNext = e.target.checked;
        });
    }

    initPlayer() {
        this.audio.volume = parseFloat(this.volumeBar.value) || 0.85;
        this.updateRepeatButton();
        this.updateShuffleButton();
    }

    async loadInitialData() {
        await Promise.allSettled([
            this.loadProvidersStatus(),
            this.loadSettings(),
            this.loadFavorites(),
            this.loadHistory()
        ]);
    }

    // --- Headers & CSRF Utility ---

    getHeaders(extra = {}) {
        const headers = { 'Accept': 'application/json', ...extra };
        if (this.csrfToken) {
            headers['X-CSRF-Token'] = this.csrfToken;
        }
        return headers;
    }

    // --- Providers Health & Status ---

    async loadProvidersStatus() {
        try {
            const res = await fetch('/api/music/providers', { headers: this.getHeaders() });
            if (!res.ok) return;
            const data = await res.json();
            const providers = data.providers || [];
            const healthy = providers.filter(p => p.healthy).map(p => p.provider);
            if (healthy.length > 0) {
                this.activeProvidersBadge.textContent = `Providers: ${healthy.join(', ')}`;
                this.activeProvidersBadge.style.color = '#4cd964';
            } else {
                this.activeProvidersBadge.textContent = 'Providers: 0 active';
                this.activeProvidersBadge.style.color = '#ffc107';
            }
        } catch (err) {
            console.warn('Could not fetch provider status:', err);
        }
    }

    // --- Camera & Emotion Pipeline ---

    async startCamera() {
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('Camera access is not supported by your browser.');
            }
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
            });
            this.video.srcObject = this.stream;
            this.video.style.display = 'block';
            this.cameraPlaceholder.style.display = 'none';

            await new Promise(resolve => {
                this.video.onloadedmetadata = () => {
                    this.video.play();
                    resolve();
                };
            });

            this.startCameraBtn.disabled = true;
            this.captureBtn.disabled = false;
            this.autoCaptureBtn.disabled = false;
            this.stopCameraBtn.disabled = false;
        } catch (err) {
            alert(`Camera error: ${err.message}`);
        }
    }

    stopCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(t => t.stop());
            this.stream = null;
        }
        this.video.srcObject = null;
        this.video.style.display = 'none';
        this.cameraPlaceholder.style.display = 'block';

        this.startCameraBtn.disabled = false;
        this.captureBtn.disabled = true;
        this.autoCaptureBtn.disabled = true;
        this.stopCameraBtn.disabled = true;

        if (this.isAutoCaptureRunning) {
            this.toggleAutoCapture();
        }
    }

    async captureEmotion() {
        try {
            this.loading.style.display = 'block';
            this.loadingMessage.textContent = 'Analyzing facial emotion...';
            this.captureBtn.disabled = true;

            this.canvas.width = this.video.videoWidth || 640;
            this.canvas.height = this.video.videoHeight || 480;
            this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
            const imageData = this.canvas.toDataURL('image/jpeg', 0.85);

            const genres = this.genreFilter.value.split(',').map(s => s.trim()).filter(Boolean);
            const payload = {
                image: imageData,
                mode: this.recModeSelect.value,
                mood: this.userMoodOverride.value || null,
                genres: genres,
                providers: this.providerFilter.value ? [this.providerFilter.value] : null,
                limit: 15
            };

            const response = await fetch('/analyze', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify(payload)
            });

            const result = await response.json();
            if (result.error) throw new Error(result.error);

            this.displayEmotionResult(result);

            const tracks = result.recommended_tracks || (result.recommendations && result.recommendations.tracks) || [];
            if (tracks.length > 0) {
                this.loadQueue(tracks, true);
                if (result.recommendations && result.recommendations.target_profile) {
                    const prof = result.recommendations.target_profile;
                    this.recProfileSummary.textContent = `Mode: ${result.recommendations.mode} &bull; Target Mood: ${prof.target_mood}`;
                }
            } else {
                this.showPlayerAlert('No playable tracks found for current filters and licensing mode.', 'warning');
            }

            this.songsPlayed = result.songs_played || (this.songsPlayed + 1);
            this.songsCountEl.textContent = this.songsPlayed;

        } catch (err) {
            console.error('Capture failed:', err);
            alert(`Emotion analysis failed: ${err.message}`);
        } finally {
            this.loading.style.display = 'none';
            this.captureBtn.disabled = false;
        }
    }

    displayEmotionResult(result) {
        this.currentEmotion = result.dominant_emotion || 'neutral';
        this.emotionResult.textContent = this.currentEmotion;
        this.emotionConfidence.textContent = `${Math.round(result.confidence || 0)}%`;
        this.emotionResultsCard.style.display = 'block';

        this.emotionScores.innerHTML = '';
        const scores = result.emotion_scores || {};
        const sorted = Object.entries(scores).sort(([, a], [, b]) => b - a);

        sorted.forEach(([emotion, val]) => {
            const pct = Math.round(val);
            const row = document.createElement('div');
            row.className = 'emotion-score';
            row.innerHTML = `
                <span class="emotion-name">${emotion}</span>
                <div class="emotion-bar">
                    <div class="emotion-fill" style="width: ${pct}%"></div>
                </div>
                <span class="emotion-value">${pct}%</span>
            `;
            this.emotionScores.appendChild(row);
        });
    }

    async toggleAutoCapture() {
        try {
            const nextState = !this.isAutoCaptureRunning;
            const res = await fetch('/auto-capture', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ enable: nextState })
            });
            const data = await res.json();
            if (!data.success) throw new Error(data.error || 'Failed to toggle auto-capture');

            this.isAutoCaptureRunning = data.auto_capture_enabled;
            if (this.isAutoCaptureRunning) {
                this.autoCaptureBtn.textContent = 'Stop Auto-Capture';
                this.autoCaptureBtn.className = 'btn btn-danger';
                this.autoCaptureStatus.style.display = 'block';
                this.captureBtn.disabled = true;

                const intervalMs = (data.interval_seconds || this.autoCaptureIntervalSeconds) * 1000;
                this.autoCaptureTimer = setInterval(() => {
                    if (this.stream && !this.loading.offsetParent) {
                        this.captureEmotion();
                    }
                }, intervalMs);
            } else {
                this.autoCaptureBtn.textContent = 'Start Auto-Capture';
                this.autoCaptureBtn.className = 'btn btn-warning';
                this.autoCaptureStatus.style.display = 'none';
                this.captureBtn.disabled = false;
                if (this.autoCaptureTimer) {
                    clearInterval(this.autoCaptureTimer);
                    this.autoCaptureTimer = null;
                }
            }
        } catch (err) {
            alert(`Auto-capture error: ${err.message}`);
        }
    }

    onRecModeChange() {
        const mode = this.recModeSelect.value;
        if (mode === 'mood_shifting') {
            this.modeDescription.textContent = 'Applies iso-principle transition to guide you toward calm or uplifting states.';
        } else {
            this.modeDescription.textContent = 'Matches musical BPM, energy, and mood tags directly to your detected state.';
        }
    }

    async fetchRecommendations() {
        try {
            this.loading.style.display = 'block';
            this.loadingMessage.textContent = 'Refreshing recommendations...';

            const emotion = this.currentEmotion || 'neutral';
            const params = new URLSearchParams({
                emotion: emotion,
                mode: this.recModeSelect.value,
                limit: '15'
            });
            if (this.userMoodOverride.value) {
                params.set('mood', this.userMoodOverride.value);
            }
            if (this.genreFilter.value) {
                params.set('genres', this.genreFilter.value);
            }
            if (this.providerFilter.value) {
                params.set('providers', this.providerFilter.value);
            }

            const res = await fetch(`/api/music/recommendations?${params.toString()}`, {
                headers: this.getHeaders()
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);

            this.loadQueue(data.tracks || [], true);
            if (data.target_profile) {
                this.recProfileSummary.textContent = `Mode: ${data.mode} &bull; Target Mood: ${data.target_profile.target_mood}`;
            }
        } catch (err) {
            alert(`Could not fetch recommendations: ${err.message}`);
        } finally {
            this.loading.style.display = 'none';
        }
    }

    // --- Audio Player Engine ---

    loadQueue(tracks, autoPlayFirst = false) {
        this.queue = tracks || [];
        this.queueCount.textContent = this.queue.length;
        this.renderTrackList(this.queueList, this.queue, (track, idx) => {
            this.playTrackAtIndex(idx);
        });

        if (autoPlayFirst && this.queue.length > 0) {
            this.playTrackAtIndex(0);
        }
    }

    clearQueue() {
        this.queue = [];
        this.currentTrackIndex = -1;
        this.queueCount.textContent = '0';
        this.renderTrackList(this.queueList, [], null);
        this.audio.pause();
        this.audio.src = '';
        this.isPlaying = false;
        this.updatePlayPauseButton();
    }

    async playTrackAtIndex(index) {
        if (index < 0 || index >= this.queue.length) return;
        this.currentTrackIndex = index;
        const track = this.queue[index];
        await this.loadAndPlayTrack(track);
    }

    async loadAndPlayTrack(track) {
        this.currentTrack = track;
        this.retryAttempts = 0;
        this.clearPlayerAlert();
        this.updateNowPlayingUI(track);

        try {
            // Obtain fresh, authorized playback URL and verify licensing via backend
            const playbackRes = await fetch(`/api/music/playback/${encodeURIComponent(track.internal_id)}?refresh=true&record_history=true`, {
                headers: this.getHeaders()
            });

            if (!playbackRes.ok) {
                const errData = await playbackRes.json();
                throw new Error(errData.error || `Playback authorization failed (${playbackRes.status})`);
            }

            const playbackInfo = await playbackRes.json();
            if (!playbackInfo.playback_url) {
                throw new Error('Provider returned no streamable audio URL.');
            }

            this.audio.src = playbackInfo.playback_url;
            await this.audio.play();
            this.isPlaying = true;
            this.updatePlayPauseButton();
            this.highlightCurrentPlayingItem();

            // Refresh history count after recording play
            this.loadHistory();

        } catch (err) {
            console.error('Playback error:', err);
            this.showPlayerAlert(`Cannot play '${track.title}': ${err.message}`, 'error');
            
            // Advance to next track automatically after a brief pause
            if (this.autoPlayNext && this.queue.length > 1) {
                setTimeout(() => this.playNext(), 1800);
            }
        }
    }

    togglePlayPause() {
        if (!this.audio.src) {
            if (this.queue.length > 0) {
                this.playTrackAtIndex(0);
            }
            return;
        }

        if (this.audio.paused) {
            this.audio.play().then(() => {
                this.isPlaying = true;
                this.updatePlayPauseButton();
            }).catch(err => {
                console.error('Play failed:', err);
            });
        } else {
            this.audio.pause();
            this.isPlaying = false;
            this.updatePlayPauseButton();
        }
    }

    playNext() {
        if (this.queue.length === 0) return;
        if (this.repeatMode === 'one') {
            this.audio.currentTime = 0;
            this.audio.play();
            return;
        }

        let nextIdx = this.currentTrackIndex + 1;
        if (this.isShuffle) {
            nextIdx = Math.floor(Math.random() * this.queue.length);
        } else if (nextIdx >= this.queue.length) {
            if (this.repeatMode === 'all') {
                nextIdx = 0;
            } else {
                return;
            }
        }
        this.playTrackAtIndex(nextIdx);
    }

    playPrevious() {
        if (this.queue.length === 0) return;
        if (this.audio.currentTime > 3) {
            this.audio.currentTime = 0;
            return;
        }
        let prevIdx = this.currentTrackIndex - 1;
        if (prevIdx < 0) {
            prevIdx = this.queue.length - 1;
        }
        this.playTrackAtIndex(prevIdx);
    }

    seekAudio(percent) {
        if (this.audio.duration && !isNaN(this.audio.duration)) {
            this.audio.currentTime = (percent / 100) * this.audio.duration;
        }
    }

    setVolume(value) {
        this.audio.volume = Math.max(0, Math.min(1, value));
        if (this.audio.volume === 0) {
            this.muteBtn.textContent = '🔇';
            this.isMuted = true;
        } else {
            this.muteBtn.textContent = '🔊';
            this.isMuted = false;
        }
    }

    toggleMute() {
        if (this.isMuted) {
            this.setVolume(this.previousVolume || 0.85);
            this.volumeBar.value = this.audio.volume;
        } else {
            this.previousVolume = this.audio.volume;
            this.setVolume(0);
            this.volumeBar.value = 0;
        }
    }

    toggleShuffle() {
        this.isShuffle = !this.isShuffle;
        this.updateShuffleButton();
    }

    cycleRepeat() {
        const modes = ['off', 'all', 'one'];
        const currentIdx = modes.indexOf(this.repeatMode);
        this.repeatMode = modes[(currentIdx + 1) % modes.length];
        this.updateRepeatButton();
    }

    updateShuffleButton() {
        this.shuffleBtn.classList.toggle('active', this.isShuffle);
        this.shuffleBtn.title = `Shuffle: ${this.isShuffle ? 'On' : 'Off'}`;
    }

    updateRepeatButton() {
        this.repeatBtn.classList.toggle('active', this.repeatMode !== 'off');
        if (this.repeatMode === 'one') {
            this.repeatBtn.textContent = '🔂';
            this.repeatBtn.title = 'Repeat: Current Track';
        } else if (this.repeatMode === 'all') {
            this.repeatBtn.textContent = '🔁';
            this.repeatBtn.title = 'Repeat: Entire Queue';
        } else {
            this.repeatBtn.textContent = '🔁';
            this.repeatBtn.title = 'Repeat: Off';
        }
    }

    updatePlayPauseButton() {
        this.playPauseBtn.textContent = this.isPlaying ? '⏸' : '▶';
        this.playPauseBtn.title = this.isPlaying ? 'Pause' : 'Play';
    }

    onAudioTimeUpdate() {
        if (!this.audio.duration || isNaN(this.audio.duration)) return;
        const cur = this.audio.currentTime;
        const dur = this.audio.duration;
        const pct = (cur / dur) * 100;
        this.progressBar.value = pct;
        this.currentTimeEl.textContent = this.formatTime(cur);
    }

    onAudioLoadedMetadata() {
        this.totalDurationEl.textContent = this.formatTime(this.audio.duration);
    }

    onAudioEnded() {
        this.isPlaying = false;
        this.updatePlayPauseButton();
        if (this.autoPlayNext) {
            this.playNext();
        }
    }

    async onAudioError(e) {
        console.warn('Audio element error:', e);
        if (this.currentTrack && this.retryAttempts < 1) {
            this.retryAttempts++;
            this.showPlayerAlert('Playback stream expired. Refreshing authorized stream...', 'warning');
            try {
                const refreshed = await fetch(`/api/music/playback/${encodeURIComponent(this.currentTrack.internal_id)}?refresh=true`, {
                    headers: this.getHeaders()
                });
                if (refreshed.ok) {
                    const info = await refreshed.json();
                    if (info.playback_url) {
                        this.audio.src = info.playback_url;
                        await this.audio.play();
                        this.isPlaying = true;
                        this.updatePlayPauseButton();
                        this.clearPlayerAlert();
                        return;
                    }
                }
            } catch (err) {
                console.error('Stream refresh failed:', err);
            }
        }

        this.showPlayerAlert('Playback stream failed or was blocked by provider licensing.', 'error');
        if (this.autoPlayNext && this.queue.length > 1) {
            setTimeout(() => this.playNext(), 1600);
        }
    }

    updateNowPlayingUI(track) {
        this.currentTrackTitle.textContent = track.title || 'Untitled Track';
        this.currentTrackArtist.textContent = track.artist || 'Unknown Artist';
        this.metaGenre.textContent = track.genre ? `Genre: ${track.genre}` : '';
        this.metaBpm.textContent = track.bpm ? `&bull; ${Math.round(track.bpm)} BPM` : '';
        this.metaEnergy.textContent = (track.energy !== null && track.energy !== undefined) ? `&bull; Energy: ${Math.round(track.energy * 100)}%` : '';

        this.currentProviderBadge.textContent = track.provider.toUpperCase();
        this.currentProviderBadge.className = `badge badge-provider ${track.provider.toLowerCase()}`;

        if (track.artwork) {
            this.trackArtwork.src = track.artwork;
        } else {
            this.trackArtwork.src = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120' viewBox='0 0 120 120'%3E%3Crect width='120' height='120' fill='%23333'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23888' font-size='32'%3E%E2%99%AC%3C/text%3E%3C/svg%3E";
        }

        const lic = track.licensing || {};
        this.licenseBadge.textContent = lic.license_type || 'Standard';
        this.attributionText.textContent = lic.attribution_text || '';

        // Update feedback & favorite button states
        this.likeBtn.classList.toggle('active', this.likedTracks.has(track.internal_id));
        this.dislikeBtn.classList.toggle('active', this.dislikedTracks.has(track.internal_id));
        this.favBtn.classList.toggle('active', this.favoritesMap.has(track.internal_id));
    }

    highlightCurrentPlayingItem() {
        const items = document.querySelectorAll('.track-item');
        items.forEach(el => {
            el.classList.toggle('playing', el.dataset.trackId === (this.currentTrack && this.currentTrack.internal_id));
        });
    }

    showPlayerAlert(msg, type = 'warning') {
        this.playerAlert.textContent = msg;
        this.playerAlert.className = `player-alert ${type}`;
        this.playerAlert.style.display = 'block';
    }

    clearPlayerAlert() {
        this.playerAlert.style.display = 'none';
        this.playerAlert.textContent = '';
    }

    formatTime(sec) {
        if (!sec || isNaN(sec)) return '0:00';
        const mins = Math.floor(sec / 60);
        const rem = Math.floor(sec % 60);
        return `${mins}:${rem < 10 ? '0' : ''}${rem}`;
    }

    // --- Feedback & Favorites ---

    async toggleFeedback(type) {
        if (!this.currentTrack) return;
        const trackId = this.currentTrack.internal_id;
        const currentActive = (type === 'like' && this.likedTracks.has(trackId)) ||
                              (type === 'dislike' && this.dislikedTracks.has(trackId));
        const feedbackValue = currentActive ? 'neutral' : type;

        try {
            const res = await fetch('/api/music/feedback', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    track_id: trackId,
                    feedback: feedbackValue,
                    artist: this.currentTrack.artist,
                    genre: this.currentTrack.genre
                })
            });
            const data = await res.json();
            if (!data.success) throw new Error(data.error);

            if (feedbackValue === 'like') {
                this.likedTracks.add(trackId);
                this.dislikedTracks.delete(trackId);
            } else if (feedbackValue === 'dislike') {
                this.dislikedTracks.add(trackId);
                this.likedTracks.delete(trackId);
                // Disliked track is automatically skipped
                if (this.autoPlayNext) this.playNext();
            } else {
                this.likedTracks.delete(trackId);
                this.dislikedTracks.delete(trackId);
            }

            this.likeBtn.classList.toggle('active', this.likedTracks.has(trackId));
            this.dislikeBtn.classList.toggle('active', this.dislikedTracks.has(trackId));
        } catch (err) {
            alert(`Feedback failed: ${err.message}`);
        }
    }

    async toggleCurrentFavorite() {
        if (!this.currentTrack) return;
        await this.toggleFavorite(this.currentTrack);
        this.favBtn.classList.toggle('active', this.favoritesMap.has(this.currentTrack.internal_id));
    }

    async toggleFavorite(track) {
        const isFav = this.favoritesMap.has(track.internal_id);
        const nextState = !isFav;

        try {
            const res = await fetch('/api/music/favorites', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    track_id: track.internal_id,
                    is_favorite: nextState,
                    track: track
                })
            });
            const data = await res.json();
            if (!data.success) throw new Error(data.error);

            if (nextState) {
                this.favoritesMap.set(track.internal_id, track);
            } else {
                this.favoritesMap.delete(track.internal_id);
            }
            this.favCount.textContent = this.favoritesMap.size;
            this.renderTrackList(this.favoritesList, Array.from(this.favoritesMap.values()), (t) => {
                this.loadQueue([t], true);
            });
        } catch (err) {
            alert(`Could not update favorites: ${err.message}`);
        }
    }

    async loadFavorites() {
        try {
            const res = await fetch('/api/music/favorites', { headers: this.getHeaders() });
            if (!res.ok) return;
            const data = await res.json();
            this.favoritesMap.clear();
            (data.favorites || []).forEach(item => {
                if (item.track && item.track_id) {
                    this.favoritesMap.set(item.track_id, item.track);
                }
            });
            this.favCount.textContent = this.favoritesMap.size;
            this.renderTrackList(this.favoritesList, Array.from(this.favoritesMap.values()), (t) => {
                this.loadQueue([t], true);
            });
        } catch (err) {
            console.warn('Could not load favorites:', err);
        }
    }

    async loadHistory() {
        try {
            const res = await fetch('/api/music/history', { headers: this.getHeaders() });
            if (!res.ok) return;
            const data = await res.json();
            const history = data.history || [];
            this.historyCount.textContent = history.length;
            const tracks = history.map(h => h.track || {
                internal_id: h.track_id,
                provider: h.provider,
                title: h.title,
                artist: h.artist,
                genre: h.genre
            });
            this.renderTrackList(this.historyList, tracks, (t) => {
                this.loadQueue([t], true);
            });
        } catch (err) {
            console.warn('Could not load history:', err);
        }
    }

    // --- Search Tab ---

    async performSearch() {
        const query = this.searchInput.value.trim();
        if (!query) return;

        try {
            this.searchResultsList.innerHTML = '<li class="empty-list-message">Searching multi-provider catalog...</li>';
            const params = new URLSearchParams({ q: query, limit: '20' });
            if (this.providerFilter.value) {
                params.set('provider', this.providerFilter.value);
            }
            const res = await fetch(`/api/music/search?${params.toString()}`, { headers: this.getHeaders() });
            const data = await res.json();
            if (data.error) throw new Error(data.error);

            const tracks = data.tracks || [];
            if (tracks.length === 0) {
                this.searchResultsList.innerHTML = `<li class="empty-list-message">No matching playable tracks found for '${query}'.</li>`;
                return;
            }

            this.renderTrackList(this.searchResultsList, tracks, (track) => {
                // Add to current queue and play immediately
                this.queue.push(track);
                this.queueCount.textContent = this.queue.length;
                this.renderTrackList(this.queueList, this.queue, (t, i) => this.playTrackAtIndex(i));
                this.playTrackAtIndex(this.queue.length - 1);
            });
        } catch (err) {
            this.searchResultsList.innerHTML = `<li class="empty-list-message error">Search failed: ${err.message}</li>`;
        }
    }

    // --- Tab Rendering ---

    switchTab(tabId) {
        this.tabBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tabId));
        this.tabContents.forEach(content => content.classList.toggle('active', content.id === tabId));
    }

    renderTrackList(ulElement, tracks, onPlayClick) {
        ulElement.innerHTML = '';
        if (!tracks || tracks.length === 0) {
            ulElement.innerHTML = '<li class="empty-list-message">No tracks to display.</li>';
            return;
        }

        tracks.forEach((track, idx) => {
            const li = document.createElement('li');
            li.className = 'track-item';
            li.dataset.trackId = track.internal_id;
            if (this.currentTrack && this.currentTrack.internal_id === track.internal_id) {
                li.classList.add('playing');
            }

            const artworkSrc = track.artwork || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='44' height='44' viewBox='0 0 44 44'%3E%3Crect width='44' height='44' fill='%23222'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23666' font-size='16'%3E%E2%99%AC%3C/text%3E%3C/svg%3E";
            const providerName = (track.provider || 'music').toLowerCase();

            li.innerHTML = `
                <button class="btn-play-track" title="Play Track">▶</button>
                <img src="${artworkSrc}" alt="Artwork" class="track-item-artwork" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'44\\' height=\\'44\\'%3E%3Crect width=\\'44\\' height=\\'44\\' fill=\\'%23222\\'/ %3E%3C/svg%3E'">
                <div class="track-item-info">
                    <div class="track-item-title">${this.escapeHtml(track.title || 'Untitled')}</div>
                    <div class="track-item-artist">${this.escapeHtml(track.artist || 'Unknown')}</div>
                    <div class="track-item-tags">
                        <span class="badge badge-provider ${providerName}">${providerName}</span>
                        ${track.genre ? `<span class="badge badge-license">${this.escapeHtml(track.genre)}</span>` : ''}
                    </div>
                </div>
                <div class="track-item-actions">
                    <button class="btn-icon-small btn-fav-item ${this.favoritesMap.has(track.internal_id) ? 'active' : ''}" title="Favorite">❤️</button>
                </div>
            `;

            li.querySelector('.btn-play-track').addEventListener('click', () => {
                if (onPlayClick) onPlayClick(track, idx);
            });

            li.querySelector('.btn-fav-item').addEventListener('click', async (e) => {
                e.stopPropagation();
                await this.toggleFavorite(track);
                li.querySelector('.btn-fav-item').classList.toggle('active', this.favoritesMap.has(track.internal_id));
            });

            ulElement.appendChild(li);
        });
    }

    escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // --- Settings Storage ---

    async loadSettings() {
        try {
            const res = await fetch('/settings', { headers: this.getHeaders() });
            if (!res.ok) return;
            const data = await res.json();
            this.songsBeforeRecheck = data.songs_before_recheck || 3;
            this.songsBeforeRecheckInput.value = this.songsBeforeRecheck;
            this.songsPlayed = data.songs_played || 0;
            this.songsCountEl.textContent = this.songsPlayed;
            if (data.auto_capture_interval) {
                this.autoCaptureIntervalSeconds = data.auto_capture_interval;
                this.autoCaptureIntervalInput.value = this.autoCaptureIntervalSeconds;
            }
        } catch (err) {
            console.warn('Could not load settings:', err);
        }
    }

    async saveSettings() {
        try {
            const recheck = parseInt(this.songsBeforeRecheckInput.value, 10);
            const interval = parseInt(this.autoCaptureIntervalInput.value, 10);
            const res = await fetch('/settings', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    songs_before_recheck: recheck,
                    auto_capture_interval: interval
                })
            });
            const data = await res.json();
            if (data.success) {
                this.songsBeforeRecheck = recheck;
                this.autoCaptureIntervalSeconds = interval;
                alert('Settings updated successfully!');
            }
        } catch (err) {
            alert(`Failed to save settings: ${err.message}`);
        }
    }

    async resetCounter() {
        try {
            const res = await fetch('/reset', {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' })
            });
            const data = await res.json();
            if (data.success) {
                this.songsPlayed = 0;
                this.songsCountEl.textContent = '0';
                alert('Song counter reset.');
            }
        } catch (err) {
            alert(`Failed to reset counter: ${err.message}`);
        }
    }
}

// Instantiate on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    window.emotionMusicApp = new EmotionMusicApp();
});
