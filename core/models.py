from django.db import models
from django.utils import timezone
from decimal import Decimal

# ==========================================
# 1. KATEGORİ VE İMALAT YAPISI
# ==========================================

class Kategori(models.Model):
    isim = models.CharField(max_length=100, verbose_name="Kategori Adı")
    
    def __str__(self):
        return self.isim
    
    class Meta:
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
        verbose_name_plural = "3. Teklifler (İcmal)"

# ==========================================
# 4. GİDERLER (OPEX)
# ==========================================

class GiderKategorisi(models.Model):
    isim = models.CharField(max_length=100)
    
    def __str__(self):
        return self.isim
    
    class Meta:
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
        verbose_name_plural = "4. Harcamalar"

# ==========================================
# 5. ÖDEMELER
# ==========================================

class Odeme(models.Model):
    ODEME_TURLERI = [
        ('nakit', 'Nakit / Havale'),
        ('cek', 'Çek'),
        ('kk', 'Kredi Kartı'),
    ]
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
    
    cek_durumu = models.CharField(
        max_length=20, 
        choices=CEK_DURUMLARI, 
        default='beklemede', 
        verbose_name="Çek Durumu",
        help_text="Sadece Çek ödemeleri için kullanılır."
    )
    
    aciklama = models.CharField(max_length=200, blank=True)
    
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


# ==========================================
# 6. ŞANTİYE & MALZEME YÖNETİMİ (YENİ MODÜL)
# ==========================================

class Malzeme(models.Model):
    isim = models.CharField(max_length=200, verbose_name="Malzeme Adı (Örn: Ø14 Demir)")
    birim = models.CharField(max_length=20, choices=IsKalemi.BIRIMLER, default='adet')
    kritik_stok = models.FloatField(default=10, verbose_name="Kritik Stok Uyarı Limiti")
    
    def __str__(self):
        return self.isim
    
    class Meta:
        verbose_name_plural = "Malzeme Tanımları"

class DepoHareket(models.Model):
    ISLEM_TURLERI = [
        ('giris', '📥 Depo Girişi (Satınalma)'),
        ('cikis', '📤 Depo Çıkışı (Kullanım)'),
        ('iade', '↩️ İade / Red (Kusurlu Mal)'),
    ]
    
    IADE_AKSIYONLARI = [
        ('yok', '-'),
        ('degisim', '🔄 Yenisi Gelecek (Borç Düşme)'),
        ('iptal', '⛔ İptal Et / Faturadan Düş (Borç Düş)'),
    ]

    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, related_name='hareketler')
    tarih = models.DateField(default=timezone.now)
    islem_turu = models.CharField(max_length=10, choices=ISLEM_TURLERI)
    miktar = models.FloatField(verbose_name="Miktar")
    
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Tedarikçi (Giriş ise)")
    irsaliye_no = models.CharField(max_length=50, blank=True, verbose_name="İrsaliye No")
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama / Kullanılan Yer")
    
    # İade Mantığı
    iade_sebebi = models.CharField(max_length=200, blank=True, verbose_name="Red Sebebi")
    iade_aksiyonu = models.CharField(max_length=20, choices=IADE_AKSIYONLARI, default='yok', verbose_name="İade Sonucu")
    kanit_gorseli = models.ImageField(upload_to='depo_kanit/', blank=True, null=True, verbose_name="Hasar/Kanıt Fotoğrafı")

    def save(self, *args, **kwargs):
        # Eğer çıkış yapılıyorsa miktarı negatif kaydetmek yerine pozitif tutuyoruz,
        # hesaplarken işlem türüne bakacağız.
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_islem_turu_display()} - {self.malzeme.isim}"

    class Meta:
        verbose_name_plural = "Depo: Giriş/Çıkış"


# ==========================================
# 7. TAŞERON HAKEDİŞ YÖNETİMİ (YENİ MODÜL)
# ==========================================

class Hakedis(models.Model):
    """
    Onaylanmış bir Teklif (Sözleşme) üzerinden ilerler.
    """
    teklif = models.ForeignKey(Teklif, on_delete=models.CASCADE, related_name='hakedisler', limit_choices_to={'durum': 'onaylandi'})
    hakedis_no = models.PositiveIntegerField(default=1, verbose_name="Hakediş No")
    tarih = models.DateField(default=timezone.now)
    
    donem_baslangic = models.DateField(verbose_name="Dönem Başı")
    donem_bitis = models.DateField(verbose_name="Dönem Sonu")
    
    tamamlanma_orani = models.FloatField(verbose_name="Bu Dönem Tamamlanma (%)", help_text="Örn: 10 girerseniz işin %10'u bitmiş sayılır.")
    
    # Kesintiler
    malzeme_zayiati = models.FloatField(default=0, verbose_name="Malzeme / Zayiat Kesintisi (TL)")
    diger_kesintiler = models.FloatField(default=0, verbose_name="Diğer Kesintiler (Avans/Stopaj vb.)")
    
    onay_durumu = models.BooleanField(default=False, verbose_name="Hakediş Onaylandı mı?")
    
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def hakedis_tutari(self):
        # Sözleşme Tutarı * (Tamamlanma Oranı / 100)
        sozlesme_tutari = self.teklif.toplam_fiyat_tl
        return sozlesme_tutari * (self.tamamlanma_orani / 100)

    @property
    def odenecek_net_tutar(self):
        return self.hakedis_tutari - (self.malzeme_zayiati + self.diger_kesintiler)

    def __str__(self):
        return f"{self.teklif.tedarikci} - Hakediş #{self.hakedis_no}"

    class Meta:
        verbose_name_plural = "Taşeron Hakedişleri"

    # ==========================================
# 8. MALZEME TALEP FORMU (YENİ EKLEME)
# ==========================================

class MalzemeTalep(models.Model):
    ONCELIKLER = [
        ('normal', '🟢 Normal'),
        ('acil', '🔴 Acil'),
        ('cok_acil', '🔥 ÇOK ACİL (İş Durdu)'),
    ]
    
    DURUMLAR = [
        ('bekliyor', '⏳ Onay Bekliyor'),
        ('onaylandi', '✅ Onaylandı (Satınalmada)'),
        ('tamamlandi', '📦 Temin Edildi / Geldi'),
        ('red', '❌ Reddedildi'),
    ]

    talep_eden = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Talep Eden Mühendis")
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, related_name='talepler')
    miktar = models.FloatField(verbose_name="İstenen Miktar")
    oncelik = models.CharField(max_length=10, choices=ONCELIKLER, default='normal', verbose_name="Aciliyet Durumu")
    
    proje_yeri = models.CharField(max_length=200, blank=True, verbose_name="Kullanılacak Yer (Örn: C Blok Zemin)")
    aciklama = models.TextField(blank=True, verbose_name="Notlar")
    
    durum = models.CharField(max_length=20, choices=DURUMLAR, default='bekliyor')
    tarih = models.DateTimeField(default=timezone.now, verbose_name="Talep Tarihi")

    # --- YENİ EKLENEN TARİHÇE ALANLARI ---
    onay_tarihi = models.DateTimeField(null=True, blank=True, verbose_name="Onaylanma Zamanı")
    temin_tarihi = models.DateTimeField(null=True, blank=True, verbose_name="Temin/Teslim Zamanı")

    def __str__(self):
        return f"{self.malzeme.isim} - {self.miktar} ({self.get_oncelik_display()})"

    class Meta:
        verbose_name_plural = "Malzeme Talepleri"
        ordering = ['-tarih']