from django.core.management.base import BaseCommand
from core.models import (
    Fatura, Hakedis, DepoTransfer, DepoHareket, Odeme, Harcama,
    SatinAlma, Teklif, MalzemeTalep, Malzeme, IsKalemi, 
    Kategori, Tedarikci, Depo, GiderKategorisi
)

class Command(BaseCommand):
    help = 'Kullanıcılar hariç tüm veritabanını temizler'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("⚠️ Veriler siliniyor..."))
        
        # İlişki sırasına göre silmek önemlidir (Önce çocuk, sonra ebeveyn)
        models_to_delete = [
            Hakedis,       # Satınalmaya bağlı
            Fatura,        # Satınalmaya bağlı
            DepoHareket,   # Malzeme ve Depoya bağlı
            DepoTransfer,  # Depolara bağlı
            Odeme,         # Hakediş ve Tedarikçiye bağlı
            Harcama,       # Gider Kategorisine bağlı
            SatinAlma,     # Teklife bağlı
            Teklif,        # Talep ve Tedarikçiye bağlı
            MalzemeTalep,  # Malzeme ve Kullanıcıya bağlı
            
            # Ana Tanımlar
            Malzeme, 
            IsKalemi, 
            Kategori,      # İş Kalemleri için
            Tedarikci, 
            Depo, 
            GiderKategorisi
        ]
        
        for model in models_to_delete:
            count = model.objects.all().count()
            model.objects.all().delete()
            if count > 0:
                self.stdout.write(f"- {model.__name__}: {count} kayıt silindi.")
            
        self.stdout.write(self.style.SUCCESS('✅ Veritabanı başarıyla temizlendi (Kullanıcı hesapları korundu).'))