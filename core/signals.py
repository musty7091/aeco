from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum
from django.db import transaction # Atomik işlem için eklendi
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
        # Uzman Önerisi: İşlemleri atomik blok içine alıyoruz (Ya hep ya hiç)
        with transaction.atomic():
            siparis_obj = getattr(instance, 'bagli_siparis', None)

            # 1. Otomatik Sipariş Eşleşmesi (FIFO)
            # Kaynak depo SANAL ise ve sipariş belirtilmemişse, eski siparişleri bulmaya çalış
            if not siparis_obj and instance.kaynak_depo.is_sanal:
                try:
                    # Bu malzemeyi içeren ve tamamlanmamış en eski siparişi bul
                    aday_siparisler = SatinAlma.objects.filter(
                        teklif__malzeme=instance.malzeme
                    ).exclude(teslimat_durumu='tamamlandi').order_by('created_at')
                    
                    for aday in aday_siparisler:
                        # 'sanal_depoda_bekleyen' bir property olduğu için veritabanı seviyesinde filtreleyemeyiz, döngüde bakıyoruz
                        if aday.sanal_depoda_bekleyen > 0:
                            siparis_obj = aday
                            
                            # Açıklamayı güncelle
                            if not instance.aciklama:
                                instance.aciklama = f"Otomatik Eşleşme: Sipariş #{aday.id}"
                            else:
                                instance.aciklama += f" (Oto. Sipariş #{aday.id})"
                            
                            # Döngüden çık, ilk bulduğunu kullan (FIFO)
                            break
                except Exception as e:
                    print(f"FIFO Eşleşme Hatası: {e}")
                    # Hata olsa bile transfere engel olma, devam et.

            # 2. Kaynak Depo ÇIKIŞ Hareketi
            DepoHareket.objects.create(
                malzeme=instance.malzeme,
                depo=instance.kaynak_depo,
                tarih=instance.tarih,
                islem_turu='cikis',
                miktar=instance.miktar,
                siparis=siparis_obj,
                aciklama=f"TRANSFER ÇIKIŞI -> {instance.hedef_depo.isim} | {instance.aciklama if instance.aciklama else ''}"
            )
            
            # 3. Hedef Depo GİRİŞ Hareketi
            DepoHareket.objects.create(
                malzeme=instance.malzeme,
                depo=instance.hedef_depo,
                tarih=instance.tarih,
                islem_turu='giris',
                miktar=instance.miktar,
                siparis=siparis_obj,
                aciklama=f"TRANSFER GİRİŞİ <- {instance.kaynak_depo.isim} | {instance.aciklama if instance.aciklama else ''}"
            )
            
            # Eğer bir siparişe bağlandıysa, siparişin durumunu güncellemek için kaydet
            if siparis_obj:
                siparis_obj.save()