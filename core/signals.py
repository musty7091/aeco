from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum
from decimal import Decimal
from .models import DepoTransfer, DepoHareket, SatinAlma

@receiver(post_save, sender=DepoTransfer)
def depo_transfer_post_save(sender, instance, created, **kwargs):
    """
    Bir DepoTransfer nesnesi kaydedildiğinde otomatik olarak
    kaynak depodan çıkış ve hedef depoya giriş hareketlerini oluşturur.
    Ayrıca otomatik FIFO eşleşmesi yapmaya çalışır.
    """
    if created:
        # 1. Otomatik Sipariş Eşleşmesi (FIFO - First In First Out)
        # Eğer bir sipariş belirtilmemişse ve kaynak depo Sanal ise;
        siparis_obj = getattr(instance, 'bagli_siparis', None)
        
        if not siparis_obj and instance.kaynak_depo.is_sanal:
            # Bu malzemeyi içeren ve tamamlanmamış en eski siparişi bul
            aday_siparisler = SatinAlma.objects.filter(
                teklif__malzeme=instance.malzeme
            ).exclude(teslimat_durumu='tamamlandi').order_by('created_at')
            
            for aday in aday_siparisler:
                if aday.sanal_depoda_bekleyen > 0:
                    siparis_obj = aday
                    # Notu güncellemek için (save yapmadan sadece instance üzerinde)
                    if not instance.aciklama:
                        instance.aciklama = f"Otomatik Eşleşme: Sipariş #{aday.id}"
                    else:
                        instance.aciklama += f" (Oto. Sipariş #{aday.id})"
                    
                    # Tekrar save ederek açıklamayı ve bağlantıyı güncelle
                    # (recursion'ı önlemek için update kullanabiliriz ama basitlik için geçiyoruz şimdilik)
                    break

        # 2. Kaynak Depo ÇIKIŞ Hareketi
        DepoHareket.objects.create(
            malzeme=instance.malzeme,
            depo=instance.kaynak_depo,
            tarih=instance.tarih,
            islem_turu='cikis',
            miktar=instance.miktar,
            siparis=siparis_obj,
            aciklama=f"TRANSFER ÇIKIŞI -> {instance.hedef_depo.isim} | {instance.aciklama}"
        )
        
        # 3. Hedef Depo GİRİŞ Hareketi
        DepoHareket.objects.create(
            malzeme=instance.malzeme,
            depo=instance.hedef_depo,
            tarih=instance.tarih,
            islem_turu='giris',
            miktar=instance.miktar,
            siparis=siparis_obj,
            aciklama=f"TRANSFER GİRİŞİ <- {instance.kaynak_depo.isim} | {instance.aciklama}"
        )
        
        # Eğer bir siparişe bağlandıysa, siparişin durumunu tetiklemek için siparişi kaydet
        if siparis_obj:
            siparis_obj.save()