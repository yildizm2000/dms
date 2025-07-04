# Language Model Training Project

Bu proje, Hugging Face Transformers kütüphanesi kullanarak dil modeli fine-tuning işlemi yapmak için tasarlanmıştır.

## Proje Yapısı

```
.
├── config/
│   └── config.json          # Eğitim konfigürasyonu
├── data/
│   └── dataset.json         # Eğitim verisi
├── scripts/
│   └── train.py            # Ana eğitim scripti
├── models/                 # Eğitilmiş modeller buraya kaydedilir
├── logs/                   # Eğitim logları
├── requirements.txt        # Python bağımlılıkları
├── .env                   # Çevresel değişkenler
└── README.md              # Bu dosya
```

## Kurulum

1. Gerekli bağımlılıkları yükleyin:
```bash
pip install -r requirements.txt
```

2. Çevresel değişkenleri ayarlayın (.env dosyasını düzenleyin)

## Kullanım

Eğitimi başlatmak için:

```bash
cd scripts
python train.py
```

## Konfigürasyon

`config/config.json` dosyasında eğitim parametrelerini değiştirebilirsiniz:

- `model_name`: Kullanılacak model (örn: "gpt2", "distilgpt2")
- `dataset_path`: Dataset dosyasının yolu
- `train_params`: Eğitim parametreleri
  - `epochs`: Eğitim epoch sayısı
  - `batch_size`: Batch boyutu
  - `learning_rate`: Öğrenme oranı
  - `gradient_accumulation_steps`: Gradient akümülasyon adımları

## Dataset Formatı

Dataset dosyası JSON Lines formatında olmalıdır. Her satır bir JSON objesi olmalı ve `text` alanı içermelidir:

```json
{"text": "Örnek metin 1"}
{"text": "Örnek metin 2"}
```

## Gereksinimler

- Python 3.8+
- PyTorch 2.0+
- Transformers 4.30+
- CUDA (opsiyonel, GPU kullanımı için)

## Notlar

- İlk çalıştırmada model ve tokenizer indirileceği için internet bağlantısı gereklidir
- GPU mevcut değilse CPU'da çalışır (daha yavaş)
- Bellek kullanımını optimize etmek için batch boyutları küçük tutulmuştur