import requests
import xml.etree.ElementTree as ET
from decimal import Decimal

def tcmb_kur_getir():
    """
    TCMB'den güncel USD, EUR ve GBP kurlarını çeker.
    Hata durumunda varsayılan olarak 1.0 döner.
    """
    url = "https://www.tcmb.gov.tr/kurlar/today.xml"
    
    kurlar = {
        'USD': Decimal('1.0'),
        'EUR': Decimal('1.0'),
        'GBP': Decimal('1.0') # Sterlin Eklendi
    }
    
    try:
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            
            for currency in root.findall('Currency'):
                kod = currency.get('Kod')
                
                # Banknot Satış yoksa Forex Satış (Piyasa)
                satis = currency.find('BanknoteSelling').text
                if not satis:
                    satis = currency.find('ForexSelling').text
                    
                if satis and kod in ['USD', 'EUR', 'GBP']:
                    # Nokta/Virgül karmaşasını önlemek için güvenli dönüşüm
                    deger = Decimal(satis)
                    kurlar[kod] = deger

    except Exception as e:
        print(f"Kur çekme hatası: {e}")
        
    return kurlar