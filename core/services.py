# core/services.py
from django.db import transaction
from core.models import DepoHareket

class StockService:
    @staticmethod
    @transaction.atomic
    def execute_transfer(malzeme, miktar, kaynak_depo, hedef_depo, siparis=None, aciklama=""):
        """
        Sistemdeki tüm stok hareketlerini yöneten merkezi ve atomik servis.
        'Ya hep ya hiç' kuralı ile çalışır.
        """
        # 1. Kaynak Depodan ÇIKIŞ
        DepoHareket.objects.create(
            malzeme=malzeme,
            depo=kaynak_depo,
            miktar=miktar,
            islem_turu='cikis',
            siparis=siparis,
            aciklama=f"ÇIKIŞ: {aciklama}"
        )

        # 2. Hedef Depoya GİRİŞ
        DepoHareket.objects.create(
            malzeme=malzeme,
            depo=hedef_depo,
            miktar=miktar,
            islem_turu='giris',
            siparis=siparis,
            aciklama=f"GİRİŞ: {aciklama}"
        )
        return True