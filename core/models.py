from django.db import models
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum
from django.core.exceptions import ValidationError

# ==========================================
# SABİTLER (GLOBAL)
# ==========================================

KDV_ORANLARI = [
    (0, '%0'), 
    (5, '%5'), 
    (10, '%10'), 
    (16, '%16'), 
    (20, '%20')
]

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
    
    kategori = models.ForeignKey(Kategori, on_delete=models.CASCADE, related_name='kalemler', verbose_name="Kategori")
    isim = models.CharField(max_length=200, verbose_name="İş Kalemi Adı")
    hedef_miktar = models.FloatField(default=1, verbose_name="Yaklaşık Metraj")
    birim = models.CharField(max_length=20, choices=BIRIMLER, default='adet')
    
    kdv_orani = models.IntegerField(choices=KDV_ORANLARI, default=20, verbose_name="Varsayılan KDV (%)")
    aciklama = models.TextField(blank=True, verbose_name="İş Tanımı / Teknik Şartname")
    
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
# 3. DEPO VE STOK YÖNETİMİ
# ==========================================

class Depo(models.Model):
    isim = models.CharField(max_length=100, verbose_name="Depo Adı")
    adres = models.CharField(max_length=200, blank=True, verbose_name="Lokasyon / Adres")
    is_sanal = models.BooleanField(default=False, verbose_name="Sanal / Tedarikçi Deposu mu?")
    
    def __str__(self):
        tur = "(Sanal)" if self.is_sanal else "(Fiziksel)"
        return f"{self.isim} {tur}"

    class Meta:
        verbose_name_plural = "Depo Tanımları"

class Malzeme(models.Model):
    KATEGORILER = [
        ('genel', 'Genel Malzeme'),
        ('hirdavat', 'Hırdavat / Nalburiye'),
        ('elektrik', 'Elektrik & Aydınlatma'),
        ('mekanik', 'Mekanik & Tesisat'),
        ('insaat', 'Kaba İnşaat (Çimento/Demir)'),
        ('boya', 'Boya & Kimyasal'),
        ('demirbas', 'Demirbaş / Ekipman'),
    ]
    
    isim = models.CharField(max_length=200, verbose_name="Malzeme Adı (Örn: Ø14 Demir)")
    kategori = models.CharField(max_length=20, choices=KATEGORILER, default='genel', verbose_name="Malzeme Grubu")
    marka = models.CharField(max_length=100, blank=True, verbose_name="Marka / Model", help_text="Örn: Bosch, Vitra vb.")
    birim = models.CharField(max_length=20, choices=IsKalemi.BIRIMLER, default='adet')
    kdv_orani = models.IntegerField(choices=KDV_ORANLARI, default=20, verbose_name="Varsayılan KDV (%)")
    kritik_stok = models.FloatField(default=10, verbose_name="Kritik Stok Uyarı Limiti")
    aciklama = models.TextField(blank=True, verbose_name="Teknik Özellikler / Notlar")
    
    @property
    def stok(self):
        giren = self.hareketler.filter(islem_turu='giris').aggregate(Sum('miktar'))['miktar__sum'] or 0
        cikan = self.hareketler.filter(islem_turu='cikis').aggregate(Sum('miktar'))['miktar__sum'] or 0
        iade_iptal = self.hareketler.filter(islem_turu='iade', iade_aksiyonu='iptal').aggregate(Sum('miktar'))['miktar__sum'] or 0
        return giren - cikan - iade_iptal

    def depo_stogu(self, depo_id):
        giren = self.hareketler.filter(depo_id=depo_id, islem_turu='giris').aggregate(Sum('miktar'))['miktar__sum'] or 0
        cikan = self.hareketler.filter(depo_id=depo_id, islem_turu='cikis').aggregate(Sum('miktar'))['miktar__sum'] or 0
        iade_iptal = self.hareketler.filter(depo_id=depo_id, islem_turu='iade', iade_aksiyonu='iptal').aggregate(Sum('miktar'))['miktar__sum'] or 0
        return giren - cikan - iade_iptal

    def __str__(self):
        return f"{self.isim} ({self.marka})" if self.marka else self.isim
    
    class Meta:
        verbose_name = "7. Envanter (Stok Durumu)"
        verbose_name_plural = "7. Envanter (Stok Durumu)"

# ==========================================
# 4. MALZEME TALEP FORMU
# ==========================================

class MalzemeTalep(models.Model):
    ONCELIKLER = [
        ('normal', '🟢 Normal'),
        ('acil', '🔴 Acil'),
        ('cok_acil', '🔥 ÇOK ACİL (İş Durdu)'),
    ]
    
    DURUMLAR = [
        ('bekliyor', '⏳ Talep Açıldı (Onay Bekliyor)'),
        ('islemde', '🔍 Satınalma / Teklif Sürecinde'),
        ('onaylandi', '✅ Sipariş Verildi'),
        ('tamamlandi', '📦 Temin Edildi / Geldi'),
        ('red', '❌ Reddedildi / İptal'),
    ]

    talep_eden = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Talep Eden")
    
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, related_name='talepler', null=True, blank=True, verbose_name="Malzeme (Satınalma)")
    is_kalemi = models.ForeignKey(IsKalemi, on_delete=models.CASCADE, related_name='talepler', null=True, blank=True, verbose_name="İş Kalemi (Hizmet/Taşeron)")
    
    miktar = models.FloatField(verbose_name="İstenen Miktar")
    oncelik = models.CharField(max_length=10, choices=ONCELIKLER, default='normal', verbose_name="Aciliyet Durumu")
    
    proje_yeri = models.CharField(max_length=200, blank=True, verbose_name="Kullanılacak Yer")
    aciklama = models.TextField(blank=True, verbose_name="Notlar")
    
    durum = models.CharField(max_length=20, choices=DURUMLAR, default='bekliyor')
    tarih = models.DateTimeField(default=timezone.now, verbose_name="Talep Tarihi")

    onay_tarihi = models.DateTimeField(null=True, blank=True, verbose_name="Onaylanma Zamanı")
    temin_tarihi = models.DateTimeField(null=True, blank=True, verbose_name="Temin/Teslim Zamanı")

    def clean(self):
        if not self.malzeme and not self.is_kalemi:
            raise ValidationError("Lütfen ya bir Malzeme ya da bir İş Kalemi seçiniz.")
        if self.malzeme and self.is_kalemi:
            raise ValidationError("Aynı anda hem Malzeme hem Hizmet seçemezsiniz.")

    def __str__(self):
        ad = self.malzeme.isim if self.malzeme else (self.is_kalemi.isim if self.is_kalemi else "Tanımsız")
        return f"Talep: {ad}"

    class Meta:
        verbose_name_plural = "Malzeme ve Hizmet Talepleri"
        ordering = ['-tarih']

# ==========================================
# 5. TEKLİFLER (FİYAT TOPLAMA)
# ==========================================

class Teklif(models.Model):
    DURUMLAR = [
        ('beklemede', '⏳ İncelemede'),
        ('onaylandi', '✅ Onaylandı (Sipariş)'),
        ('reddedildi', '❌ Reddedildi'),
    ]
    PARA_BIRIMLERI = [
        ('TRY', '₺ Türk Lirası'), ('USD', '$ Amerikan Doları'),
        ('EUR', '€ Euro'), ('GBP', '£ İngiliz Sterlini'),
    ]
    
    talep = models.ForeignKey(MalzemeTalep, on_delete=models.CASCADE, related_name='teklifler', null=True, blank=True, verbose_name="İlgili Talep")
    
    is_kalemi = models.ForeignKey(IsKalemi, on_delete=models.CASCADE, related_name='teklifler', null=True, blank=True, verbose_name="İş Kalemi (Taşeronluk)")
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, related_name='teklifler', null=True, blank=True, verbose_name="Malzeme (Satınalma)")
    
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.CASCADE, related_name='teklifler')
    
    miktar = models.FloatField(default=1, verbose_name="Teklif Miktarı")
    
    birim_fiyat = models.FloatField(verbose_name="Birim Fiyat (KDV Hariç)")
    para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMLERI, default='TRY')
    kur_degeri = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000, verbose_name="İşlem Kuru")
    
    kdv_dahil_mi = models.BooleanField(default=False, verbose_name="Bu fiyata KDV Dahil mi?")
    kdv_orani = models.IntegerField(choices=KDV_ORANLARI, default=20, verbose_name="KDV Oranı")
    
    teklif_dosyasi = models.FileField(upload_to='teklifler/', blank=True, null=True, verbose_name="Teklif PDF/Resim")
    durum = models.CharField(max_length=20, choices=DURUMLAR, default='beklemede')
    
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)
    
    def clean(self):
        if not self.is_kalemi and not self.malzeme:
            raise ValidationError("Lütfen ya bir 'İş Kalemi' ya da bir 'Malzeme' seçiniz.")
        if self.is_kalemi and self.malzeme:
            raise ValidationError("Aynı anda hem İş Kalemi hem Malzeme seçemezsiniz.")

    def save(self, *args, **kwargs):
        kdv_carpani = 0 if self.kdv_orani == -1 else self.kdv_orani
        if self.kdv_dahil_mi:
            self.birim_fiyat = self.birim_fiyat / (1 + (kdv_carpani / 100))
            self.kdv_dahil_mi = False
            
        if self.pk is None and self.talep:
            if self.talep.durum == 'bekliyor':
                self.talep.durum = 'islemde'
                self.talep.save()
                
        super(Teklif, self).save(*args, **kwargs)

    @property
    def toplam_fiyat_tl(self):
        kdv_carpani = 0 if self.kdv_orani == -1 else self.kdv_orani
        tutar_tl = float(self.birim_fiyat) * float(self.kur_degeri) * float(self.miktar)
        kdvli_tutar = tutar_tl * (1 + (kdv_carpani / 100))
        return kdvli_tutar
    
    @property
    def toplam_fiyat_orijinal(self):
        kdv_carpani = 0 if self.kdv_orani == -1 else self.kdv_orani
        ham_tutar = float(self.birim_fiyat) * float(self.miktar)
        kdvli_tutar = ham_tutar * (1 + (kdv_carpani / 100))
        return kdvli_tutar

    @property
    def birim_fiyat_kdvli(self):
        kdv_carpani = 0 if self.kdv_orani == -1 else self.kdv_orani
        return float(self.birim_fiyat) * (1 + (kdv_carpani / 100))

    def __str__(self):
        nesne = self.is_kalemi.isim if self.is_kalemi else (self.malzeme.isim if self.malzeme else "Tanımsız")
        return f"{self.tedarikci} - {nesne}"
    
    class Meta:
        verbose_name = "3. Teklifler (Fiyat Toplama)"
        verbose_name_plural = "3. Teklifler (Fiyat Toplama)"


# ==========================================
# 6. SATINALMA (RESMİLEŞEN SİPARİŞLER)
# ==========================================

class SatinAlma(models.Model):
    TESLIMAT_DURUMLARI = [
        ('bekliyor', '🔴 Bekliyor (Hiç Gelmedi)'),
        ('kismi', '🟠 Kısmi Teslimat (Eksik Var)'),
        ('tamamlandi', '🟢 Tamamlandı (Hepsi Geldi)'),
    ]
    
    teklif = models.OneToOneField('Teklif', on_delete=models.CASCADE, related_name='satinalma_donusumu', verbose_name="İlgili Teklif")
    
    siparis_tarihi = models.DateField(default=timezone.now, verbose_name="Sipariş Tarihi")
    teslimat_durumu = models.CharField(max_length=20, choices=TESLIMAT_DURUMLARI, default='bekliyor')
    
    # Miktar Takibi
    toplam_miktar = models.FloatField(default=0, verbose_name="Sipariş Edilen Toplam")
    
    # İki ayrı sayaç
    teslim_edilen = models.FloatField(default=0, verbose_name="Depoya Giren (Fiziksel)")
    faturalanan_miktar = models.FloatField(default=0, verbose_name="Faturası Gelen (Finansal)")
    
    aciklama = models.TextField(blank=True, verbose_name="Notlar")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Durum güncellemesi
        if self.teslim_edilen == 0:
            self.teslimat_durumu = 'bekliyor'
        elif 0 < self.teslim_edilen < self.toplam_miktar:
            self.teslimat_durumu = 'kismi'
        elif self.teslim_edilen >= self.toplam_miktar:
            self.teslimat_durumu = 'tamamlandi'
            
        super(SatinAlma, self).save(*args, **kwargs)

    @property
    def kalan_miktar(self):
        """Depoya daha girmesi gereken miktar"""
        return max(self.toplam_miktar - self.teslim_edilen, 0)

    @property
    def kalan_fatura_miktar(self):
        """Faturası henüz gelmemiş miktar"""
        return max(self.toplam_miktar - self.faturalanan_miktar, 0)

    @property
    def tamamlanma_yuzdesi(self):
        if self.toplam_miktar == 0: return 0
        yuzde = (self.teslim_edilen / self.toplam_miktar) * 100
        return min(yuzde, 100)

    # --- YENİ EKLENEN KRİTİK ÖZELLİK ---
    @property
    def sanal_depoda_bekleyen(self):
        """
        Bu siparişin Sanal Depolara girip de henüz oradan çıkmamış (Sevk edilmemiş) miktarı.
        """
        girisler = self.depo_hareketleri.filter(depo__is_sanal=True, islem_turu='giris').aggregate(Sum('miktar'))['miktar__sum'] or 0
        cikislar = self.depo_hareketleri.filter(depo__is_sanal=True, islem_turu='cikis').aggregate(Sum('miktar'))['miktar__sum'] or 0
        return max(girisler - cikislar, 0)

    def __str__(self):
        return f"{self.teklif.tedarikci} - {self.teklif.malzeme.isim} (Kalan: {self.kalan_miktar})"

    class Meta:
        verbose_name = "4. Satınalma & Siparişler"
        verbose_name_plural = "4. Satınalma & Siparişler"


# ==========================================
# 7. GİDERLER (OPEX)
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
        verbose_name_plural = "5. Harcamalar (Gider)"

# ==========================================
# 8. ÖDEMELER
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
    
    ilgili_satinalma = models.ForeignKey(
        SatinAlma, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="İlgili Satınalma / Fatura"
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
        verbose_name_plural = "6. Ödemeler"

# ==========================================
# 9. HAREKET GEÇMİŞİ & SEVKİYAT
# ==========================================

class DepoHareket(models.Model):
    ISLEM_TURLERI = [
        ('giris', '📥 Depo Girişi (Satınalma/Transfer)'),
        ('cikis', '📤 Depo Çıkışı (Kullanım/Transfer)'),
        ('iade', '↩️ İade / Red (Kusurlu Mal)'),
    ]
    
    IADE_AKSIYONLARI = [
        ('yok', '-'),
        ('degisim', '🔄 Yenisi Gelecek (Borç Düşme)'),
        ('iptal', '⛔ İptal Et / Faturadan Düş (Borç Düş)'),
    ]

    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, related_name='hareketler')
    depo = models.ForeignKey(Depo, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="İlgili Depo")
    # 'SatinAlma' string referansı, model sırasından kaynaklı hatayı önler
    siparis = models.ForeignKey('SatinAlma', on_delete=models.SET_NULL, null=True, blank=True, related_name='depo_hareketleri', verbose_name="Bağlı Sipariş")
    
    tarih = models.DateField(default=timezone.now)
    islem_turu = models.CharField(max_length=10, choices=ISLEM_TURLERI)
    miktar = models.FloatField(verbose_name="Miktar")
    
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Tedarikçi (Giriş ise)")
    irsaliye_no = models.CharField(max_length=50, blank=True, verbose_name="İrsaliye No")
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama / Kullanılan Yer")
    
    iade_sebebi = models.CharField(max_length=200, blank=True, verbose_name="Red Sebebi")
    iade_aksiyonu = models.CharField(max_length=20, choices=IADE_AKSIYONLARI, default='yok', verbose_name="İade Sonucu")
    kanit_gorseli = models.ImageField(upload_to='depo_kanit/', blank=True, null=True, verbose_name="Hasar/Kanıt Fotoğrafı")

    def __str__(self):
        return f"{self.get_islem_turu_display()} - {self.malzeme.isim}"

    class Meta:
        verbose_name = "Hareket Geçmişi (Log)"
        verbose_name_plural = "Hareket Geçmişi (Log)"


class DepoTransfer(models.Model):
    kaynak_depo = models.ForeignKey(Depo, on_delete=models.CASCADE, related_name='cikis_transferleri', verbose_name="Kaynak Depo (Nereden?)")
    hedef_depo = models.ForeignKey(Depo, on_delete=models.CASCADE, related_name='giris_transferleri', verbose_name="Hedef Depo (Nereye?)")
    
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, verbose_name="Taşınacak Malzeme")
    miktar = models.FloatField(verbose_name="Transfer Miktarı")
    
    tarih = models.DateField(default=timezone.now)
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Transfer Notu (Plaka vb.)")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            # Views.py'dan geçici olarak iliştirilen sipariş bilgisini al
            # Eğer normal transferse bu boş (None) olur, sorun çıkmaz.
            siparis_obj = getattr(self, 'bagli_siparis', None)

            # 1. Kaynak Depo ÇIKIŞI
            DepoHareket.objects.create(
                malzeme=self.malzeme,
                depo=self.kaynak_depo,
                tarih=self.tarih,
                islem_turu='cikis',
                miktar=self.miktar,
                siparis=siparis_obj, # <--- ARTIK SİPARİŞİ TANIYOR
                aciklama=f"TRANSFER ÇIKIŞI -> {self.hedef_depo.isim} | {self.aciklama}"
            )
            
            # 2. Hedef Depo GİRİŞİ
            DepoHareket.objects.create(
                malzeme=self.malzeme,
                depo=self.hedef_depo,
                tarih=self.tarih,
                islem_turu='giris',
                miktar=self.miktar,
                siparis=siparis_obj, # <--- ARTIK SİPARİŞİ TANIYOR
                aciklama=f"TRANSFER GİRİŞİ <- {self.kaynak_depo.isim} | {self.aciklama}"
            )

    class Meta:
        verbose_name = "8. Sevkiyat (Mal Kabul)"
        verbose_name_plural = "8. Sevkiyat (Mal Kabul)"


# ==========================================
# 10. TAŞERON HAKEDİŞ YÖNETİMİ
# ==========================================

class Hakedis(models.Model):
    satinalma = models.ForeignKey(SatinAlma, on_delete=models.CASCADE, related_name='hakedisler', verbose_name="İlgili Sözleşme/Sipariş", null=True, blank=True)
    
    hakedis_no = models.PositiveIntegerField(default=1, verbose_name="Hakediş No")
    tarih = models.DateField(default=timezone.now)
    
    donem_baslangic = models.DateField(verbose_name="Dönem Başı")
    donem_bitis = models.DateField(verbose_name="Dönem Sonu")
    
    tamamlanma_orani = models.FloatField(verbose_name="Bu Dönem Tamamlanma (%)", help_text="Örn: 10 girerseniz işin %10'u bitmiş sayılır.")
    
    malzeme_zayiati = models.FloatField(default=0, verbose_name="Malzeme / Zayiat Kesintisi (TL)")
    diger_kesintiler = models.FloatField(default=0, verbose_name="Diğer Kesintiler (Avans/Stopaj vb.)")
    
    onay_durumu = models.BooleanField(default=False, verbose_name="Hakediş Onaylandı mı?")
    
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def hakedis_tutari(self):
        sozlesme_tutari = self.satinalma.teklif.toplam_fiyat_tl
        return sozlesme_tutari * (self.tamamlanma_orani / 100)

    @property
    def odenecek_net_tutar(self):
        return self.hakedis_tutari - (self.malzeme_zayiati + self.diger_kesintiler)

    def __str__(self):
        return f"{self.satinalma.teklif.tedarikci} - Hakediş #{self.hakedis_no}"

    class Meta:
        verbose_name_plural = "Taşeron Hakedişleri"


class Fatura(models.Model):
    """
    Tedarikçiden gelen resmi faturanın sisteme işlendiği model.
    ARTIK OTOMATİK STOK HAREKETİ YARATMAZ. Sadece finansal kayıttır.
    Otomatik stok, views.py içinde checkbox kontrolü ile yapılır.
    """
    satinalma = models.ForeignKey(SatinAlma, on_delete=models.CASCADE, related_name='faturalar', verbose_name="İlgili Sipariş")
    
    fatura_no = models.CharField(max_length=50, verbose_name="Fatura No")
    tarih = models.DateField(default=timezone.now, verbose_name="Fatura Tarihi")
    
    miktar = models.FloatField(verbose_name="Fatura Edilen Miktar")
    tutar = models.FloatField(verbose_name="Fatura Tutarı (KDV Dahil)")
    
    depo = models.ForeignKey(Depo, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Giriş Yapılacak Depo")
    
    dosya = models.FileField(upload_to='faturalar/', blank=True, null=True, verbose_name="Fatura Görseli/PDF")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super(Fatura, self).save(*args, **kwargs)
        
        # Sadece faturalanan miktarı güncelle (Stok/Teslimat'a dokunma!)
        if is_new:
            self.satinalma.faturalanan_miktar += self.miktar
            self.satinalma.save()

    def __str__(self):
        return f"Fatura #{self.fatura_no} - {self.satinalma.teklif.tedarikci}"

    class Meta:
        verbose_name = "Alış Faturası"
        verbose_name_plural = "Alış Faturaları"