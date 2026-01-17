from django.db import models
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from django.core.exceptions import ValidationError
from core.utils import to_decimal

# ==========================================
# SABİTLER (GLOBAL)
# ==========================================

KDV_ORANLARI = [
    (-1, 'KDV Muaf / Özel Matrah'),
    (0, '%0'), 
    (5, '%5'), 
    (10, '%10'), 
    (16, '%16'), 
    (20, '%20')
]

PARA_BIRIMI_CHOICES = [
    ('TRY', 'Türk Lirası (₺)'),
    ('USD', 'Amerikan Doları ($)'),
    ('EUR', 'Euro (€)'),
    ('GBP', 'İngiliz Sterlini (£)'),
]

# ==========================================
# 1. KATEGORİ VE İMALAT YAPISI
# ==========================================

class Kategori(models.Model):
    isim = models.CharField(max_length=100, verbose_name="Kategori Adı")
    
    def __str__(self):
        return self.isim if self.isim else "Tanımsız Kategori"
    
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
    hedef_miktar = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="Yaklaşık Metraj")
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
        return self.firma_unvani if self.firma_unvani else "Tanımsız Firma"
    
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
    marka = models.CharField(max_length=100, blank=True, verbose_name="Marka / Model")
    birim = models.CharField(max_length=20, choices=IsKalemi.BIRIMLER, default='adet')
    kdv_orani = models.IntegerField(choices=KDV_ORANLARI, default=20, verbose_name="Varsayılan KDV (%)")
    kritik_stok = models.DecimalField(max_digits=10, decimal_places=2, default=10, verbose_name="Kritik Stok Uyarı Limiti")
    aciklama = models.TextField(blank=True, verbose_name="Teknik Özellikler / Notlar")
    
    @property
    def stok(self):
        giren = self.hareketler.filter(islem_turu='giris').aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        cikan = self.hareketler.filter(islem_turu='cikis').aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        iade_iptal = self.hareketler.filter(islem_turu='iade', iade_aksiyonu='iptal').aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        return giren - cikan - iade_iptal

    def depo_stogu(self, depo_id):
        giren = self.hareketler.filter(depo_id=depo_id, islem_turu='giris').aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        cikan = self.hareketler.filter(depo_id=depo_id, islem_turu='cikis').aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        iade_iptal = self.hareketler.filter(depo_id=depo_id, islem_turu='iade', iade_aksiyonu='iptal').aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
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
    
    malzeme = models.ForeignKey(Malzeme, on_delete=models.SET_NULL, related_name='talepler', null=True, blank=True, verbose_name="Malzeme (Satınalma)")
    is_kalemi = models.ForeignKey(IsKalemi, on_delete=models.SET_NULL, related_name='talepler', null=True, blank=True, verbose_name="İş Kalemi (Hizmet/Taşeron)")
    
    miktar = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="İstenen Miktar")
    oncelik = models.CharField(max_length=10, choices=ONCELIKLER, default='normal', verbose_name="Aciliyet Durumu")
    
    proje_yeri = models.CharField(max_length=200, blank=True, null=True, verbose_name="Kullanılacak Yer")
    aciklama = models.TextField(blank=True, null=True, verbose_name="Notlar")
    
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
        if self.malzeme: ad = self.malzeme.isim
        elif self.is_kalemi: ad = self.is_kalemi.isim
        else: ad = "Silinmiş/Tanımsız Kalem"
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
    
    talep = models.ForeignKey(MalzemeTalep, on_delete=models.CASCADE, related_name='teklifler', null=True, blank=True, verbose_name="İlgili Talep")
    
    is_kalemi = models.ForeignKey(IsKalemi, on_delete=models.CASCADE, related_name='teklifler', null=True, blank=True, verbose_name="İş Kalemi (Taşeronluk)")
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, related_name='teklifler', null=True, blank=True, verbose_name="Malzeme (Satınalma)")
    
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.CASCADE, related_name='teklifler')
    
    miktar = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="Teklif Miktarı")
    birim_fiyat = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Birim Fiyat (KDV Hariç)")
    
    para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMI_CHOICES, default='TRY')
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
        super(Teklif, self).save(*args, **kwargs)

    @property
    def toplam_fiyat_tl(self):
        kdv_carpani = Decimal(0) if self.kdv_orani == -1 else Decimal(self.kdv_orani)
        tutar_ham = to_decimal(self.birim_fiyat) * to_decimal(self.miktar)
        
        if self.kdv_dahil_mi:
             tutar_tl = tutar_ham * to_decimal(self.kur_degeri)
        else:
            tutar_tl = (tutar_ham * to_decimal(self.kur_degeri)) * (Decimal('1') + (kdv_carpani / Decimal('100')))
            
        return tutar_tl.quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)
    
    @property
    def toplam_fiyat_orijinal(self):
        kdv_carpani = Decimal(0) if self.kdv_orani == -1 else Decimal(self.kdv_orani)
        ham_tutar = to_decimal(self.birim_fiyat) * to_decimal(self.miktar)
        
        if not self.kdv_dahil_mi:
            kdvli_tutar = ham_tutar * (Decimal('1') + (kdv_carpani / Decimal('100')))
        else:
            kdvli_tutar = ham_tutar
            
        return kdvli_tutar.quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)

    @property
    def birim_fiyat_kdvli(self):
        kdv_carpani = Decimal(0) if self.kdv_orani == -1 else Decimal(self.kdv_orani)
        
        if self.kdv_dahil_mi:
            return to_decimal(self.birim_fiyat)
        else:
            return to_decimal(self.birim_fiyat) * (Decimal('1') + (kdv_carpani / Decimal('100')))

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
    
    toplam_miktar = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Sipariş Edilen Toplam")
    
    teslim_edilen = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Depoya Giren (Fiziksel)")
    faturalanan_miktar = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Faturası Gelen (Finansal)")
    fiili_odenen_tutar = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Şu Ana Kadar Ödenen")
    
    aciklama = models.TextField(blank=True, verbose_name="Notlar")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.teslim_edilen == 0:
            self.teslimat_durumu = 'bekliyor'
        elif 0 < self.teslim_edilen < self.toplam_miktar:
            self.teslimat_durumu = 'kismi'
        elif self.teslim_edilen >= self.toplam_miktar:
            self.teslimat_durumu = 'tamamlandi'
            
        super(SatinAlma, self).save(*args, **kwargs)

    @property
    def kalan_miktar(self):
        return max(self.toplam_miktar - self.teslim_edilen, Decimal('0'))

    @property
    def kalan_fatura_miktar(self):
        return max(self.toplam_miktar - self.faturalanan_miktar, Decimal('0'))

    @property
    def tamamlanma_yuzdesi(self):
        if self.toplam_miktar == 0: return Decimal('0')
        yuzde = (self.teslim_edilen / self.toplam_miktar) * Decimal('100')
        return min(yuzde, Decimal('100'))

    @property
    def sanal_depoda_bekleyen(self):
        girisler = self.depo_hareketleri.filter(depo__is_sanal=True, islem_turu='giris').aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        cikislar = self.depo_hareketleri.filter(depo__is_sanal=True, islem_turu='cikis').aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        return max(girisler - cikislar, Decimal('0'))

    def __str__(self):
        return f"{self.teklif.tedarikci} - {self.teklif.malzeme.isim if self.teklif.malzeme else self.teklif.is_kalemi.isim} (Kalan: {self.kalan_miktar})"

    class Meta:
        verbose_name = "4. Satınalma & Siparişler"
        verbose_name_plural = "4. Satınalma & Siparişler"


# ==========================================
# 7. GİDERLER (OPEX)
# ==========================================

class GiderKategorisi(models.Model):
    isim = models.CharField(max_length=100, verbose_name="Gider Kategorisi")
    
    def __str__(self):
        return self.isim if self.isim else "Tanımsız Kategori"
    
    class Meta:
        verbose_name = "Gider Tanımı"
        verbose_name_plural = "Gider Tanımları"

class Harcama(models.Model):
    kategori = models.ForeignKey(
        GiderKategorisi, 
        on_delete=models.CASCADE, 
        related_name='harcamalar',
        verbose_name="Gider Türü"
    )
    aciklama = models.CharField(max_length=200, verbose_name="Harcama Açıklaması")
    
    tutar = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Tutar")
    para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMI_CHOICES, default='TRY', verbose_name="Para Birimi")
    
    kur_degeri = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000, verbose_name="İşlem Kuru")
    
    tarih = models.DateField(default=timezone.now, verbose_name="Harcama Tarihi")
    dekont = models.FileField(upload_to='harcamalar/', blank=True, null=True, verbose_name="Dekont / Fiş")

    @property
    def tl_tutar(self):
        return (to_decimal(self.tutar) * to_decimal(self.kur_degeri)).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)

    def __str__(self):
        kat_ismi = self.kategori.isim if self.kategori else "Kategorisiz"
        return f"{self.aciklama} ({kat_ismi}) - {self.tutar} {self.para_birimi}"
    
    class Meta:
        verbose_name = "5. Harcama (Gider)"
        verbose_name_plural = "5. Harcamalar (Gider)"
        ordering = ['-tarih']


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
    siparis = models.ForeignKey('SatinAlma', on_delete=models.SET_NULL, null=True, blank=True, related_name='depo_hareketleri', verbose_name="Bağlı Sipariş")
    
    tarih = models.DateField(default=timezone.now)
    islem_turu = models.CharField(max_length=10, choices=ISLEM_TURLERI)
    
    miktar = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Miktar")
    
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
    bagli_siparis = models.ForeignKey('SatinAlma', related_name='transferler', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Bağlı Sipariş")
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, verbose_name="Taşınacak Malzeme")
    
    miktar = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Transfer Miktarı")
    
    tarih = models.DateField(default=timezone.now)
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Transfer Notu (Plaka vb.)")
    
    created_at = models.DateTimeField(auto_now_add=True)

    # DİKKAT: save() metodu temizlendi. 
    # DepoHareket oluşturma mantığı core/signals.py dosyasına taşındı.

    class Meta:
        verbose_name = "8. Sevkiyat (Mal Kabul)"
        verbose_name_plural = "8. Sevkiyat (Mal Kabul)"


# ==========================================
# 10. TAŞERON HAKEDİŞ YÖNETİMİ
# ==========================================

class Hakedis(models.Model):
    satinalma = models.ForeignKey('SatinAlma', on_delete=models.CASCADE, related_name='hakedisler', verbose_name="İlgili Sözleşme")
    
    hakedis_no = models.PositiveIntegerField(default=1, verbose_name="Hakediş No")
    tarih = models.DateField(default=timezone.now, verbose_name="Hakediş Tarihi")
    
    donem_baslangic = models.DateField(verbose_name="Dönem Başı", null=True, blank=True)
    donem_bitis = models.DateField(verbose_name="Dönem Sonu", null=True, blank=True)
    
    aciklama = models.TextField(blank=True, verbose_name="Yapılan İşin Açıklaması")
    
    tamamlanma_orani = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Bu Dönem İlerleme (%)")
    
    brut_tutar = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Hakediş Tutarı (KDV Hariç)")
    
    kdv_orani = models.PositiveIntegerField(default=20, verbose_name="KDV (%)")
    kdv_tutari = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="KDV Tutarı")
    
    stopaj_orani = models.PositiveIntegerField(default=0, verbose_name="Stopaj (%)", help_text="Genelde %3")
    stopaj_tutari = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Kesilen Stopaj")
    
    teminat_orani = models.PositiveIntegerField(default=0, verbose_name="Teminat (%)", help_text="Genelde %5 veya %10")
    teminat_tutari = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Kesilen Teminat")
    
    avans_kesintisi = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Avans Kesintisi")
    diger_kesintiler = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Malzeme/Ceza vb.")
    
    odenecek_net_tutar = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Ödenecek Net Tutar")
    fiili_odenen_tutar = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Şu Ana Kadar Ödenen")

    onay_durumu = models.BooleanField(default=False, verbose_name="Onaylandı")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # NOT: Dış servis çağrısı (tcmb_kur_getir) kaldırıldı.
        # Artık kur bilgisi View katmanında çekilip modele işlenmeli.
        # Burada sadece mevcut verilerle matematiksel işlem yapılıyor.
        
        try:
            teklif = self.satinalma.teklif
            islem_kuru = to_decimal(teklif.kur_degeri) # Varsayılan: Sabit Kur

            # Eğer view tarafında kur güncellendiyse (veya buraya kur parametresi eklenseydi)
            # o kullanılabilirdi. Şimdilik "save" anında blocking istek yapmıyoruz.
            
            birim_fiyat = to_decimal(teklif.birim_fiyat)
            
            if teklif.kdv_dahil_mi:
                kdv_orani_teklif = to_decimal(teklif.kdv_orani)
                birim_fiyat = birim_fiyat / (Decimal('1.0') + (kdv_orani_teklif / Decimal('100.0')))

            miktar = to_decimal(self.satinalma.toplam_miktar)
            sozlesme_toplam_tl = birim_fiyat * miktar * islem_kuru

            if self.tamamlanma_orani:
                oran = to_decimal(self.tamamlanma_orani)
                self.brut_tutar = sozlesme_toplam_tl * (oran / Decimal('100.0'))
            else:
                self.brut_tutar = Decimal('0.00')
                
        except Exception as e:
            print(f"Hakediş hesaplama hatası: {e}")
            self.brut_tutar = Decimal('0.00')

        try:
            kdv_orani = to_decimal(self.kdv_orani or 0)
            stopaj_orani = to_decimal(self.stopaj_orani or 0)
            teminat_orani = to_decimal(self.teminat_orani or 0)
            avans_kesintisi = to_decimal(self.avans_kesintisi or 0)
            diger_kesintiler = to_decimal(self.diger_kesintiler or 0)

            self.kdv_tutari = self.brut_tutar * (kdv_orani / Decimal('100.0'))
            self.stopaj_tutari = self.brut_tutar * (stopaj_orani / Decimal('100.0'))
            self.teminat_tutari = self.brut_tutar * (teminat_orani / Decimal('100.0'))
            
            toplam_alacak = self.brut_tutar + self.kdv_tutari
            toplam_kesinti = self.stopaj_tutari + self.teminat_tutari + avans_kesintisi + diger_kesintiler
            
            self.odenecek_net_tutar = toplam_alacak - toplam_kesinti
            
        except Exception as e:
            print(f"Net tutar hesaplama hatası: {e}")
            pass

        super(Hakedis, self).save(*args, **kwargs)

    def __str__(self):
        try:
            tedarikci_adi = self.satinalma.teklif.tedarikci.firma_unvani
        except (AttributeError, models.ObjectDoesNotExist):
            tedarikci_adi = "Bilinmeyen Tedarikçi"
        return f"Hakediş #{self.hakedis_no} - {tedarikci_adi}"

    class Meta:
        verbose_name_plural = "6. Taşeron Hakedişleri"
        ordering = ['-tarih']

class Fatura(models.Model):
    satinalma = models.ForeignKey(SatinAlma, on_delete=models.CASCADE, related_name='faturalar', verbose_name="İlgili Sipariş")
    
    fatura_no = models.CharField(max_length=50, verbose_name="Fatura No")
    tarih = models.DateField(default=timezone.now, verbose_name="Fatura Tarihi")
    
    miktar = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Fatura Edilen Miktar")
    tutar = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Fatura Tutarı (KDV Dahil)")
    
    depo = models.ForeignKey(Depo, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Giriş Yapılacak Depo")
    
    dosya = models.FileField(upload_to='faturalar/', blank=True, null=True, verbose_name="Fatura Görseli/PDF")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super(Fatura, self).save(*args, **kwargs)
        
        if is_new:
            self.satinalma.faturalanan_miktar += self.miktar
            self.satinalma.save()

    def __str__(self):
        try:
            ted_adi = self.satinalma.teklif.tedarikci.firma_unvani
        except:
            ted_adi = "Bilinmeyen"
        return f"Fatura #{self.fatura_no} - {ted_adi}"

    class Meta:
        verbose_name = "Alış Faturası"
        verbose_name_plural = "Alış Faturaları"

class Odeme(models.Model):
    ODEME_TURLERI = [
        ('nakit', 'Nakit'),
        ('havale', 'Havale / EFT'),
        ('cek', 'Çek'),
    ]
    
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.CASCADE, related_name='odemeler', verbose_name="Ödenen Firma")
    bagli_hakedis = models.ForeignKey('Hakedis', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="İlgili Hakediş")
    
    tarih = models.DateField(default=timezone.now, verbose_name="İşlem Tarihi")
    odeme_turu = models.CharField(max_length=10, choices=ODEME_TURLERI, default='nakit', verbose_name="Ödeme Yöntemi")
    
    tutar = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Ödenen Tutar")
    para_birimi = models.CharField(max_length=3, choices=PARA_BIRIMI_CHOICES, default='TRY', verbose_name="Para Birimi")
    
    banka_adi = models.CharField(max_length=100, blank=True, verbose_name="Banka Adı")
    cek_no = models.CharField(max_length=50, blank=True, verbose_name="Çek No / Dekont No")
    vade_tarihi = models.DateField(null=True, blank=True, verbose_name="Çek Vadesi")
    
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Açıklama")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.odeme_turu == 'cek' and not self.vade_tarihi:
            self.vade_tarihi = self.tarih
        super(Odeme, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.tedarikci} - {self.tutar} {self.para_birimi} ({self.get_odeme_turu_display()})"

    class Meta:
        verbose_name = "7. Ödeme & Çek Çıkışı"
        verbose_name_plural = "7. Ödeme & Çek Çıkışı"
        ordering = ['-tarih']