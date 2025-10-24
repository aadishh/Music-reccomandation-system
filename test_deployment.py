#!/usr/bin/env python3
"""
Test script to verify deployment readiness
"""
import sys
import os

def test_imports():
    """Test all critical imports"""
    print("🧪 Testing imports...")
    
    try:
        import flask
        print("✅ Flask imported")
    except ImportError as e:
        print(f"❌ Flask failed: {e}")
        return False
    
    try:
        import cv2
        print("✅ OpenCV imported")
    except ImportError as e:
        print(f"❌ OpenCV failed: {e}")
        return False
    
    try:
        import numpy
        print("✅ NumPy imported")
    except ImportError as e:
        print(f"❌ NumPy failed: {e}")
        return False
    
    # Test TensorFlow/DeepFace (optional)
    try:
        import tensorflow as tf
        print(f"✅ TensorFlow {tf.__version__} imported")
        
        try:
            from deepface import DeepFace
            print("✅ DeepFace imported")
            deepface_available = True
        except ImportError as e:
            print(f"⚠️  DeepFace failed: {e}")
            deepface_available = False
    except ImportError as e:
        print(f"⚠️  TensorFlow failed: {e}")
        deepface_available = False
    
    # Test fallback
    if not deepface_available:
        try:
            from emotion_fallback import FallbackEmotionDetector
            print("✅ Fallback emotion detector available")
        except ImportError as e:
            print(f"❌ Fallback detector failed: {e}")
            return False
    
    return True

def test_app_startup():
    """Test if the app can start"""
    print("\n🚀 Testing app startup...")
    
    try:
        # Set environment variables
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
        
        # Import app
        from app import app, emotion_system
        print("✅ App imported successfully")
        
        # Test emotion system
        detector_type = "DeepFace" if hasattr(emotion_system, 'fallback_detector') else "Fallback"
        print(f"✅ Emotion system initialized with {detector_type}")
        
        return True
        
    except Exception as e:
        print(f"❌ App startup failed: {e}")
        return False

def main():
    print("🔍 Deployment Readiness Test")
    print("=" * 40)
    
    # Test imports
    imports_ok = test_imports()
    
    # Test app startup
    app_ok = test_app_startup()
    
    print("\n📊 Results:")
    print("=" * 40)
    
    if imports_ok and app_ok:
        print("✅ All tests passed! Ready for deployment")
        print("\n🚀 Next steps:")
        print("1. git add .")
        print("2. git commit -m 'Fix deployment with fallback system'")
        print("3. git push")
        print("4. Deploy on Render")
        return 0
    else:
        print("❌ Some tests failed. Check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())