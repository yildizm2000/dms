#!/usr/bin/env python3
"""
Setup test script - bu script eğitim ortamının doğru kurulduğunu test eder
"""

import sys
import os
import json

# Proje kök dizinini ekle
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

def test_imports():
    """Gerekli kütüphanelerin yüklenebilirliğini test eder"""
    print("Testing imports...")
    
    try:
        import torch
        print(f"✓ PyTorch {torch.__version__}")
    except ImportError as e:
        print(f"✗ PyTorch import failed: {e}")
        return False
    
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        print(f"✓ Transformers imported successfully")
    except ImportError as e:
        print(f"✗ Transformers import failed: {e}")
        return False
    
    try:
        from datasets import load_dataset
        print(f"✓ Datasets imported successfully")
    except ImportError as e:
        print(f"✗ Datasets import failed: {e}")
        return False
    
    return True

def test_cuda():
    """CUDA kullanılabilirliğini test eder"""
    import torch
    
    print("\nTesting CUDA...")
    if torch.cuda.is_available():
        print(f"✓ CUDA is available")
        print(f"  - Device count: {torch.cuda.device_count()}")
        print(f"  - Current device: {torch.cuda.current_device()}")
        print(f"  - Device name: {torch.cuda.get_device_name()}")
    else:
        print("! CUDA is not available, will use CPU")
    
    return True

def test_config():
    """Config dosyasının varlığını ve geçerliliğini test eder"""
    print("\nTesting configuration...")
    
    config_path = os.path.join(project_root, 'config', 'config.json')
    
    if not os.path.exists(config_path):
        print(f"✗ Config file not found at: {config_path}")
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        required_keys = ['model_name', 'dataset_path', 'train_params']
        for key in required_keys:
            if key not in config:
                print(f"✗ Missing required key in config: {key}")
                return False
        
        print(f"✓ Config file is valid")
        print(f"  - Model: {config['model_name']}")
        print(f"  - Dataset: {config['dataset_path']}")
        
    except json.JSONDecodeError as e:
        print(f"✗ Config file is not valid JSON: {e}")
        return False
    
    return True

def test_dataset():
    """Dataset dosyasının varlığını test eder"""
    print("\nTesting dataset...")
    
    config_path = os.path.join(project_root, 'config', 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    dataset_path = os.path.join(project_root, config['dataset_path'])
    
    if not os.path.exists(dataset_path):
        print(f"✗ Dataset file not found at: {dataset_path}")
        return False
    
    # Dataset'in ilk birkaç satırını test et
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()[:3]
        
        for i, line in enumerate(lines):
            json.loads(line.strip())  # JSON geçerliliğini test et
        
        print(f"✓ Dataset file is valid ({len(lines)} sample lines checked)")
        
    except json.JSONDecodeError as e:
        print(f"✗ Dataset file contains invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"✗ Error reading dataset: {e}")
        return False
    
    return True

def test_directories():
    """Gerekli dizinlerin varlığını test eder"""
    print("\nTesting directories...")
    
    required_dirs = ['config', 'data', 'scripts', 'models', 'logs']
    
    for dir_name in required_dirs:
        dir_path = os.path.join(project_root, dir_name)
        if os.path.exists(dir_path):
            print(f"✓ {dir_name}/ directory exists")
        else:
            print(f"✗ {dir_name}/ directory missing")
            return False
    
    return True

def main():
    """Ana test fonksiyonu"""
    print("=== Training Setup Test ===\n")
    
    tests = [
        ("Imports", test_imports),
        ("CUDA", test_cuda),
        ("Directories", test_directories),
        ("Configuration", test_config),
        ("Dataset", test_dataset)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} Test ---")
        try:
            if test_func():
                passed += 1
            else:
                print(f"✗ {test_name} test failed")
        except Exception as e:
            print(f"✗ {test_name} test error: {e}")
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✓ All tests passed! Ready for training.")
        return True
    else:
        print("✗ Some tests failed. Please fix the issues before training.")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)