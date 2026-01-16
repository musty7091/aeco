from django.db import models
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum, Q
from django.core.exceptions import ValidationError
# from core.utils import to_decimal # Bu satır eğer utils dosyanız yoksa hata verebilir, gerekirse yorum satırı yapın.

# ==========================================
# SABİTLER
# ==========================================

KDV_ORANLARI = [
    (0, '%0'), 
    (5, '%5'), 
    (10, '%10'), 
    (16, '%16'), 
    (20, '%20')
]

# ==========================================
# ENUM Sınıfları (Sabitler)
# ==========================================

class ParaBirimi(models.TextChoices):
    TL = 'TRY', 'Türk Lirası (₺)'
    USD = 'USD', 'Amerikan Doları ($)'
    EUR = 'EUR', 'Euro (€)'
    GBP = 'GBP', 'İngiliz Sterlini (£)'

class DepoTuru(models.TextChoices):
    MERKEZ = 'merkez', '🏢 Merkez Depo (Ana Stok)'
    BAGLANTI = 'baglanti', '🔗 Bağlantı Deposu (Tedarikçide)'
    KULLANIM = 'kullanim', '🔨 Kullanım Deposu (Şantiye/Tüketim)'

class IslemTuru(models.TextChoices):
    GIRIS = 'giris', '📥 Giriş (Satınalma)'
    CIKIS = 'cikis', '📤 Çıkış (Tüketim)'
    TRANSFER = 'transfer', '🔄 Transfer'
    IADE = 'iade', '↩️ İade'

class Birimler(models.TextChoices):
    ADET = 'adet', 'Adet'
    M2 = 'm2', 'Metrekare (m²)'
    M3 = 'm3', 'Metreküp (m³)'
    KG = 'kg', 'Kilogram (kg)'
    TON = 'ton', 'Ton'
    MT = 'mt', 'Metre (mt)'
    ADAM_SAAT = 'adam_saat', 'Adam/Saat'
    GOTURU = 'goturu', 'Götürü (Toplu)'

# ==========================================
# 1. KATEGORİ VE İMALAT YAPISI
# ==========================================

class Kategori(models.Model):
    isim = models.CharField(max_length=100, verbose_name="Kategori Adı")
    
    def __str__(self):
        return self.isim

class IsKalemi(models.Model):
    kategori = models.ForeignKey(Kategori, on_delete=models.CASCADE, related_name='kalemler')
    isim = models.CharField(max_length=200, verbose_name="İş Kalemi Adı")
    birim = models.CharField(max_length=20, choices=Birimler.choices, default=Birimler.ADET)
    aciklama = models.TextField(blank=True, verbose_name="Teknik Şartname")
    
    def __str__(self):
        return self.isim

# ==========================================
# 2. DEPO VE STOK YÖNETİMİ
# ==========================================

class Depo(models.Model):
    isim = models.CharField(max_length=100, verbose_name="Depo Adı")
    tur = models.CharField(
        max_length=20, 
        choices=DepoTuru.choices, 
        default=DepoTuru.MERKEZ,
        verbose_name="Depo Türü"
    )
    adres = models.CharField(max_length=200, blank=True)
    
    def __str__(self):
        return f"{self.isim} ({self.get_tur_display()})"

    class Meta:
        verbose_name = "Depo Tanımı"
        verbose_name_plural = "Depo Tanımları"

class Malzeme(models.Model):
    isim = models.CharField(max_length=200, verbose_name="Malzeme Adı")
    birim = models.CharField(max_length=20, choices=Birimler.choices, default=Birimler.ADET)
    marka = models.CharField(max_length=100, blank=True, verbose_name="Marka")
    kritik_stok = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    kdv_orani = models.IntegerField(choices=KDV_ORANLARI, default=20, verbose_name="KDV Oranı")
    
    @property
    def stok(self):
        hareketler = self.hareketler.filter(
            depo__tur__in=[DepoTuru.MERKEZ, DepoTuru.BAGLANTI]
        )
        giren = hareketler.filter(islem_turu__in=[IslemTuru.GIRIS, IslemTuru.TRANSFER, IslemTuru.IADE])\
                          .aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        cikan = hareketler.filter(islem_turu__in=[IslemTuru.CIKIS, IslemTuru.TRANSFER])\
                          .aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        return giren - cikan

    def depo_stogu(self, depo_id):
        h = self.hareketler.filter(depo_id=depo_id)
        giren = h.filter(islem_turu__in=[IslemTuru.GIRIS, IslemTuru.TRANSFER, IslemTuru.IADE])\
                 .aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        cikan = h.filter(islem_turu__in=[IslemTuru.CIKIS, IslemTuru.TRANSFER])\
                 .aggregate(Sum('miktar'))['miktar__sum'] or Decimal('0')
        return giren - cikan

    def __str__(self):
        return f"{self.isim} ({self.marka})" if self.marka else self.isim

class Tedarikci(models.Model):
    firma_unvani = models.CharField(max_length=200, verbose_name="Firma Ünvanı")
    yetkili = models.CharField(max_length=100, blank=True)
    telefon = models.CharField(max_length=20, blank=True)
    
    def __str__(self):
        return self.firma_unvani

# ==========================================
# 3. HAREKET GEÇMİŞİ
# ==========================================

class DepoHareket(models.Model):
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, related_name='hareketler')
    depo = models.ForeignKey(Depo, on_delete=models.CASCADE, related_name='hareketler')
    
    islem_turu = models.CharField(max_length=20, choices=IslemTuru.choices)
    miktar = models.DecimalField(max_digits=10, decimal_places=2)
    tarih = models.DateTimeField(default=timezone.now)
    
    transfer = models.ForeignKey('DepoTransfer', on_delete=models.SET_NULL, null=True, blank=True, related_name='hareket_loglari')
    aciklama = models.CharField(max_length=300, blank=True)
    
    def __str__(self):
        return f"{self.malzeme.isim} - {self.get_islem_turu_display()}"

class DepoTransfer(models.Model):
    kaynak_depo = models.ForeignKey(Depo, on_delete=models.CASCADE, related_name='cikis_transferleri')
    hedef_depo = models.ForeignKey(Depo, on_delete=models.CASCADE, related_name='giris_transferleri')
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE)
    miktar = models.DecimalField(max_digits=10, decimal_places=2)
    tarih = models.DateTimeField(default=timezone.now)
    aciklama = models.CharField(max_length=200, blank=True)
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            DepoHareket.objects.create(
                malzeme=self.malzeme,
                depo=self.kaynak_depo,
                islem_turu=IslemTuru.TRANSFER,
                miktar=self.miktar * -1,
                tarih=self.tarih,
                transfer=self,
                aciklama=f"Transfer: {self.hedef_depo.isim} deposuna sevk"
            )
            DepoHareket.objects.create(
                malzeme=self.malzeme,
                depo=self.hedef_depo,
                islem_turu=IslemTuru.TRANSFER,
                miktar=self.miktar, 
                tarih=self.tarih,
                transfer=self,
                aciklama=f"Transfer: {self.kaynak_depo.isim} deposundan gelen"
            )

# ==========================================
# 4. TALEP VE SATINALMA SÜRECİ
# ==========================================

class MalzemeTalep(models.Model):
    DURUM_CHOICES = [
        ('bekliyor', '⏳ Onay Bekliyor'),
        ('islemde', '⚙️ Satınalma Sürecinde'),
        ('tamamlandi', '✅ Tamamlandı'),
        ('iptal', '❌ İptal'),
    ]
    
    talep_eden = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, related_name='talepler')
    miktar = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="İstenen Miktar")
    proje_yeri = models.CharField(max_length=200, blank=True, verbose_name="Kullanılacak Yer")
    
    durum = models.CharField(max_length=20, choices=DURUM_CHOICES, default='bekliyor')
    tarih = models.DateTimeField(default=timezone.now)
    aciklama = models.TextField(blank=True)

    def __str__(self):
        return f"{self.malzeme.isim} - {self.miktar} {self.malzeme.get_birim_display()}"

class Teklif(models.Model):
    DURUM_CHOICES = [
        ('beklemede', '⏳ Değerlendiriliyor'),
        ('onaylandi', '✅ Onaylandı (Sipariş)'),
        ('reddedildi', '❌ Reddedildi'),
    ]

    talep = models.ForeignKey(MalzemeTalep, on_delete=models.CASCADE, related_name='teklifler', null=True, blank=True)
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.CASCADE, related_name='teklifler')
    
    malzeme = models.ForeignKey(Malzeme, on_delete=models.CASCADE, null=True, blank=True)
    is_kalemi = models.ForeignKey(IsKalemi, on_delete=models.CASCADE, null=True, blank=True)

    fiyat = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Birim Fiyat")
    para_birimi = models.CharField(max_length=3, choices=ParaBirimi.choices, default=ParaBirimi.TL)
    
    # DÜZELTME: choices=KDV_ORANLARI eklendi
    kdv_orani = models.IntegerField(choices=KDV_ORANLARI, default=20, verbose_name="KDV (%)")
    kdv_dahil_mi = models.BooleanField(default=False)
    
    durum = models.CharField(max_length=20, choices=DURUM_CHOICES, default='beklemede')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def sonuc_tutar(self):
        """
        Birim fiyatın KDV dahil/hariç durumuna göre net maliyetini hesaplar.
        Şablonlarda (Template) göstermek için kullanılır.
        """
        if self.kdv_dahil_mi:
            # Fiyat zaten KDV'li ise olduğu gibi döner
            return self.fiyat
        else:
            # KDV hariçse üzerine eklenir
            tutar = self.fiyat * (1 + Decimal(self.kdv_orani) / 100)
            return tutar.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        if self.talep and not self.malzeme:
            self.malzeme = self.talep.malzeme
        super().save(*args, **kwargs)

class SatinAlma(models.Model):
    teklif = models.OneToOneField(Teklif, on_delete=models.CASCADE, related_name='siparis')
    siparis_tarihi = models.DateField(default=timezone.now)
    
    toplam_miktar = models.DecimalField(max_digits=10, decimal_places=2)
    teslim_edilen = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Depoya giren miktar")
    
    aciklama = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def kalan_miktar(self):
        return self.toplam_miktar - self.teslim_edilen

    def __str__(self):
        return f"Sipariş #{self.id} - {self.teklif.tedarikci}"

# ==========================================
# 5. FİNANS VE MUHASEBE
# ==========================================

class Fatura(models.Model):
    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.PROTECT, related_name='faturalar')
    
    siparis = models.ForeignKey(SatinAlma, on_delete=models.SET_NULL, null=True, blank=True, related_name='faturalar')
    hakedis = models.ForeignKey('Hakedis', on_delete=models.SET_NULL, null=True, blank=True, related_name='faturalar')
    
    fatura_no = models.CharField(max_length=50, verbose_name="Fatura No")
    tarih = models.DateField(default=timezone.now)
    son_odeme_tarihi = models.DateField(null=True, blank=True)
    
    tutar_kdv_haric = models.DecimalField(max_digits=15, decimal_places=2)
    kdv_tutari = models.DecimalField(max_digits=15, decimal_places=2)
    toplam_tutar = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Ödenecek Tutar")
    
    para_birimi = models.CharField(max_length=3, choices=ParaBirimi.choices, default=ParaBirimi.TL)
    kur = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000, help_text="Fatura tarihindeki kur")

    dosya = models.FileField(upload_to='faturalar/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.fatura_no} - {self.tedarikci} ({self.toplam_tutar} {self.para_birimi})"

class Odeme(models.Model):
    ODEME_TURU = [
        ('nakit', 'Nakit'),
        ('havale', 'Havale / EFT'),
        ('cek', 'Çek'),
    ]
    
    CEK_DURUMU = [
        ('beklemede', '⏳ Müşteride / Bekliyor'),
        ('tahsil_edildi', '✅ Tahsil Edildi (Hesaptan Düştü)'),
        ('karsiliksiz', '❌ Karşılıksız / İade'),
    ]

    tedarikci = models.ForeignKey(Tedarikci, on_delete=models.PROTECT, related_name='odemeler')
    
    bagli_fatura = models.ForeignKey(Fatura, on_delete=models.SET_NULL, null=True, blank=True, related_name='odemeler')
    
    tarih = models.DateField(default=timezone.now, verbose_name="İşlem Tarihi")
    odeme_turu = models.CharField(max_length=10, choices=ODEME_TURU, default='havale')
    
    tutar = models.DecimalField(max_digits=15, decimal_places=2)
    para_birimi = models.CharField(max_length=3, choices=ParaBirimi.choices, default=ParaBirimi.TL)
    kur = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000)
    
    banka_adi = models.CharField(max_length=100, blank=True)
    cek_no = models.CharField(max_length=50, blank=True)
    vade_tarihi = models.DateField(null=True, blank=True)
    cek_durumu = models.CharField(max_length=20, choices=CEK_DURUMU, default='beklemede')
    
    aciklama = models.CharField(max_length=200, blank=True)

    @property
    def cariye_etkisi(self):
        if self.odeme_turu == 'cek' and self.cek_durumu != 'tahsil_edildi':
            return Decimal('0')
        return self.tutar

    def __str__(self):
        return f"{self.tedarikci} - {self.tutar} {self.para_birimi}"

# ==========================================
# 6. TAŞERON VE HAKEDİŞ SİSTEMİ
# ==========================================

class Hakedis(models.Model):
    sozlesme = models.ForeignKey(SatinAlma, on_delete=models.CASCADE, related_name='hakedisler')
    hakedis_no = models.PositiveIntegerField()
    tarih = models.DateField(default=timezone.now)
    
    onceki_toplam_yuzde = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    bu_donem_yuzde = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Bu Dönem İlerleme (%)")
    kümülatif_yuzde = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Toplam İlerleme (%)")
    
    hakedis_tutari = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Hakediş Tutarı (KDV Hariç)")
    
    kesintiler_toplami = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Avans, Stopaj vb.")
    odenmesi_gereken = models.DecimalField(max_digits=15, decimal_places=2)
    
    onaylandi = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.pk:
            onceki = Hakedis.objects.filter(sozlesme=self.sozlesme).order_by('-hakedis_no').first()
            if onceki:
                self.hakedis_no = onceki.hakedis_no + 1
                self.onceki_toplam_yuzde = onceki.kümülatif_yuzde
            else:
                self.hakedis_no = 1
                self.onceki_toplam_yuzde = 0
            
            self.kümülatif_yuzde = self.onceki_toplam_yuzde + self.bu_donem_yuzde
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sozlesme.teklif.tedarikci} - Hakediş #{self.hakedis_no}"
    
# ==========================================
# 7. GENEL GİDERLER (OPEX)
# ==========================================

class GiderKategorisi(models.Model):
    isim = models.CharField(max_length=100, verbose_name="Gider Kategorisi")
    
    def __str__(self):
        return self.isim
    
    class Meta:
        verbose_name = "Gider Kategorisi"
        verbose_name_plural = "Gider Kategorileri"

class Harcama(models.Model):
    kategori = models.ForeignKey(GiderKategorisi, on_delete=models.CASCADE, related_name='harcamalar')
    aciklama = models.CharField(max_length=200, verbose_name="Harcama Açıklaması")
    
    tutar = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Tutar")
    para_birimi = models.CharField(max_length=3, choices=ParaBirimi.choices, default=ParaBirimi.TL)
    kur = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000)
    
    tarih = models.DateField(default=timezone.now)
    dekont = models.FileField(upload_to='harcamalar/', blank=True, null=True)

    def __str__(self):
        return f"{self.aciklama} - {self.tutar} {self.para_birimi}"
    
    class Meta:
        verbose_name = "Genel Gider (Harcama)"
        verbose_name_plural = "Genel Giderler (Harcama)"