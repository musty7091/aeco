from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.db.models import Sum
from django.contrib.auth.decorators import login_required 
from .models import (
    Kategori, GiderKategorisi, Teklif, Odeme, Harcama, 
    Tedarikci, Malzeme, DepoHareket, Hakedis, MalzemeTalep
)
from .utils import tcmb_kur_getir
from django.contrib.auth import logout

# ========================================================
# 1. YAZDIRMA VE ARA İŞLEM EKRANLARI
# ========================================================

@login_required
def islem_sonuc(request, model_name, pk):
    """
    Kaydetme işleminden sonra kullanıcıya 'Yazdırayım mı?' diye soran ara ekran.
    """
    context = {
        'model_name': model_name,
        'pk': pk
    }
    return render(request, 'islem_sonuc.html', context)

@login_required
def belge_yazdir(request, model_name, pk):
    """
    Resmi dökümü oluşturan ve yazıcı penceresini açan ekran.
    """
    belge_data = {}
    baslik = ""
    
    # Yardımcı Fonksiyon: Bakiye Hesapla
    def hesapla_bakiye(tedarikci):
        if not tedarikci: return 0
        borc = sum(t.toplam_fiyat_tl for t in tedarikci.teklifler.filter(durum='onaylandi'))
        odenen = sum(o.tl_tutar for o in tedarikci.odemeler.all())
        return borc - odenen

    if model_name == 'teklif':
        obj = get_object_or_404(Teklif, pk=pk)
        baslik = "SATIN ALMA / TEKLİF FİŞİ"
        bakiye = hesapla_bakiye(obj.tedarikci)
        
        # İsim Belirleme (Hibrit Yapı)
        if obj.is_kalemi:
            is_adi = obj.is_kalemi.isim
        elif obj.malzeme:
            is_adi = obj.malzeme.isim
        else:
            is_adi = "Belirtilmemiş"

        belge_data = {
            'İşlem No': f"TK-{obj.id}",
            'Tarih': timezone.now(), 
            'Firma': obj.tedarikci.firma_unvani,
            'İş Kalemi / Malzeme': is_adi,
            'Miktar': f"{obj.miktar}",
            
            # --- GÜNCELLEME BURADA ---
            'Birim Fiyat (KDV Hariç)': f"{obj.birim_fiyat:,.2f} {obj.para_birimi}",
            'KDV Oranı': f"%{obj.kdv_orani}",
            'Birim Fiyat (KDV Dahil)': f"{obj.birim_fiyat_kdvli:,.2f} {obj.para_birimi}", # Yeni Eklenen Satır
            # -------------------------
            
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
        if obj.odeme_turu == 'cek':
            detay += f" - Vade: {obj.cek_vade_tarihi}"
        bakiye = hesapla_bakiye(obj.tedarikci)
        ilgili_is = "Genel / Mahsuben (Cari Hesaba)"
        if obj.ilgili_teklif:
            if obj.ilgili_teklif.is_kalemi:
                ad = obj.ilgili_teklif.is_kalemi.isim
            elif obj.ilgili_teklif.malzeme:
                ad = obj.ilgili_teklif.malzeme.isim
            else:
                ad = "Teklif #" + str(obj.ilgili_teklif.id)
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
        
        talep_eden_bilgi = "Bilinmiyor"
        if obj.talep_eden:
            talep_eden_bilgi = f"{obj.talep_eden.first_name} {obj.talep_eden.last_name} ({obj.talep_eden.username})"

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

    context = {
        'baslik': baslik,
        'data': belge_data,
        'tarih_saat': timezone.now()
    }
    return render(request, 'belge_yazdir.html', context)


# ========================================================
# 2. OPERASYONEL FONKSİYONLAR
# ========================================================

@login_required
def teklif_durum_guncelle(request, teklif_id, yeni_durum):
    """
    İcmal ekranında Onayla/Reddet butonları için.
    """
    teklif = get_object_or_404(Teklif, id=teklif_id)
    if yeni_durum in ['onaylandi', 'reddedildi', 'beklemede']:
        # Eğer bu bir İş Kalemi ise diğerlerini reddet, Malzeme ise reddetme (Malzeme çoklu alınabilir)
        if yeni_durum == 'onaylandi' and teklif.is_kalemi:
            Teklif.objects.filter(is_kalemi=teklif.is_kalemi).update(durum='beklemede')
        
        teklif.durum = yeni_durum
        teklif.save()
    return redirect('icmal_raporu')

@login_required
def dashboard(request):
    """
    Ana Yönetici Paneli
    """
    # Yetki
    kullanici_gruplari = request.user.groups.values_list('name', flat=True)
    is_yonetici = request.user.is_superuser or request.user.is_staff
    gorsun_finans = is_yonetici or 'MUHASEBE_FINANS' in kullanici_gruplari or 'OFIS_VE_SATINALMA' in kullanici_gruplari
    gorsun_santiye = is_yonetici or 'SAHA_EKIBI' in kullanici_gruplari or 'OFIS_VE_SATINALMA' in kullanici_gruplari

    # Kurlar
    guncel_kurlar = tcmb_kur_getir()
    kur_usd = float(guncel_kurlar.get('USD', 1))
    kur_eur = float(guncel_kurlar.get('EUR', 1))
    kur_gbp = float(guncel_kurlar.get('GBP', 1))

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
    
    if gorsun_finans:
        imalat_kategorileri = Kategori.objects.prefetch_related('kalemler__teklifler').all()
        gider_kategorileri = GiderKategorisi.objects.prefetch_related('harcamalar').all()
        tedarikciler = Tedarikci.objects.all()

        # İmalat Hesabı
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

        # Gider Hesabı
        for gider_kat in gider_kategorileri:
            gider_toplam = 0
            for harcama in gider_kat.harcamalar.all():
                gider_toplam += harcama.tl_tutar
            if gider_toplam > 0:
                gider_labels.append(gider_kat.isim)
                gider_data.append(round(gider_toplam, 2))
                harcama_tutari += gider_toplam

        # Borç Hesabı
        toplam_onaylanan_borc = 0
        toplam_odenen = 0
        for ted in tedarikciler:
            toplam_onaylanan_borc += sum(t.toplam_fiyat_tl for t in ted.teklifler.filter(durum='onaylandi'))
            toplam_odenen += sum(o.tl_tutar for o in ted.odemeler.all())
        
        kalan_borc = toplam_onaylanan_borc - toplam_odenen
        genel_toplam = imalat_maliyeti + harcama_tutari

        if toplam_kalem_sayisi > 0:
            oran = int((dolu_kalem_sayisi / toplam_kalem_sayisi) * 100)

    def cevir(tl_tutar):
        return {
            'usd': tl_tutar / kur_usd,
            'eur': tl_tutar / kur_eur,
            'gbp': tl_tutar / kur_gbp
        }

    # Şantiye Verileri
    depo_ozeti = []
    son_iadeler = []
    bekleyen_talepler = []
    bekleyen_talep_sayisi = 0

    if gorsun_santiye:
        malzemeler = Malzeme.objects.all()
        for mal in malzemeler:
            # Modeldeki 'stok' property'sini kullanıyoruz (models.py'de tanımlı)
            mevcut_stok = mal.stok
            
            # Ek bilgi için yine de giriş/çıkış toplamlarını çekebiliriz
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
        'gorsun_finans': gorsun_finans,
        'gorsun_santiye': gorsun_santiye,
        'is_yonetici': is_yonetici,
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
        'depo_ozeti': depo_ozeti,
        'son_iadeler': son_iadeler,
        'bekleyen_talepler': bekleyen_talepler,
        'bekleyen_talep_sayisi': bekleyen_talep_sayisi
    }
    return render(request, 'dashboard.html', context)

@login_required
def icmal_raporu(request):
    """
    İcmal Listesi (Hibrit yapıya uygun olması için güncellenebilir ama şimdilik kategori bazlı çalışıyor)
    """
    kategoriler = Kategori.objects.prefetch_related('kalemler__teklifler__tedarikci').all()
    for kat in kategoriler:
        for kalem in kat.kalemler.all():
            teklifler = kalem.teklifler.all()
            kalem.referans_fiyat = 0
            kalem.durum_rengi = "secondary"
            if teklifler:
                onayli = teklifler.filter(durum='onaylandi').first()
                if onayli:
                    kalem.referans_fiyat = onayli.toplam_fiyat_tl
                    kalem.durum_rengi = "success"
                else:
                    bekleyenler = teklifler.filter(durum='beklemede')
                    if bekleyenler.exists():
                        kalem.referans_fiyat = min(t.toplam_fiyat_tl for t in bekleyenler)
                        kalem.durum_rengi = "warning"
                    else:
                        kalem.durum_rengi = "danger"
    return render(request, 'icmal.html', {'kategoriler': kategoriler})

@login_required
def finans_ozeti(request):
    """
    Tedarikçi bazlı borç/alacak tablosu
    """
    if not request.user.is_superuser and not request.user.groups.filter(name__in=['MUHASEBE_FINANS', 'OFIS_VE_SATINALMA']).exists():
        return redirect('dashboard')

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

@login_required
def tedarikci_ekstresi(request, tedarikci_id):
    """
    Tedarikçi Hesap Hareketleri (Ekstre) - HİBRİT YAPIYA GÖRE GÜNCELLENDİ
    """
    tedarikci = get_object_or_404(Tedarikci, id=tedarikci_id)
    hareketler = []
    
    # A. BORÇLAR (Teklifler)
    onayli_teklifler = tedarikci.teklifler.filter(durum='onaylandi')
    for t in onayli_teklifler:
        # --- MİKTAR ve İSİM BELİRLEME (HATA ÇÖZÜMÜ) ---
        miktar = t.miktar # Artık miktar teklif modelinde
        
        if t.is_kalemi:
            isim = t.is_kalemi.isim
            birim_yazisi = t.is_kalemi.get_birim_display()
        elif t.malzeme:
            isim = t.malzeme.isim
            birim_yazisi = t.malzeme.get_birim_display()
        else:
            isim = "Bilinmeyen Kalem"
            birim_yazisi = "-"
        # ---------------------------------------------

        # Orijinal Döviz Tutarını Hesapla
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
        
    # B. ÖDEMELER
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
def cek_takibi(request):
    """
    Çek Takip Ekranı
    """
    if not request.user.is_superuser and not request.user.groups.filter(name__in=['MUHASEBE_FINANS', 'OFIS_VE_SATINALMA']).exists():
        return redirect('dashboard')

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
    cek = get_object_or_404(Odeme, id=odeme_id)
    if cek.cek_durumu == 'beklemede':
        cek.cek_durumu = 'odendi'
    else:
        cek.cek_durumu = 'beklemede'
    cek.save()
    return redirect('cek_takibi')

def cikis_yap(request):
    logout(request)
    return redirect('/admin/login/')