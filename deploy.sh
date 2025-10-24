#!/bin/bash

echo "🚀 Emotion Music App - Deployment Helper"
echo "========================================"

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: app.py not found. Make sure you're in the project root directory."
    exit 1
fi

echo "✅ Project structure verified"

# Run deployment test
echo "🧪 Running deployment readiness test..."
python3 test_deployment.py

if [ $? -eq 0 ]; then
    echo ""
    echo "🎯 Deployment Summary:"
    echo "====================="
    echo "✅ Flexible TensorFlow versions (2.20.0+)"
    echo "✅ Fallback emotion detection system"
    echo "✅ TensorFlow warnings suppressed"
    echo "✅ Memory optimized build process"
    echo "✅ Extended timeout (300s) for ML loading"
    echo "✅ Graceful degradation if DeepFace fails"
    echo ""
    echo "🚀 Ready for deployment!"
    echo ""
    echo "📋 Deployment Options:"
    echo "1. Full ML: Uses DeepFace + TensorFlow (if available)"
    echo "2. Fallback: Uses lightweight emotion detection"
    echo "3. Both work with the same Spotify playlists!"
    echo ""
    echo "🔧 Next steps:"
    echo "git add ."
    echo "git commit -m 'Add fallback system for reliable deployment'"
    echo "git push"
    echo ""
    echo "💡 The app will automatically choose the best available detector!"
else
    echo ""
    echo "❌ Deployment test failed. Please check the errors above."
    exit 1
fi