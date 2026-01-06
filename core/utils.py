import requests
import xml.etree.ElementTree as ET
from decimal import Decimal

def tcmb_kur_getir():
    """
    TCMB'den günlük kurları çeker.
    Eğer bağlantı hatası olursa varsayılan olarak 1.0 döndürür (Sistemi kilitlememek için).
    """
    url = "https://www.tcmb.gov.tr/kurlar/today.xml"
    
    kurlar = {
        'USD': 1.0,
        'EUR': 1.0,
        'GBP': 1.0
    }
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            
            for currency in root.findall('Currency'):
                kod = currency.get('Kod')
                if kod in ['USD', 'EUR', 'GBP']:
                    # ForexSelling (Döviz Satış) genelde piyasa için baz alınır
                    satis = currency.find('ForexSelling').text
                    if satis:
                        kurlar[kod] = Decimal(satis)
                        
    except Exception as e:
        print(f"Kur çekme hatası: {e}")
        # Hata durumunda eski usul devam et, site çökmesin.
        
    return kurlar