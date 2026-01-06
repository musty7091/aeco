from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.db.models import Sum
from django.contrib.auth.decorators import login_required # Güvenlik için
from .models import Kategori, GiderKategorisi, Teklif, Odeme, Harcama, Tedarikci
from .utils import tcmb_kur_getir
from django.contrib.auth import logout  # <-- BU SATIRI EKLEYİN

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
        
        belge_data = {
            'İşlem No': f"TK-{obj.id}",
            'Tarih': timezone.now(), 
            'Firma': obj.tedarikci.firma_unvani,
            'İş Kalemi': obj.is_kalemi.isim,
            'Birim Fiyat': f"{obj.birim_fiyat:,.2f} {obj.para_birimi}",
            'Kur': f"{obj.kur_degeri}",
            'KDV Oranı': f"%{obj.kdv_orani}",
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
            ilgili_is = f"{obj.ilgili_teklif.is_kalemi.isim} (Hakediş Ödemesi)"
            
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

    context = {
        'baslik': baslik,
        'data': belge_data,
        'tarih_saat': timezone.now()
    }
    return render(request, 'belge_yazdir.html', context)


# ========================================================
# 2. OPERASYONEL FONKSİYONLAR (Dashboard, İcmal vb.)
# ========================================================

@login_required
def teklif_durum_guncelle(request, teklif_id, yeni_durum):
    """
    İcmal ekranında Onayla/Reddet butonları için.
    """
    teklif = get_object_or_404(Teklif, id=teklif_id)
    
    if yeni_durum in ['onaylandi', 'reddedildi', 'beklemede']:
        if yeni_durum == 'onaylandi':
            # Aynı iş kalemindeki diğer teklifleri beklemede yap (Sadece biri onaylanabilir)
            Teklif.objects.filter(is_kalemi=teklif.is_kalemi).update(durum='beklemede')
        
        teklif.durum = yeni_durum
        teklif.save()
        
    return redirect('icmal_raporu')

@login_required
def dashboard(request):
    """
    Ana Yönetici Paneli (Grafikler ve Özet Kartlar)
    """
    guncel_kurlar = tcmb_kur_getir()
    kur_usd = float(guncel_kurlar.get('USD', 1))
    kur_eur = float(guncel_kurlar.get('EUR', 1))
    kur_gbp = float(guncel_kurlar.get('GBP', 1))

    imalat_kategorileri = Kategori.objects.prefetch_related('kalemler__teklifler').all()
    gider_kategorileri = GiderKategorisi.objects.prefetch_related('harcamalar').all()
    tedarikciler = Tedarikci.objects.all()
    
    toplam_proje_maliyeti = 0   
    toplam_harcama_tutari = 0    
    toplam_kalem_sayisi = 0
    dolu_kalem_sayisi = 0 
    
    imalat_etiketleri = []
    imalat_verileri = []
    gider_etiketleri = []
    gider_verileri = []

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
            imalat_etiketleri.append(kat.isim)
            imalat_verileri.append(round(kat_toplam, 2))
            toplam_proje_maliyeti += kat_toplam

    # Gider Hesabı
    for gider_kat in gider_kategorileri:
        gider_toplam = 0
        for harcama in gider_kat.harcamalar.all():
            gider_toplam += harcama.tl_tutar
        if gider_toplam > 0:
            gider_etiketleri.append(gider_kat.isim)
            gider_verileri.append(round(gider_toplam, 2))
            toplam_harcama_tutari += gider_toplam

    # Borç Hesabı
    toplam_onaylanan_borc = 0
    toplam_odenen = 0
    for ted in tedarikciler:
        toplam_onaylanan_borc += sum(t.toplam_fiyat_tl for t in ted.teklifler.filter(durum='onaylandi'))
        toplam_odenen += sum(o.tl_tutar for o in ted.odemeler.all())
    
    piyasaya_kalan_borc = toplam_onaylanan_borc - toplam_odenen
    genel_toplam = toplam_proje_maliyeti + toplam_harcama_tutari

    # Döviz Çevirici
    def cevir(tl_tutar):
        return {
            'usd': tl_tutar / kur_usd,
            'eur': tl_tutar / kur_eur,
            'gbp': tl_tutar / kur_gbp
        }

    oran = 0
    if toplam_kalem_sayisi > 0:
        oran = int((dolu_kalem_sayisi / toplam_kalem_sayisi) * 100)

    context = {
        'imalat_maliyeti': toplam_proje_maliyeti,
        'harcama_tutari': toplam_harcama_tutari,
        'genel_toplam': genel_toplam,
        'kalan_borc': piyasaya_kalan_borc,
        'oran': oran,
        'doviz_genel': cevir(genel_toplam),
        'doviz_imalat': cevir(toplam_proje_maliyeti),
        'doviz_harcama': cevir(toplam_harcama_tutari),
        'doviz_borc': cevir(piyasaya_kalan_borc),
        'imalat_labels': imalat_etiketleri,
        'imalat_data': imalat_verileri,
        'gider_labels': gider_etiketleri,
        'gider_data': gider_verileri,
        'toplam_kalem': toplam_kalem_sayisi,
        'dolu_kalem': dolu_kalem_sayisi,
        'kurlar': guncel_kurlar
    }
    return render(request, 'dashboard.html', context)

@login_required
def icmal_raporu(request):
    """
    İcmal Listesi Görüntüleme
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
    Tedarikçi Hesap Hareketleri (Ekstre)
    """
    tedarikci = get_object_or_404(Tedarikci, id=tedarikci_id)
    hareketler = []
    
    # A. BORÇLAR (Teklifler)
    # GÜNCELLEME: Orijinal Döviz Tutarını Hesapla ve Listeye Ekle
    onayli_teklifler = tedarikci.teklifler.filter(durum='onaylandi')
    for t in onayli_teklifler:
        # 1. Toplam Döviz Tutarını bul (Birim Fiyat * Miktar * KDV)
        miktar = t.is_kalemi.hedef_miktar
        ham_tutar_doviz = float(t.birim_fiyat) * float(miktar)
        kdvli_tutar_doviz = ham_tutar_doviz * (1 + (t.kdv_orani / 100))
        
        birim_yazisi = t.is_kalemi.get_birim_display()
        
        hareketler.append({
            'tarih': t.olusturulma_tarihi.date(), 
            'tur': 'BORÇ (Mal/Hizmet Alımı)',
            'aciklama': f"{t.is_kalemi.isim} ({miktar:.0f} {birim_yazisi})",
            'borc': t.toplam_fiyat_tl, # TL Karşılığı
            'alacak': 0,
            'para_birimi': t.para_birimi, 
            'doviz_tutari': kdvli_tutar_doviz # Orijinal Para Tutarı
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
            'alacak': o.tl_tutar, # TL Karşılığı
            'para_birimi': o.para_birimi,
            'doviz_tutari': o.tutar # Orijinal Para Tutarı
        })
    
    # Sıralama
    hareketler.sort(key=lambda x: x['tarih'] if x['tarih'] else timezone.now().date())

    # Bakiye Hesabı
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


# ========================================================
# 3. ÇEK TAKİP MODÜLÜ
# ========================================================

@login_required
def cek_takibi(request):
    """
    Çek Takip Ekranı: Vadesi gelen/geçen çekleri listeler.
    """
    bugun = timezone.now().date()
    tum_cekler = Odeme.objects.filter(odeme_turu='cek').order_by('cek_vade_tarihi')
    
    # 1. Vadesi Geçmiş (Riskli)
    gecikmisler = tum_cekler.filter(cek_durumu='beklemede', cek_vade_tarihi__lt=bugun)
    
    # 2. Yaklaşanlar (30 Gün)
    gelecek_30_gun = bugun + timezone.timedelta(days=30)
    yaklasanlar = tum_cekler.filter(
        cek_durumu='beklemede', 
        cek_vade_tarihi__gte=bugun, 
        cek_vade_tarihi__lte=gelecek_30_gun
    )
    
    # 3. İleri Tarihliler
    ileri_tarihliler = tum_cekler.filter(
        cek_durumu='beklemede', 
        cek_vade_tarihi__gt=gelecek_30_gun
    )
    
    # 4. Ödenmişler
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
    """
    Çeki Ödendi/Beklemede olarak değiştirir.
    """
    cek = get_object_or_404(Odeme, id=odeme_id)
    
    if cek.cek_durumu == 'beklemede':
        cek.cek_durumu = 'odendi'
    else:
        cek.cek_durumu = 'beklemede'
        
    cek.save()
    return redirect('cek_takibi')

def cikis_yap(request):
    """
    Güvenli çıkış işlemi
    """
    logout(request)
    return redirect('/admin/login/')