"""
CoinTakip — Merkezi Loglama Yapılandırması (FAZ C1)

Tüm backend modülleri log kaydını buradan alır:

    from log_config import get_logger
    logger = get_logger("price_service")

Çıktı iki yere birden gider:
  1. Konsol  — Baslat.bat ile açılan terminal penceresi
  2. Dosya   — data/logs/cointakip.log (1 MB'da döner, 3 yedek tutulur)

Dosya kaydı özellikle Baslat_Sessiz.vbs ile çalıştırıldığında kritiktir:
pencere gizli olduğu için konsol çıktısı görülemez, hata izi yalnızca dosyada kalır.

NOT: Fiyat motoru 4 saniyede bir çalıştığından, o döngüdeki rutin mesajlar
DEBUG seviyesindedir ve varsayılan INFO seviyesinde dosyaya yazılmaz.
Aksi halde log dosyası dakikalar içinde şişerdi.
"""

import os
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "data", "logs")
LOG_FILE = os.path.join(LOG_DIR, "cointakip.log")

ROOT_LOGGER_NAME = "cointakip"
MAX_BYTES = 1_000_000   # ~1 MB
BACKUP_COUNT = 3        # cointakip.log.1 .. .3  → toplam ~4 MB tavan

_configured = False


def setup_logging(level=None):
    """Kök 'cointakip' logger'ını bir kez yapılandırır. Tekrar çağrılması güvenlidir."""
    global _configured
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    if _configured:
        return logger

    # Seviye ortam değişkeniyle ezilebilir: COINTAKIP_LOG_LEVEL=DEBUG
    if level is None:
        env_level = os.environ.get("COINTAKIP_LOG_LEVEL", "INFO").upper().strip()
        level = getattr(logging, env_level, logging.INFO)

    logger.setLevel(level)
    logger.propagate = False  # uvicorn'un kök logger'ına çift kayıt düşmesin

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-24s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    # Dosya kaydı başarısız olsa bile uygulama çalışmaya devam etmeli
    # (Kural 6: Fallback Zinciri). Salt-okunur dizin veya izin hatası
    # uygulamayı durdurmamalı.
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning("Log dosyası açılamadı, yalnızca konsola yazılacak: %s", e)

    _configured = True
    return logger


def get_logger(name=None):
    """Modüle özel alt logger döndürür (ör. 'cointakip.price_service')."""
    setup_logging()
    if name:
        return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
    return logging.getLogger(ROOT_LOGGER_NAME)
