from django.db import models
from django.utils import timezone

# ==========================================
# 1. KATEGORİ VE İMALAT YAPISI
# ==========================================

class Kategori(models.Model):
    isim = models.CharField(max_length=100, verbose_name="Kategori Adı")
    
    def __str__(self):
        return self.isim
    
    class Meta:
        # "1. İmalat Kategorileri" yerine daha kısa:
        verbose_name_plural = "1. İmalat Türleri"

class IsKalemi(models.Model):
    BIRIMLER = [
        ('adet', 'Adet'), ('m2', 'Metrekare (m²)'), ('m3', 'Metreküp (m³)'),
        ('kg', 'Kilogram (kg)'), ('ton', 'Ton'), ('mt', 'Metre (mt)'),
        ('adam_saat', 'Adam/Saat'), ('goturu', 'Götürü (Toplu)'),
    ]
    
    kategori = models.ForeignKey(Kategori, on_delete=models.CASCADE, related_name='kalemler')
    isim = models.CharField(max_length=200, verbose_name="İş Kalemi Adı")
    hedef_miktar = models.FloatField(default=1, verbose_name="Yaklaşık Metraj")
    birim = models.CharField(max_length=20, choices=BIRIMLER, default='adet')
    
    def __str__(self):
        return f"{self.isim} ({self.hedef_miktar} {self.get_birim_display()})"
    
    class Meta:
        verbose_name_plural = "2. İş Kalemleri"

# ==========================================
# 2. TEDARİKÇİLER
# ==========================================

class Tedarikci(models.Model):
    firma_unvani = models.CharField(max_length=200, verbose_name="Firma Ünvanı")
    yetkili_kisi = models.CharField(max_length=100, blank=True, verbose_name="Yetkili Kişi")
    telefon = models.CharField(max_length=20, blank=True)
    adres = models.TextField(blank=True)
    
    def __str__(self):
        return self.firma_unvani
    
    class Meta:
        # "Tedarikçiler / Taşeronlar" yerine sadece:
        verbose_name_plural = "Tedarikçiler"

# ==========================================
# 3. TEKLİFLER
# ==========================================

class Teklif(models.Model):
    DURUMLAR = [
        ('beklemede', '⏳ Beklemede'),
        ('onaylandi', '✅ Onaylandı / Sözleşme'),
        ('reddedildi', '❌ Reddedildi'),
    ]
    PARA_BIRIMLERI = [
        ('TRY', '₺ Türk Lirası'), ('USD', '$ Amerikan Doları'),
        ('EUR', '€ Euro'), ('GBP', '£ İngiliz Sterlini'),
    ]
    
    is_kalemi = models.ForeignKey(IsKalemi, on_delete=models.CASCADE, related_name='teklifler')
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.CASCADE, related_name='teklifler')
    
    birim_fiyat = models.FloatField(verbose_name="Birim Fiyat (KDV Hariç)")
    para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMLERI, default='TRY')
    kur_degeri = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000, verbose_name="İşlem Kuru")
    
    kdv_dahil_mi = models.BooleanField(default=False, verbose_name="Bu fiyata KDV Dahil mi?")
    kdv_orani = models.FloatField(default=20, verbose_name="KDV Oranı (%)")
    
    teklif_dosyasi = models.FileField(upload_to='teklifler/', blank=True, null=True, verbose_name="Teklif PDF/Resim")
    durum = models.CharField(max_length=20, choices=DURUMLAR, default='beklemede')
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        if self.kdv_dahil_mi:
            self.birim_fiyat = self.birim_fiyat / (1 + (self.kdv_orani / 100))
            self.kdv_dahil_mi = False
        super(Teklif, self).save(*args, **kwargs)

    @property
    def toplam_fiyat_tl(self):
        miktar = self.is_kalemi.hedef_miktar
        tutar_tl = float(self.birim_fiyat) * float(self.kur_degeri) * miktar
        kdvli_tutar = tutar_tl * (1 + (self.kdv_orani / 100))
        return kdvli_tutar

    def __str__(self):
        return f"{self.tedarikci} - {self.is_kalemi.isim}"
    
    class Meta:
        # "3. Teklifler (İcmal)" sığıyor, sorun yok.
        verbose_name_plural = "3. Teklifler (İcmal)"

# ==========================================
# 4. GİDERLER (OPEX)
# ==========================================

class GiderKategorisi(models.Model):
    isim = models.CharField(max_length=100)
    
    def __str__(self):
        return self.isim
    
    class Meta:
        # "Gider Kategorileri (OPEX)" yerine:
        verbose_name_plural = "Gider Tanımları"

class Harcama(models.Model):
    PARA_BIRIMLERI = [('TRY', 'TL'), ('USD', 'USD'), ('EUR', 'EUR'), ('GBP', 'GBP')]

    kategori = models.ForeignKey(GiderKategorisi, on_delete=models.CASCADE, related_name='harcamalar')
    aciklama = models.CharField(max_length=200)
    tutar = models.FloatField()
    para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMLERI, default='TRY')
    tarih = models.DateField(default=timezone.now)
    dekont = models.FileField(upload_to='harcamalar/', blank=True, null=True)

    @property
    def tl_tutar(self):
        return self.tutar

    def __str__(self):
        return f"{self.aciklama} - {self.tutar}"
    
    class Meta:
        # "4. Gider / Harcama Fişleri" yerine daha kısa:
        verbose_name_plural = "4. Harcamalar"

# ==========================================
# 5. ÖDEMELER (GÜNCELLENEN KISIM)
# ==========================================

class Odeme(models.Model):
    ODEME_TURLERI = [
        ('nakit', 'Nakit / Havale'),
        ('cek', 'Çek'),
        ('kk', 'Kredi Kartı'),
    ]
    
    # YENİ: ÇEK DURUMLARI
    CEK_DURUMLARI = [
        ('beklemede', '⏳ Vadesi Bekleniyor'),
        ('odendi', '✅ Ödendi / Tahsil Edildi'),
        ('karsiliksiz', '❌ Karşılıksız / İptal'),
    ]

    PARA_BIRIMLERI = [('TRY', 'TL'), ('USD', 'USD'), ('EUR', 'EUR'), ('GBP', 'GBP')]
    
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.CASCADE, related_name='odemeler')
    
    ilgili_teklif = models.ForeignKey(
        Teklif, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        limit_choices_to={'durum': 'onaylandi'} 
    )
    
    tarih = models.DateField(default=timezone.now, verbose_name="İşlem Tarihi")
    tutar = models.FloatField(verbose_name="Tutar")
    para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMLERI, default='TRY')
    kur_degeri = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000, verbose_name="İşlem Kuru")
    
    odeme_turu = models.CharField(max_length=10, choices=ODEME_TURLERI, default='nakit')
    
    # YENİ EKLENEN ALAN: Çek Durumu
    cek_durumu = models.CharField(
        max_length=20, 
        choices=CEK_DURUMLARI, 
        default='beklemede', 
        verbose_name="Çek Durumu",
        help_text="Sadece Çek ödemeleri için kullanılır."
    )
    
    aciklama = models.CharField(max_length=200, blank=True)
    
    # Çek Bilgileri
    cek_vade_tarihi = models.DateField(blank=True, null=True, verbose_name="Çek Vade Tarihi")
    cek_numarasi = models.CharField(max_length=50, blank=True, verbose_name="Çek No")
    cek_banka = models.CharField(max_length=100, blank=True, verbose_name="Banka Adı")
    cek_sube = models.CharField(max_length=100, blank=True, verbose_name="Şube")
    cek_gorseli = models.ImageField(upload_to='cekler/', blank=True, null=True)
    
    dekont = models.FileField(upload_to='odemeler/', blank=True, null=True)

    @property
    def tl_tutar(self):
        return float(self.tutar) * float(self.kur_degeri)

    def __str__(self):
        return f"{self.tedarikci} - {self.tutar} {self.para_birimi}"

    class Meta:
        verbose_name_plural = "5. Ödemeler"