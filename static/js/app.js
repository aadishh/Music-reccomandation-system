class EmotionMusicApp {
    constructor() {
        this.video = document.getElementById('video');
        this.canvas = document.getElementById('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.stream = null;
        
        this.initializeElements();
        this.bindEvents();
        this.loadSettings();
    }
    
    initializeElements() {
        this.startCameraBtn = document.getElementById('startCamera');
        this.captureBtn = document.getElementById('captureBtn');
        this.stopCameraBtn = document.getElementById('stopCamera');
        this.loading = document.getElementById('loading');
        this.results = document.getElementById('results');
        this.emotionResult = document.getElementById('emotionResult');
        this.emotionScores = document.getElementById('emotionScores');
        this.playlistLink = document.getElementById('playlistLink');
        this.songsCount = document.getElementById('songsCount');
        this.songsBeforeRecheck = document.getElementById('songsBeforeRecheck');
        this.updateSettingsBtn = document.getElementById('updateSettings');
        this.resetCounterBtn = document.getElementById('resetCounter');
    }
    
    bindEvents() {
        this.startCameraBtn.addEventListener('click', () => this.startCamera());
        this.captureBtn.addEventListener('click', () => this.captureEmotion());
        this.stopCameraBtn.addEventListener('click', () => this.stopCamera());
        this.updateSettingsBtn.addEventListener('click', () => this.updateSettings());
        this.resetCounterBtn.addEventListener('click', () => this.resetCounter());
    }
    
    async startCamera() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ 
                video: { 
                    width: { ideal: 640 },
                    height: { ideal: 480 }
                } 
            });
            
            this.video.srcObject = this.stream;
            
            this.startCameraBtn.disabled = true;
            this.captureBtn.disabled = false;
            this.stopCameraBtn.disabled = false;
            
            console.log('Camera started successfully');
        } catch (error) {
            console.error('Error starting camera:', error);
            alert('Could not access camera. Please ensure camera permissions are granted.');
        }
    }
    
    stopCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        
        this.video.srcObject = null;
        this.startCameraBtn.disabled = false;
        this.captureBtn.disabled = true;
        this.stopCameraBtn.disabled = true;
        
        console.log('Camera stopped');
    }
    
    async captureEmotion() {
        try {
            // Show loading
            this.results.style.display = 'none';
            this.loading.style.display = 'block';
            this.captureBtn.disabled = true;
            
            // Capture image from video
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
            this.ctx.drawImage(this.video, 0, 0);
            
            // Convert to base64
            const imageData = this.canvas.toDataURL('image/jpeg', 0.8);
            
            // Send to server for analysis
            const response = await fetch('/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ image: imageData })
            });
            
            const result = await response.json();
            
            if (result.error) {
                throw new Error(result.error);
            }
            
            // Display results
            this.displayResults(result);
            
        } catch (error) {
            console.error('Error analyzing emotion:', error);
            alert('Failed to analyze emotion: ' + error.message);
        } finally {
            this.loading.style.display = 'none';
            this.captureBtn.disabled = false;
        }
    }
    
    displayResults(result) {
        // Display dominant emotion
        this.emotionResult.textContent = result.dominant_emotion;
        
        // Display emotion scores
        this.displayEmotionScores(result.emotion_scores);
        
        // Display playlist link
        if (result.playlist_url) {
            this.playlistLink.href = result.playlist_url;
            this.playlistLink.style.display = 'inline-block';
        }
        
        // Update song count
        this.songsCount.textContent = result.songs_played || 0;
        
        // Show results
        this.results.style.display = 'block';
        
        console.log('Emotion analysis result:', result);
    }
    
    displayEmotionScores(scores) {
        this.emotionScores.innerHTML = '';
        
        if (!scores || Object.keys(scores).length === 0) {
            this.emotionScores.innerHTML = '<p>No detailed scores available</p>';
            return;
        }
        
        // Sort emotions by score
        const sortedEmotions = Object.entries(scores)
            .sort(([,a], [,b]) => b - a);
        
        sortedEmotions.forEach(([emotion, score]) => {
            const scoreElement = document.createElement('div');
            scoreElement.className = 'emotion-score';
            
            const percentage = Math.round(score);
            
            scoreElement.innerHTML = `
                <span class="emotion-name">${emotion}</span>
                <div class="emotion-bar">
                    <div class="emotion-fill" style="width: ${percentage}%"></div>
                </div>
                <span class="emotion-value">${percentage}%</span>
            `;
            
            this.emotionScores.appendChild(scoreElement);
        });
    }
    
    async loadSettings() {
        try {
            const response = await fetch('/settings');
            const settings = await response.json();
            
            this.songsBeforeRecheck.value = settings.songs_before_recheck || 3;
            this.songsCount.textContent = settings.songs_played || 0;
            
            if (settings.current_emotion) {
                console.log('Current emotion:', settings.current_emotion);
            }
        } catch (error) {
            console.error('Error loading settings:', error);
        }
    }
    
    async updateSettings() {
        try {
            const songsBeforeRecheck = parseInt(this.songsBeforeRecheck.value);
            
            if (songsBeforeRecheck < 1 || songsBeforeRecheck > 10) {
                alert('Songs before recheck must be between 1 and 10');
                return;
            }
            
            const response = await fetch('/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    songs_before_recheck: songsBeforeRecheck
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert('Settings updated successfully!');
            } else {
                throw new Error('Failed to update settings');
            }
            
        } catch (error) {
            console.error('Error updating settings:', error);
            alert('Failed to update settings: ' + error.message);
        }
    }
    
    async resetCounter() {
        try {
            const response = await fetch('/reset', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.songsCount.textContent = '0';
                alert('Song counter reset successfully!');
            } else {
                throw new Error('Failed to reset counter');
            }
            
        } catch (error) {
            console.error('Error resetting counter:', error);
            alert('Failed to reset counter: ' + error.message);
        }
    }
}

// Initialize the app when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new EmotionMusicApp();
});