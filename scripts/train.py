import sys
import os
import json
import torch
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    set_seed
)
from datasets import load_dataset
from dotenv import load_dotenv
import logging

# Logging ayarı
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PROJE KÖK DİZİNİNİ PATH'E EKLE
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Çevresel değişkenler
load_dotenv()

def load_config():
    """Yapılandırma dosyasını kesin olarak bulur ve yükler"""
    # Proje kök dizinini kesin olarak belirle
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..'))
    
    # Denenecek kesin yollar
    config_locations = [
        os.path.join(project_root, 'config', 'config.json'),  # Önerilen standart konum
        os.path.join(project_root, 'config.json'),           # Kök dizinde
        os.path.join(script_dir, 'config.json')             # Script yanında
    ]
    
    for config_path in config_locations:
        if os.path.exists(config_path):
            print(f"Config dosyası bulundu: {config_path}")  # Debug mesajı
            with open(config_path, 'r') as f:
                return json.load(f)
    
    # Hata mesajında kesin yolları göster
    raise FileNotFoundError(
        "Config dosyası şu konumlarda bulunamadı:\n" +
        "\n".join([f"- {path}" for path in config_locations]) +
        "\n\nÇÖZÜM: Lütfen config.json dosyasını bu konumlardan birine yerleştirin.\n" +
        f"Önerilen konum: {config_locations[0]}\n" +
        "Örnek içerik:\n" +
        json.dumps({
            "model_name": "gpt2",
            "dataset_path": "data/dataset.json",
            "train_params": {
                "epochs": 1,
                "batch_size": 2,
                "learning_rate": 2e-5
            }
        }, indent=2)
    )

def preprocess_data(examples, tokenizer, max_length=512):
    """Dataset örneklerini model için ön işler"""
    # 'text' alanını tokenize et
    if 'text' in examples:
        texts = examples['text']
    elif 'input' in examples:
        texts = examples['input']
    elif 'content' in examples:
        texts = examples['content']
    else:
        # Eğer bu alanlar yoksa, tüm string alanları birleştir
        texts = []
        for i in range(len(list(examples.values())[0])):
            text_parts = []
            for key, value_list in examples.items():
                if isinstance(value_list[i], str):
                    text_parts.append(f"{key}: {value_list[i]}")
            texts.append(" | ".join(text_parts))
    
    # Tokenize işlemi
    tokenized = tokenizer(
        texts,
        truncation=True,
        padding=False,
        max_length=max_length,
        return_tensors=None
    )
    
    # Labels'ı input_ids ile aynı yap (causal language modeling için)
    tokenized["labels"] = tokenized["input_ids"].copy()
    
    return tokenized

def load_model_and_tokenizer(model_name):
    """Model ve tokenizer yükler, bellek optimizasyonu yapar"""
    try:
        # Bellek dostu yükleme
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        tokenizer.pad_token = tokenizer.eos_token
        
        # Model yükleme ayarları
        model_kwargs = {
            "torch_dtype": torch.float16 if torch.cuda.is_available() else torch.float32,
            "device_map": "auto" if torch.cuda.is_available() else None,
            "low_cpu_mem_usage": True
        }
        
        model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
        
        return model, tokenizer
    except Exception as e:
        logger.error(f"Model loading failed: {str(e)}")
        raise

def check_dataset(dataset_path):
    """Dataset varlığını ve boyutunu kontrol eder"""
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"Dataset file not found at: {dataset_path}")
    
    # Büyük datasetler için uyarı
    file_size = os.path.getsize(dataset_path) / (1024 * 1024)  # MB cinsinden
    if file_size > 100:  # 100MB'tan büyükse uyar
        logger.warning(f"Large dataset detected ({file_size:.2f}MB). Consider using a smaller subset for testing.")

def train():
    """Optimize edilmiş model eğitim fonksiyonu"""
    try:
        # Seed ayarı
        set_seed(42)
        
        # Config yükle
        config = load_config()
        
        # Dataset kontrolü
        check_dataset(config['dataset_path'])
        
        # Model ve tokenizer yükle
        model, tokenizer = load_model_and_tokenizer(config['model_name'])
        logger.info("Model and tokenizer loaded successfully")
        
        # Veri yükleme (sadece küçük bir kısmıyla başla)
        try:
            dataset = load_dataset('json', data_files=config['dataset_path'], split='train[:20%]')  # Başlangıçta %20
            logger.info(f"Dataset loaded. Samples: {len(dataset)}")
        except Exception as e:
            logger.error(f"Dataset loading failed: {str(e)}")
            raise
        
        # Ön işleme
        processed_dataset = dataset.map(
            lambda x: preprocess_data(x, tokenizer),
            batched=True,
            batch_size=1000,
            remove_columns=dataset.column_names
        )
        
        # Eğitim argümanları (optimize edilmiş)
        training_args = TrainingArguments(
            output_dir=os.path.join(project_root, 'models'),
            overwrite_output_dir=True,
            num_train_epochs=config['train_params'].get('epochs', 1),
            per_device_train_batch_size=config['train_params'].get('batch_size', 2),
            gradient_accumulation_steps=config['train_params'].get('gradient_accumulation_steps', 4),
            learning_rate=config['train_params'].get('learning_rate', 2e-5),
            logging_dir=os.path.join(project_root, 'logs'),
            logging_steps=100,
            save_steps=500,
            save_total_limit=2,
            fp16=torch.cuda.is_available(),
            bf16=not torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
            optim=config['train_params'].get('optim', "adafactor"),
            report_to="none",
            disable_tqdm=False  # İlerleme çubuğu
        )
        
        # Data collator
        data_collator = DataCollatorForLanguageModeling(
            tokenizer=tokenizer,
            mlm=False
        )
        
        # Trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=processed_dataset,
            data_collator=data_collator,
        )
        
        logger.info("Starting training...")
        trainer.train()
        
        # Modeli kaydet
        output_dir = os.path.join(project_root, 'models/final_model')
        trainer.save_model(output_dir)
        tokenizer.save_pretrained(output_dir)
        logger.info(f"Model saved to {output_dir}")
        
    except Exception as e:
        logger.error(f"Training failed: {str(e)}")
        raise

if __name__ == '__main__':
    train()