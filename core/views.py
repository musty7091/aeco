import json
from django.contrib.auth import logout
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.db.models import Sum
from django.contrib.auth.decorators import login_required 
from django.contrib import messages
from .models import (
    Kategori, GiderKategorisi, Teklif, Odeme, Harcama, 
    Tedarikci, Malzeme, DepoHareket, Hakedis, MalzemeTalep
)
from .utils import tcmb_kur_getir
from .forms import TeklifForm, TedarikciForm, MalzemeForm, TalepForm # Yeni formları import etmeyi unutmayın

# ========================================================
# 0. YARDIMCI GÜVENLİK FONKSİYONU
# ========================================================

def yetki_kontrol(user, izinli_gruplar):
    if user.is_superuser:
        return True
    if not user.groups.exists():
        return False
    user_groups = user.groups.values_list('name', flat=True)
    for grup in user_groups:
        if grup in izinli_gruplar:
            return True
    return False

def erisim_engellendi(request):
    return render(request, 'erisim_engellendi.html')

# ========================================================
# 1. ANA KARŞILAMA EKRANI
# ========================================================

@login_required
def dashboard(request):
    return render(request, 'dashboard.html')

# ========================================================
# 2. MODÜL 1: TEKLİF YÖNETİMİ (İCMAL & GİRİŞ)
# ========================================================

@login_required
def icmal_raporu(request):
    """
    GÜNCELLENMİŞ VERSİYON:
    Artık sabit kategorileri değil, yaşayan 'Malzeme Taleplerini' listeler.
    """
    # 1. Yetki Kontrolü
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    # 2. Veri Çekme (Talep Bazlı)
    # Bekleyen, İşlemde (Teklif Toplanan) veya Sipariş Onaylanmışları getir.
    # Tamamlanmış veya Reddedilmişleri listeyi şişirmemek için getirmiyoruz.
    aktif_talepler = MalzemeTalep.objects.filter(
        durum__in=['bekliyor', 'islemde', 'onaylandi']
    ).select_related(
        'malzeme', 'is_kalemi', 'talep_eden'  # <-- 'is_kalemi' EKLENDİ
    ).prefetch_related(
        'teklifler', 'teklifler__tedarikci'
    ).order_by('-oncelik', '-tarih')

    context = {'aktif_talepler': aktif_talepler}
    return render(request, 'icmal.html', context)

@login_required
def talep_olustur(request):
    """
    Saha ekibinin veya teknik ofisin yeni malzeme/hizmet talebi oluşturduğu ekran.
    """
    if request.method == 'POST':
        form = TalepForm(request.POST)
        if form.is_valid():
            talep = form.save(commit=False)
            talep.talep_eden = request.user 
            talep.durum = 'bekliyor' 
            talep.save()
            
            # --- HATA DÜZELTME: İSİM BELİRLEME ---
            # Eğer malzeme seçildiyse onun adını, iş kalemi seçildiyse onun adını al.
            if talep.malzeme:
                talep_adi = talep.malzeme.isim
            elif talep.is_kalemi:
                talep_adi = talep.is_kalemi.isim
            else:
                talep_adi = "Yeni Talep"
            # -------------------------------------
            
            messages.success(request, f"✅ {talep_adi} talebiniz oluşturuldu ve satınalma ekranına düştü.")
            
            # Yönlendirmeyi İcmal ekranına yapalım ki sonucu görebilsinler
            return redirect('icmal_raporu') 
        else:
            messages.error(request, "Lütfen alanları kontrol ediniz.")
    else:
        form = TalepForm()

    return render(request, 'talep_olustur.html', {'form': form})

@login_required
def teklif_ekle(request):
    """
    Sadeleştirilmiş Teklif Giriş Ekranı.
    Otomatik Kur Bilgisi ve TALEP BAĞLANTISI ile donatıldı.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    # URL'den gelen 'talep_id' varsa yakala
    talep_id = request.GET.get('talep_id')
    secili_talep = None
    
    # Form açılışında verileri hazırlamak için
    initial_data = {}

    if talep_id:
        secili_talep = get_object_or_404(MalzemeTalep, id=talep_id)
        # Formdaki alanları otomatik doldur
        initial_data['miktar'] = secili_talep.miktar
        if secili_talep.malzeme:
            initial_data['malzeme'] = secili_talep.malzeme
        if secili_talep.is_kalemi:
            initial_data['is_kalemi'] = secili_talep.is_kalemi

    # Canlı Kurları Çek ve JSON'a çevir (Frontend için)
    guncel_kurlar = tcmb_kur_getir()
    kurlar_dict = {k: float(v) for k, v in guncel_kurlar.items()}
    kurlar_dict['TRY'] = 1.0
    kurlar_json = json.dumps(kurlar_dict)

    if request.method == 'POST':
        form = TeklifForm(request.POST, request.FILES)
        if form.is_valid():
            teklif = form.save(commit=False)
            
            # --- KRİTİK DOKUNUŞ: TALEBİ TEKLİFE BAĞLA ---
            if talep_id:
                talep_obj = get_object_or_404(MalzemeTalep, id=talep_id)
                teklif.talep = talep_obj # İlişki burada kuruluyor!
                
                # Malzeme/Hizmet bilgisi formdan gelmese bile talepten zorla
                if talep_obj.malzeme: teklif.malzeme = talep_obj.malzeme
                if talep_obj.is_kalemi: teklif.is_kalemi = talep_obj.is_kalemi
            # ---------------------------------------------

            # KDV Oranını float'a çevir
            oran = int(form.cleaned_data['kdv_orani_secimi'])
            teklif.kdv_orani = float(oran)
            
            # Kur değerini veritabanına sabitle
            secilen_para = teklif.para_birimi
            teklif.kur_degeri = guncel_kurlar.get(secilen_para, 1.0)
            
            teklif.save()
            messages.success(request, f"✅ Teklif başarıyla kaydedildi ve talebe bağlandı.")
            return redirect('icmal_raporu')
        else:
            messages.error(request, "Lütfen formdaki hataları düzeltiniz.")
    else:
        form = TeklifForm(initial=initial_data)

    context = {
        'form': form,
        'kurlar_json': kurlar_json,
        'guncel_kurlar': guncel_kurlar,
        'secili_talep': secili_talep # Şablonda bilgi göstermek isterseniz diye
    }
    return render(request, 'teklif_ekle.html', context)

@login_required
def tedarikci_ekle(request):
    """
    Hızlı tedarikçi tanımlama ekranı.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    if request.method == 'POST':
        form = TedarikciForm(request.POST)
        if form.is_valid():
            ted = form.save()
            messages.success(request, f"✅ {ted.firma_unvani} başarıyla eklendi.")
            # Eğer popup/yeni sekme ise kapatma mesajı gösterilebilir, 
            # şimdilik listeye veya geldiği yere dönmesi mantıklı.
            return redirect('tedarikci_ekle') 
    else:
        form = TedarikciForm()

    return render(request, 'tedarikci_ekle.html', {'form': form})

@login_required
def malzeme_ekle(request):
    """
    Hızlı malzeme tanımlama ekranı.
    """
    if not yetki_kontrol(request.user, ['SAHA_EKIBI', 'OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    if request.method == 'POST':
        form = MalzemeForm(request.POST)
        if form.is_valid():
            mal = form.save()
            messages.success(request, f"✅ {mal.isim} stok kartı açıldı.")
            return redirect('malzeme_ekle')
    else:
        form = MalzemeForm()

    return render(request, 'malzeme_ekle.html', {'form': form})

@login_required
def teklif_durum_guncelle(request, teklif_id, yeni_durum):
    teklif = get_object_or_404(Teklif, id=teklif_id)
    
    if yeni_durum == 'onaylandi':
        # 1. Bu teklifi onayla
        teklif.durum = 'onaylandi'
        teklif.save()
        
        # 2. Talebe bağlı diğer teklifleri 'beklemede' veya 'red' yapabiliriz, 
        # ama genelde 'beklemede' kalırlar (yedek olarak).
        
        # 3. BAĞLI TALEBİN DURUMUNU GÜNCELLE
        if teklif.talep:
            teklif.talep.durum = 'onaylandi'
            teklif.talep.onay_tarihi = timezone.now()
            teklif.talep.save()
            
    elif yeni_durum == 'beklemede':
        teklif.durum = 'beklemede'
        teklif.save()
        # Eğer onaydan geri çekildiyse, talebi de işlemde statüsüne çek
        if teklif.talep and teklif.talep.durum == 'onaylandi':
            teklif.talep.durum = 'islemde'
            teklif.talep.save()
            
    elif yeni_durum == 'reddedildi':
        teklif.durum = 'reddedildi'
        teklif.save()

    return redirect('icmal_raporu')

# ========================================================
# 3. MODÜL 2: SATINALMA & FİNANS
# ========================================================

@login_required
def finans_dashboard(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    guncel_kurlar = tcmb_kur_getir()
    kur_usd = float(guncel_kurlar.get('USD', 1))
    kur_eur = float(guncel_kurlar.get('EUR', 1))
    kur_gbp = float(guncel_kurlar.get('GBP', 1))

    def cevir(tl_tutar):
        return {
            'usd': tl_tutar / kur_usd,
            'eur': tl_tutar / kur_eur,
            'gbp': tl_tutar / kur_gbp
        }

    imalat_maliyeti = 0
    harcama_tutari = 0
    genel_toplam = 0
    kalan_borc = 0
    oran = 0
    imalat_labels = []
    imalat_data = []
    gider_labels = []
    gider_data = []
    toplam_kalem_sayisi = 0
    dolu_kalem_sayisi = 0

    imalat_kategorileri = Kategori.objects.prefetch_related('kalemler__teklifler').all()
    gider_kategorileri = GiderKategorisi.objects.prefetch_related('harcamalar').all()
    tedarikciler = Tedarikci.objects.all()

    for kat in imalat_kategorileri:
        kat_toplam = 0
        for kalem in kat.kalemler.all():
            toplam_kalem_sayisi += 1
            tum_teklifler = kalem.teklifler.all()
            maliyet = 0
            onayli = tum_teklifler.filter(durum='onaylandi').first()
            if onayli:
                maliyet = onayli.toplam_fiyat_tl
                dolu_kalem_sayisi += 1
            else:
                bekleyenler = tum_teklifler.filter(durum='beklemede')
                if bekleyenler.exists():
                    maliyet = min(t.toplam_fiyat_tl for t in bekleyenler)
                    dolu_kalem_sayisi += 1
            kat_toplam += maliyet
        if kat_toplam > 0:
            imalat_labels.append(kat.isim)
            imalat_data.append(round(kat_toplam, 2))
            imalat_maliyeti += kat_toplam

    for gider_kat in gider_kategorileri:
        gider_toplam = 0
        for harcama in gider_kat.harcamalar.all():
            gider_toplam += harcama.tl_tutar
        if gider_toplam > 0:
            gider_labels.append(gider_kat.isim)
            gider_data.append(round(gider_toplam, 2))
            harcama_tutari += gider_toplam

    toplam_onaylanan_borc = 0
    toplam_odenen = 0
    for ted in tedarikciler:
        toplam_onaylanan_borc += sum(t.toplam_fiyat_tl for t in ted.teklifler.filter(durum='onaylandi'))
        toplam_odenen += sum(o.tl_tutar for o in ted.odemeler.all())
    
    kalan_borc = toplam_onaylanan_borc - toplam_odenen
    genel_toplam = imalat_maliyeti + harcama_tutari

    if toplam_kalem_sayisi > 0:
        oran = int((dolu_kalem_sayisi / toplam_kalem_sayisi) * 100)

    context = {
        'imalat_maliyeti': imalat_maliyeti,
        'harcama_tutari': harcama_tutari,
        'genel_toplam': genel_toplam,
        'kalan_borc': kalan_borc,
        'oran': oran,
        'doviz_genel': cevir(genel_toplam),
        'doviz_imalat': cevir(imalat_maliyeti),
        'doviz_harcama': cevir(harcama_tutari),
        'doviz_borc': cevir(kalan_borc),
        'imalat_labels': imalat_labels,
        'imalat_data': imalat_data,
        'gider_labels': gider_labels,
        'gider_data': gider_data,
        'toplam_kalem': toplam_kalem_sayisi,
        'dolu_kalem': dolu_kalem_sayisi,
        'kurlar': guncel_kurlar,
    }
    return render(request, 'finans_dashboard.html', context)

@login_required
def finans_ozeti(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    tedarikciler = Tedarikci.objects.all()
    finans_verisi = []
    genel_toplam_borc = 0
    genel_toplam_odenen = 0
    genel_kalan_bakiye = 0

    for ted in tedarikciler:
        onayli_teklifler = ted.teklifler.filter(durum='onaylandi')
        toplam_borc = sum(t.toplam_fiyat_tl for t in onayli_teklifler)
        yapilan_odemeler = ted.odemeler.all()
        toplam_odenen = sum(o.tl_tutar for o in yapilan_odemeler)
        kalan = toplam_borc - toplam_odenen
        
        if toplam_borc > 0 or toplam_odenen > 0:
            finans_verisi.append({
                'id': ted.id,
                'firma': ted.firma_unvani,
                'borc': toplam_borc,
                'odenen': toplam_odenen,
                'bakiye': kalan
            })
            genel_toplam_borc += toplam_borc
            genel_toplam_odenen += toplam_odenen
            genel_kalan_bakiye += kalan

    context = {
        'veriler': finans_verisi,
        'toplam_borc': genel_toplam_borc,
        'toplam_odenen': genel_toplam_odenen,
        'toplam_bakiye': genel_kalan_bakiye,
    }
    return render(request, 'finans_ozeti.html', context)

# ========================================================
# 4. MODÜL 3: DEPO & TALEP
# ========================================================

@login_required
def depo_dashboard(request):
    if not yetki_kontrol(request.user, ['SAHA_EKIBI', 'OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    depo_ozeti = []
    malzemeler = Malzeme.objects.all()
    for mal in malzemeler:
        mevcut_stok = mal.stok
        giren = DepoHareket.objects.filter(malzeme=mal, islem_turu='giris').aggregate(Sum('miktar'))['miktar__sum'] or 0
        cikan = DepoHareket.objects.filter(malzeme=mal, islem_turu='cikis').aggregate(Sum('miktar'))['miktar__sum'] or 0
        
        durum_renk = "success"
        if mevcut_stok <= mal.kritik_stok:
            durum_renk = "danger"
        elif mevcut_stok <= (mal.kritik_stok * 1.5):
            durum_renk = "warning"

        depo_ozeti.append({
            'isim': mal.isim,
            'birim': mal.get_birim_display(),
            'giren': giren,
            'cikan': cikan,
            'stok': mevcut_stok,
            'durum_renk': durum_renk
        })

    son_iadeler = DepoHareket.objects.filter(islem_turu='iade').order_by('-tarih')[:5]
    bekleyen_talepler = MalzemeTalep.objects.filter(durum='bekliyor').order_by('-oncelik', '-tarih')[:10]
    bekleyen_talep_sayisi = MalzemeTalep.objects.filter(durum='bekliyor').count()

    context = {
        'depo_ozeti': depo_ozeti,
        'son_iadeler': son_iadeler,
        'bekleyen_talepler': bekleyen_talepler,
        'bekleyen_talep_sayisi': bekleyen_talep_sayisi
    }
    return render(request, 'depo_dashboard.html', context)

# ========================================================
# 5. MODÜL 4: HAKEDİŞ & ÖDEME
# ========================================================

@login_required
def odeme_dashboard(request):
    if not yetki_kontrol(request.user, ['MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')
    
    bugun = timezone.now().date()
    tum_cekler = Odeme.objects.filter(odeme_turu='cek').order_by('cek_vade_tarihi')
    gecikmisler = tum_cekler.filter(cek_durumu='beklemede', cek_vade_tarihi__lt=bugun)
    yaklasanlar = tum_cekler.filter(cek_durumu='beklemede', cek_vade_tarihi__gte=bugun, cek_vade_tarihi__lte=bugun + timezone.timedelta(days=30))
    toplam_risk = sum(c.tl_tutar for c in tum_cekler.filter(cek_durumu='beklemede'))
    son_hakedisler = Hakedis.objects.all().order_by('-tarih')[:10]
    
    context = {
        'gecikmisler': gecikmisler,
        'yaklasanlar': yaklasanlar,
        'toplam_risk': toplam_risk,
        'son_hakedisler': son_hakedisler,
        'bugun': bugun
    }
    return render(request, 'odeme_dashboard.html', context)

@login_required
def cek_takibi(request):
    if not yetki_kontrol(request.user, ['MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    bugun = timezone.now().date()
    tum_cekler = Odeme.objects.filter(odeme_turu='cek').order_by('cek_vade_tarihi')
    
    gecikmisler = tum_cekler.filter(cek_durumu='beklemede', cek_vade_tarihi__lt=bugun)
    gelecek_30_gun = bugun + timezone.timedelta(days=30)
    yaklasanlar = tum_cekler.filter(cek_durumu='beklemede', cek_vade_tarihi__gte=bugun, cek_vade_tarihi__lte=gelecek_30_gun)
    ileri_tarihliler = tum_cekler.filter(cek_durumu='beklemede', cek_vade_tarihi__gt=gelecek_30_gun)
    odenmisler = tum_cekler.filter(cek_durumu='odendi')
    toplam_risk = sum(c.tl_tutar for c in tum_cekler.filter(cek_durumu='beklemede'))

    context = {
        'gecikmisler': gecikmisler,
        'yaklasanlar': yaklasanlar,
        'ileri_tarihliler': ileri_tarihliler,
        'odenmisler': odenmisler,
        'toplam_risk': toplam_risk,
        'bugun': bugun
    }
    return render(request, 'cek_takibi.html', context)

@login_required
def cek_durum_degistir(request, odeme_id):
    if not yetki_kontrol(request.user, ['MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')
    cek = get_object_or_404(Odeme, id=odeme_id)
    if cek.cek_durumu == 'beklemede':
        cek.cek_durumu = 'odendi'
    else:
        cek.cek_durumu = 'beklemede'
    cek.save()
    return redirect('cek_takibi')

# ========================================================
# 6. DİĞER (YAZDIRMA, DETAY VS.)
# ========================================================

@login_required
def islem_sonuc(request, model_name, pk):
    return render(request, 'islem_sonuc.html', {'model_name': model_name, 'pk': pk})

@login_required
def belge_yazdir(request, model_name, pk):
    belge_data = {}
    baslik = ""
    def hesapla_bakiye(tedarikci):
        if not tedarikci: return 0
        borc = sum(t.toplam_fiyat_tl for t in tedarikci.teklifler.filter(durum='onaylandi'))
        odenen = sum(o.tl_tutar for o in tedarikci.odemeler.all())
        return borc - odenen

    if model_name == 'teklif':
        obj = get_object_or_404(Teklif, pk=pk)
        baslik = "SATIN ALMA / TEKLİF FİŞİ"
        bakiye = hesapla_bakiye(obj.tedarikci)
        if obj.is_kalemi: is_adi = obj.is_kalemi.isim
        elif obj.malzeme: is_adi = obj.malzeme.isim
        else: is_adi = "Belirtilmemiş"

        belge_data = {
            'İşlem No': f"TK-{obj.id}",
            'Tarih': timezone.now(), 
            'Firma': obj.tedarikci.firma_unvani,
            'İş Kalemi / Malzeme': is_adi,
            'Miktar': f"{obj.miktar}",
            'Birim Fiyat (KDV Hariç)': f"{obj.birim_fiyat:,.2f} {obj.para_birimi}",
            'KDV Oranı': f"%{obj.kdv_orani}",
            'Birim Fiyat (KDV Dahil)': f"{obj.birim_fiyat_kdvli:,.2f} {obj.para_birimi}",
            'Kur': f"{obj.kur_degeri}",
            'Toplam Maliyet (TL)': f"{obj.toplam_fiyat_tl:,.2f} TL",
            'Durum': obj.get_durum_display(),
            '------------------': '------------------', 
            'Güncel Firma Bakiyesi': f"{bakiye:,.2f} TL"
        }
    elif model_name == 'odeme':
        obj = get_object_or_404(Odeme, pk=pk)
        baslik = "TEDARİKÇİ ÖDEME MAKBUZU"
        detay = f"({obj.get_odeme_turu_display()})"
        if obj.odeme_turu == 'cek': detay += f" - Vade: {obj.cek_vade_tarihi}"
        bakiye = hesapla_bakiye(obj.tedarikci)
        ilgili_is = "Genel / Mahsuben (Cari Hesaba)"
        if obj.ilgili_teklif:
            if obj.ilgili_teklif.is_kalemi: ad = obj.ilgili_teklif.is_kalemi.isim
            elif obj.ilgili_teklif.malzeme: ad = obj.ilgili_teklif.malzeme.isim
            else: ad = "Teklif #" + str(obj.ilgili_teklif.id)
            ilgili_is = f"{ad} (Hakediş Ödemesi)"
            
        belge_data = {
            'İşlem No': f"OD-{obj.id}",
            'İşlem Tarihi': obj.tarih,
            'Yazdırılma Zamanı': timezone.now(),
            'Kime Ödendi': obj.tedarikci.firma_unvani,
            'İlgili İş / Hakediş': ilgili_is,
            'Ödeme Tutarı': f"{obj.tutar:,.2f} {obj.para_birimi}",
            'İşlem Kuru': obj.kur_degeri,
            'TL Karşılığı': f"{obj.tl_tutar:,.2f} TL",
            'Ödeme Yöntemi': detay,
            'Açıklama': obj.aciklama,
            '------------------': '------------------',
            'Kalan Borç Bakiyesi': f"{bakiye:,.2f} TL"
        }
    elif model_name == 'harcama':
        obj = get_object_or_404(Harcama, pk=pk)
        baslik = "GİDER / HARCAMA FİŞİ"
        belge_data = {
            'İşlem No': f"HR-{obj.id}",
            'Tarih': obj.tarih,
            'Kategori': obj.kategori.isim,
            'Açıklama': obj.aciklama,
            'Tutar': f"{obj.tutar:,.2f} {obj.para_birimi}",
        }
    elif model_name == 'malzemetalep':
        obj = get_object_or_404(MalzemeTalep, pk=pk)
        baslik = "MALZEME TALEP VE TAKİP FORMU"
        talep_zamani = obj.tarih.strftime('%d.%m.%Y %H:%M')
        onay_zamani = obj.onay_tarihi.strftime('%d.%m.%Y %H:%M') if obj.onay_tarihi else "- (Bekliyor)"
        temin_zamani = obj.temin_tarihi.strftime('%d.%m.%Y %H:%M') if obj.temin_tarihi else "- (Bekliyor)"
        talep_eden_bilgi = f"{obj.talep_eden.first_name} {obj.talep_eden.last_name} ({obj.talep_eden.username})" if obj.talep_eden else "Bilinmiyor"

        belge_data = {
            'Talep No': f"TLP-{obj.id:04d}",
            'Talep Oluşturulma': talep_zamani,
            'Talep Eden': talep_eden_bilgi,
            '------------------': '------------------',
            'İstenen Malzeme': obj.malzeme.isim,
            'Miktar': f"{obj.miktar} {obj.malzeme.get_birim_display()}",
            'Kullanılacak Yer': obj.proje_yeri,
            'Aciliyet Durumu': obj.get_oncelik_display(),
            'Açıklama / Not': obj.aciklama,
            '-------------------': '------------------',
            'DURUM': obj.get_durum_display(),
            '🕒 Onaylanma Zamanı': onay_zamani,
            '🚚 Temin/Teslim Zamanı': temin_zamani,
        }

    context = {'baslik': baslik, 'data': belge_data, 'tarih_saat': timezone.now()}
    return render(request, 'belge_yazdir.html', context)

@login_required
def tedarikci_ekstresi(request, tedarikci_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    tedarikci = get_object_or_404(Tedarikci, id=tedarikci_id)
    hareketler = []
    
    onayli_teklifler = tedarikci.teklifler.filter(durum='onaylandi')
    for t in onayli_teklifler:
        miktar = t.miktar 
        if t.is_kalemi:
            isim = t.is_kalemi.isim
            birim_yazisi = t.is_kalemi.get_birim_display()
        elif t.malzeme:
            isim = t.malzeme.isim
            birim_yazisi = t.malzeme.get_birim_display()
        else:
            isim = "Bilinmeyen Kalem"
            birim_yazisi = "-"

        ham_tutar_doviz = float(t.birim_fiyat) * float(miktar)
        kdvli_tutar_doviz = ham_tutar_doviz * (1 + (t.kdv_orani / 100))
        
        hareketler.append({
            'tarih': t.olusturulma_tarihi.date(), 
            'tur': 'BORÇ (Mal/Hizmet Alımı)',
            'aciklama': f"{isim} ({miktar:.0f} {birim_yazisi})",
            'borc': t.toplam_fiyat_tl,
            'alacak': 0,
            'para_birimi': t.para_birimi, 
            'doviz_tutari': kdvli_tutar_doviz
        })
        
    odemeler = tedarikci.odemeler.all()
    for o in odemeler:
        ek_bilgi = ""
        if o.odeme_turu == 'cek' and o.cek_vade_tarihi:
            ek_bilgi = f" (Vade: {o.cek_vade_tarihi.strftime('%d.%m.%Y')})"
            
        hareketler.append({
            'tarih': o.tarih,
            'tur': f'ÖDEME ({o.get_odeme_turu_display()})',
            'aciklama': o.aciklama + ek_bilgi,
            'borc': 0,
            'alacak': o.tl_tutar,
            'para_birimi': o.para_birimi,
            'doviz_tutari': o.tutar
        })
    
    hareketler.sort(key=lambda x: x['tarih'] if x['tarih'] else timezone.now().date())

    bakiye = 0
    toplam_borc = 0
    toplam_alacak = 0
    for h in hareketler:
        bakiye += (h['borc'] - h['alacak'])
        h['bakiye'] = bakiye
        toplam_borc += h['borc']
        toplam_alacak += h['alacak']

    context = {
        'tedarikci': tedarikci,
        'hareketler': hareketler,
        'toplam_borc': toplam_borc,
        'toplam_alacak': toplam_alacak,
        'son_bakiye': bakiye,
        'now': timezone.now()
    }
    return render(request, 'tedarikci_ekstre.html', context)

@login_required
def talep_onayla(request, talep_id):
    """
    Bekleyen bir talebi onaylar ve 'İşlemde' (Teklif Toplama) aşamasına geçirir.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    
    if talep.durum == 'bekliyor':
        talep.durum = 'islemde'
        talep.onay_tarihi = timezone.now()
        talep.save()
        
        # --- HATA DÜZELTME: İSİM KONTROLÜ ---
        talep_adi = talep.malzeme.isim if talep.malzeme else talep.is_kalemi.isim
        # ------------------------------------

        messages.success(request, f"✅ Talep onaylandı: {talep_adi} için teklif süreci başladı.")
    
    return redirect('icmal_raporu')

@login_required
def talep_tamamla(request, talep_id):
    """
    Onaylanmış (Yeşil) talebi arşivler.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    
    # --- HATA DÜZELTME: İSİM KONTROLÜ ---
    talep_adi = talep.malzeme.isim if talep.malzeme else talep.is_kalemi.isim
    # ------------------------------------

    if talep.durum == 'onaylandi':
        talep.durum = 'tamamlandi'
        talep.save()
        messages.success(request, f"📦 {talep_adi} talebi arşivlendi ve listeden kaldırıldı.")
    
    return redirect('icmal_raporu')

@login_required
def talep_sil(request, talep_id):
    """
    Talebi siler.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        messages.error(request, "Silme yetkiniz yok!")
        return redirect('icmal_raporu')

    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    
    # --- HATA DÜZELTME: İSİM KONTROLÜ ---
    talep_adi = talep.malzeme.isim if talep.malzeme else talep.is_kalemi.isim
    # ------------------------------------
    
    talep.delete()
    messages.warning(request, f"🗑️ {talep_adi} talebi silindi.")
    
    return redirect('icmal_raporu')

@login_required
def arsiv_raporu(request):
    """
    Sadece 'tamamlandi' durumundaki (arşivlenmiş) talepleri listeler.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    # Sadece BİTEN işleri çekiyoruz
    arsiv_talepler = MalzemeTalep.objects.filter(
        durum='tamamlandi'
    ).select_related('malzeme', 'talep_eden').prefetch_related('teklifler__tedarikci').order_by('-temin_tarihi', '-tarih')

    context = {
        'aktif_talepler': arsiv_talepler, # Aynı şablonu kullanmak için değişken adını aynı tuttum
        'arsiv_modu': True # Şablona "Şu an arşivdeyiz" bilgisini gönderiyoruz
    }
    return render(request, 'icmal.html', context)

@login_required
def talep_arsivden_cikar(request, talep_id):
    """
    Arşivlenmiş bir talebi tekrar 'Onaylandı' statüsüne (Aktif Listeye) çeker.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')
        
    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    if talep.durum == 'tamamlandi':
        talep.durum = 'onaylandi'
        talep.save()
        messages.success(request, f"♻️ {talep.malzeme.isim} arşivden çıkarıldı ve aktif listeye geri döndü.")
        
    return redirect('arsiv_raporu')

@login_required
def stok_listesi(request):
    """
    Tüm malzemelerin listelendiği, kritik stok durumlarının görüldüğü ana ekran.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')

    # Arama motoru
    search_query = request.GET.get('search', '')
    
    if search_query:
        malzemeler = Malzeme.objects.filter(isim__icontains=search_query)
    else:
        malzemeler = Malzeme.objects.all()

    # Stok durumlarını analiz edelim (Uyarı kartları için)
    kritik_sayisi = 0
    toplam_cesit = malzemeler.count()
    
    # Not: Stok hesabı property olduğu için veritabanında filter yapamıyoruz, döngüde bakacağız.
    # Ancak liste çok uzun değilse bu sorun olmaz.
    for malz in malzemeler:
        if malz.stok <= malz.kritik_stok:
            malz.kritik_durum = True # HTML'de kullanmak için geçici işaret
            kritik_sayisi += 1
        else:
            malz.kritik_durum = False

    context = {
        'malzemeler': malzemeler,
        'search_query': search_query,
        'toplam_cesit': toplam_cesit,
        'kritik_sayisi': kritik_sayisi,
    }
    return render(request, 'stok_listesi.html', context)

def cikis_yap(request):
    logout(request)
    return redirect('/admin/login/')