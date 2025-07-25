#!/usr/bin/env python3
"""
Simple script to test Ollama connection and setup
"""
import sys
import json
import subprocess
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
RECOMMENDED_MODELS = [
    "llama3.1:8b",      # Fastest, good for testing
    "llama3.1:70b",     # Best quality, slower
    "codellama:34b",    # Good for code generation
    "codellama:13b",    # Smaller code model
]

def check_ollama_running():
    """Check if Ollama service is running"""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if response.status_code == 200:
            logger.info("✅ Ollama service is running")
            return True
        else:
            logger.error(f"❌ Ollama service responded with status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to Ollama service")
        logger.info("Please start Ollama with: ollama serve")
        return False
    except Exception as e:
        logger.error(f"❌ Ollama connection error: {e}")
        return False

def list_available_models():
    """List models available in Ollama"""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        if response.status_code == 200:
            models = response.json().get("models", [])
            if models:
                logger.info("📋 Available models:")
                for model in models:
                    name = model.get("name", "unknown")
                    size = model.get("size", 0)
                    size_gb = size / (1024**3) if size > 0 else 0
                    logger.info(f"  - {name} ({size_gb:.1f}GB)")
                return [m["name"] for m in models]
            else:
                logger.warning("⚠️  No models installed")
                return []
        else:
            logger.error(f"❌ Failed to list models: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"❌ Error listing models: {e}")
        return []

def pull_model(model_name: str):
    """Pull a model from Ollama"""
    try:
        logger.info(f"⬇️  Pulling model {model_name}...")
        logger.info("This may take several minutes depending on model size...")
        
        response = requests.post(f"{OLLAMA_HOST}/api/pull", 
                               json={"name": model_name}, 
                               timeout=1800)  # 30 minutes timeout
        
        if response.status_code == 200:
            logger.info(f"✅ Successfully pulled model {model_name}")
            return True
        else:
            logger.error(f"❌ Failed to pull model {model_name}: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Error pulling model {model_name}: {e}")
        return False

def test_model_generation(model_name: str):
    """Test model generation with a simple prompt"""
    try:
        logger.info(f"🧪 Testing model {model_name}...")
        
        payload = {
            "model": model_name,
            "prompt": "What is AWS IAM? Answer in one sentence.",
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 100
            }
        }
        
        response = requests.post(f"{OLLAMA_HOST}/api/generate", 
                               json=payload, 
                               timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            generated_text = result.get("response", "").strip()
            logger.info(f"✅ Model {model_name} working correctly")
            logger.info(f"📝 Response: {generated_text}")
            return True
        else:
            logger.error(f"❌ Model {model_name} failed: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Error testing model {model_name}: {e}")
        return False

def check_system_resources():
    """Check system resources for model requirements"""
    try:
        import psutil
        
        # Check RAM
        memory = psutil.virtual_memory()
        total_gb = memory.total / (1024**3)
        available_gb = memory.available / (1024**3)
        
        logger.info(f"💾 System Memory: {total_gb:.1f}GB total, {available_gb:.1f}GB available")
        
        # Check disk space
        disk = psutil.disk_usage('/')
        free_gb = disk.free / (1024**3)
        
        logger.info(f"💿 Disk Space: {free_gb:.1f}GB free")
        
        # Recommend models based on available resources
        if available_gb >= 40:
            logger.info("🚀 Recommended: llama3.1:70b (best quality)")
        elif available_gb >= 20:
            logger.info("🚀 Recommended: codellama:34b or llama3.1:8b")
        elif available_gb >= 8:
            logger.info("🚀 Recommended: llama3.1:8b (fastest)")
        else:
            logger.warning("⚠️  Low memory - consider using smaller models")
        
        return True
    except ImportError:
        logger.info("📊 Install psutil for system resource info: pip install psutil")
        return False
    except Exception as e:
        logger.error(f"❌ Error checking system resources: {e}")
        return False

def main():
    """Main function to test Ollama setup"""
    logger.info("🔧 Testing Ollama setup for IAM Policy Repair...")
    logger.info("=" * 60)
    
    # Check if Ollama is running
    if not check_ollama_running():
        logger.info("\n📖 To start Ollama:")
        logger.info("1. Install Ollama: https://ollama.ai/")
        logger.info("2. Start service: ollama serve")
        logger.info("3. Run this test again")
        return False
    
    # Check system resources
    logger.info("\n🔍 Checking system resources...")
    check_system_resources()
    
    # List available models
    logger.info("\n📋 Checking available models...")
    available_models = list_available_models()
    
    # If no models available, suggest one
    if not available_models:
        logger.info("\n💡 No models found. Suggested setup:")
        logger.info("For testing: ollama pull llama3.1:8b")
        logger.info("For best results: ollama pull llama3.1:70b")
        logger.info("For code focus: ollama pull codellama:34b")
        
        # Ask user if they want to pull a model
        try:
            choice = input("\nWould you like to pull llama3.1:8b for testing? (y/n): ").lower()
            if choice == 'y':
                if pull_model("llama3.1:8b"):
                    available_models = ["llama3.1:8b"]
                else:
                    return False
            else:
                logger.info("Please manually pull a model with: ollama pull <model_name>")
                return False
        except KeyboardInterrupt:
            logger.info("\n👋 Setup cancelled")
            return False
    
    # Test the first available model
    if available_models:
        logger.info(f"\n🧪 Testing model generation...")
        test_model = available_models[0]
        if test_model_generation(test_model):
            logger.info(f"\n✅ Ollama setup complete!")
            logger.info(f"🎯 Ready to use model: {test_model}")
            logger.info(f"🔗 Ollama endpoint: {OLLAMA_HOST}")
            return True
        else:
            logger.error(f"\n❌ Model testing failed")
            return False
    
    return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)