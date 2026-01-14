from django.core.management.base import BaseCommand
from core.models import *

class Command(BaseCommand):
    help = 'Kullanıcılar hariç tüm veritabanını temizler'

    def handle(self, *args, **kwargs):
        self.stdout.write("Veriler siliniyor...")
        
        # Sırayla silme işlemleri
        models_to_delete = [
            Fatura, Hakedis, DepoTransfer, DepoHareket, Odeme, Harcama,
            SatinAlma, Teklif, MalzemeTalep, Malzeme, IsKalemi, 
            Kategori, Tedarikci, Depo, GiderKategorisi
        ]
        
        for model in models_to_delete:
            count = model.objects.all().count()
            model.objects.all().delete()
            self.stdout.write(f"- {model.__name__}: {count} kayıt silindi.")
            
        self.stdout.write(self.style.SUCCESS('✅ Veritabanı başarıyla temizlendi (Kullanıcılar hariç).'))