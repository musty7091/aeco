import json
from django.contrib.auth import logout
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.db.models import Sum, Case, When, F, DecimalField, Q
from django.contrib.auth.decorators import login_required 
from django.contrib import messages
from django.http import JsonResponse
from django.http import HttpResponse
from .models import (
    Kategori, IsKalemi, Tedarikci, Depo, Malzeme, 
    MalzemeTalep, Teklif, SatinAlma, DepoHareket,
    Odeme, Harcama, GiderKategorisi, Hakedis
)
from .models import Fatura
from .forms import FaturaGirisForm
from .forms import DepoTransferForm
from .utils import tcmb_kur_getir
from .forms import TeklifForm, TedarikciForm, MalzemeForm, TalepForm, IsKalemiForm

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
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    talepler_query = MalzemeTalep.objects.filter(
        durum__in=['bekliyor', 'islemde', 'onaylandi']
    ).select_related(
        'malzeme', 'is_kalemi', 'talep_eden'
    ).prefetch_related(
        'teklifler', 'teklifler__tedarikci'
    ).order_by('-oncelik', '-tarih')

    aktif_talepler = list(talepler_query)

    for talep in aktif_talepler:
        teklifler = talep.teklifler.all()
        if teklifler:
            try:
                en_uygun = min(teklifler, key=lambda t: t.toplam_fiyat_tl)
                talep.en_uygun_teklif_id = en_uygun.id
            except ValueError:
                pass

    context = {'aktif_talepler': aktif_talepler}
    return render(request, 'icmal.html', context)

@login_required
def talep_olustur(request):
    if request.method == 'POST':
        form = TalepForm(request.POST)
        if form.is_valid():
            talep = form.save(commit=False)
            talep.talep_eden = request.user 
            talep.durum = 'bekliyor' 
            talep.save()
            
            if talep.malzeme:
                talep_adi = talep.malzeme.isim
            elif talep.is_kalemi:
                talep_adi = talep.is_kalemi.isim
            else:
                talep_adi = "Yeni Talep"
            
            messages.success(request, f"✅ {talep_adi} talebiniz oluşturuldu ve satınalma ekranına düştü.")
            return redirect('icmal_raporu') 
        else:
            messages.error(request, "Lütfen alanları kontrol ediniz.")
    else:
        form = TalepForm()

    return render(request, 'talep_olustur.html', {'form': form})

@login_required
def teklif_ekle(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    talep_id = request.GET.get('talep_id')
    secili_talep = None
    initial_data = {}

    if talep_id:
        secili_talep = get_object_or_404(MalzemeTalep, id=talep_id)
        initial_data['miktar'] = secili_talep.miktar
        
        if secili_talep.malzeme:
            initial_data['malzeme'] = secili_talep.malzeme
            initial_data['kdv_orani_secimi'] = secili_talep.malzeme.kdv_orani
            
        if secili_talep.is_kalemi:
            initial_data['is_kalemi'] = secili_talep.is_kalemi
            initial_data['kdv_orani_secimi'] = secili_talep.is_kalemi.kdv_orani

    guncel_kurlar = tcmb_kur_getir()
    kurlar_dict = {k: float(v) for k, v in guncel_kurlar.items()}
    kurlar_dict['TRY'] = 1.0
    kurlar_json = json.dumps(kurlar_dict)

    malzeme_kdv_map = {m.id: m.kdv_orani for m in Malzeme.objects.all()}
    malzeme_kdv_json = json.dumps(malzeme_kdv_map)

    hizmet_kdv_map = {h.id: h.kdv_orani for h in IsKalemi.objects.all()}
    hizmet_kdv_json = json.dumps(hizmet_kdv_map)

    if request.method == 'POST':
        form = TeklifForm(request.POST, request.FILES)
        if form.is_valid():
            teklif = form.save(commit=False)
            
            if talep_id:
                talep_obj = get_object_or_404(MalzemeTalep, id=talep_id)
                teklif.talep = talep_obj 
                
                if talep_obj.malzeme: teklif.malzeme = talep_obj.malzeme
                if talep_obj.is_kalemi: teklif.is_kalemi = talep_obj.is_kalemi

            oran = int(form.cleaned_data['kdv_orani_secimi'])
            teklif.kdv_orani = float(oran)
            
            secilen_para = teklif.para_birimi
            teklif.kur_degeri = guncel_kurlar.get(secilen_para, 1.0)
            
            teklif.save()
            messages.success(request, f"✅ Teklif başarıyla kaydedildi.")
            return redirect('icmal_raporu')
        else:
            messages.error(request, "Lütfen formdaki hataları düzeltiniz.")
    else:
        form = TeklifForm(initial=initial_data)

    context = {
        'form': form,
        'kurlar_json': kurlar_json,
        'guncel_kurlar': guncel_kurlar,
        'secili_talep': secili_talep,
        'malzeme_kdv_json': malzeme_kdv_json,
        'hizmet_kdv_json': hizmet_kdv_json,
    }
    return render(request, 'teklif_ekle.html', context)

@login_required
def tedarikci_ekle(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    if request.method == 'POST':
        form = TedarikciForm(request.POST)
        if form.is_valid():
            ted = form.save()
            messages.success(request, f"✅ {ted.firma_unvani} başarıyla eklendi.")
            return redirect('tedarikci_ekle') 
    else:
        form = TedarikciForm()

    return render(request, 'tedarikci_ekle.html', {'form': form})

@login_required
def malzeme_ekle(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')

    if request.method == 'POST':
        form = MalzemeForm(request.POST)
        if form.is_valid():
            malzeme = form.save()
            messages.success(request, f"✅ {malzeme.isim} başarıyla stok kartlarına eklendi.")
            return redirect('stok_listesi') 
        else:
            messages.error(request, "Lütfen formdaki hataları düzeltiniz.")
    else:
        form = MalzemeForm()

    return render(request, 'malzeme_ekle.html', {'form': form})

@login_required
def teklif_durum_guncelle(request, teklif_id, yeni_durum):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    teklif = get_object_or_404(Teklif, id=teklif_id)
    eski_durum = teklif.durum
    teklif.durum = yeni_durum
    teklif.save()
    
    if yeni_durum == 'onaylandi' and eski_durum != 'onaylandi':
        if teklif.talep:
            teklif.talep.durum = 'onaylandi'
            teklif.talep.save()
        
        SatinAlma.objects.get_or_create(
            teklif=teklif,
            defaults={
                'toplam_miktar': teklif.miktar,
                'teslim_edilen': 0,
                'siparis_tarihi': timezone.now()
            }
        )
    
    messages.success(request, f"Teklif durumu '{yeni_durum}' olarak güncellendi.")
    
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
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
        tedarikci_faturalari = Fatura.objects.filter(satinalma__teklif__tedarikci=ted)
        toplam_borc = sum(f.tutar for f in tedarikci_faturalari)

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
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    
    if talep.durum == 'bekliyor':
        talep.durum = 'islemde'
        talep.onay_tarihi = timezone.now()
        talep.save()
        
        talep_adi = talep.malzeme.isim if talep.malzeme else talep.is_kalemi.isim

        messages.success(request, f"✅ Talep onaylandı: {talep_adi} için teklif süreci başladı.")
    
    return redirect('icmal_raporu')

@login_required
def talep_tamamla(request, talep_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    talep_adi = talep.malzeme.isim if talep.malzeme else talep.is_kalemi.isim

    if talep.durum == 'onaylandi':
        talep.durum = 'tamamlandi'
        talep.save()
        messages.success(request, f"📦 {talep_adi} talebi arşivlendi ve listeden kaldırıldı.")
    
    return redirect('icmal_raporu')

@login_required
def talep_sil(request, talep_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        messages.error(request, "Silme yetkiniz yok!")
        return redirect('icmal_raporu')

    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    talep_adi = talep.malzeme.isim if talep.malzeme else talep.is_kalemi.isim
    
    talep.delete()
    messages.warning(request, f"🗑️ {talep_adi} talebi silindi.")
    
    return redirect('icmal_raporu')

@login_required
def arsiv_raporu(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    arsiv_talepler = MalzemeTalep.objects.filter(
        durum='tamamlandi'
    ).select_related('malzeme', 'talep_eden').prefetch_related('teklifler__tedarikci').order_by('-temin_tarihi', '-tarih')

    context = {
        'aktif_talepler': arsiv_talepler,
        'arsiv_modu': True
    }
    return render(request, 'icmal.html', context)

@login_required
def talep_arsivden_cikar(request, talep_id):
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
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')

    search_query = request.GET.get('search', '')
    
    if search_query:
        malzemeler = Malzeme.objects.filter(isim__icontains=search_query)
    else:
        malzemeler = Malzeme.objects.all()

    kritik_sayisi = 0
    toplam_cesit = malzemeler.count()
    
    for malz in malzemeler:
        if malz.stok <= malz.kritik_stok:
            malz.kritik_durum = True
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

@login_required
def hizmet_listesi(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    hizmetler = IsKalemi.objects.all().select_related('kategori')
    
    return render(request, 'hizmet_listesi.html', {'hizmetler': hizmetler})

@login_required
def hizmet_ekle(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    if request.method == 'POST':
        form = IsKalemiForm(request.POST)
        if form.is_valid():
            hizmet = form.save()
            messages.success(request, f"✅ {hizmet.isim} hizmet kartı oluşturuldu.")
            return redirect('hizmet_listesi')
        else:
            messages.error(request, "Lütfen hataları düzeltiniz.")
    else:
        form = IsKalemiForm()

    return render(request, 'hizmet_ekle.html', {'form': form})

@login_required
def hizmet_duzenle(request, pk):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI', 'SAHA_VE_DEPO']):
        return redirect('erisim_engellendi')

    hizmet = get_object_or_404(IsKalemi, pk=pk)

    if request.method == 'POST':
        form = IsKalemiForm(request.POST, instance=hizmet)
        if form.is_valid():
            form.save()
            messages.success(request, f"✅ {hizmet.isim} güncellendi.")
            return redirect('hizmet_listesi')
    else:
        form = IsKalemiForm(instance=hizmet)

    return render(request, 'hizmet_ekle.html', {'form': form, 'duzenleme_modu': True})

@login_required
def hizmet_sil(request, pk):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'YONETICI', 'SAHA_VE_DEPO']):
        return redirect('erisim_engellendi')

    hizmet = get_object_or_404(IsKalemi, pk=pk)
    isim = hizmet.isim
    hizmet.delete()
    messages.warning(request, f"🗑️ {isim} listeden silindi.")
    
    return redirect('hizmet_listesi')

@login_required
def siparis_listesi(request):
    """
    Siparişleri listeler.
    ÖNEMLİ MANTIK DEĞİŞİKLİĞİ:
    Faturası kesilip 'Tamamlandı' olsa bile, eğer mal SANAL DEPODA ise 'Bekleyenler' listesinde görünür.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')

    # Tüm siparişleri çekiyoruz (DB optimizasyonu ile)
    tum_siparisler = SatinAlma.objects.select_related(
        'teklif__tedarikci', 'teklif__malzeme', 'teklif__is_kalemi'
    ).prefetch_related('depo_hareketleri', 'depo_hareketleri__depo').order_by('-created_at')

    bekleyenler = []
    bitenler = []

    for siparis in tum_siparisler:
        # 1. Henüz tamamlanmamış (kısmi veya bekliyor) siparişler -> BEKLEYEN
        if siparis.teslimat_durumu != 'tamamlandi':
            bekleyenler.append(siparis)
        
        # 2. 'Tamamlandı' görünüyor AMA Sanal Depoda malı var -> BEKLEYEN (Çünkü operasyon bitmedi)
        elif siparis.sanal_depoda_bekleyen > 0:
            bekleyenler.append(siparis)
            
        # 3. Gerçekten bitmiş (Hem faturası tam, hem sanal deposu boş) -> BİTEN
        else:
            bitenler.append(siparis)

    # Bitenleri sınırla (Son 20)
    bitenler = bitenler[:20]

    return render(request, 'siparis_listesi.html', {
        'bekleyenler': bekleyenler,
        'bitenler': bitenler
    })

@login_required
def mal_kabul(request, siparis_id):
    if not yetki_kontrol(request.user, ['SAHA_VE_DEPO', 'OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')

    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    depolar = Depo.objects.all()

    if request.method == 'POST':
        try:
            gelen_miktar = float(request.POST.get('gelen_miktar'))
        except ValueError:
            messages.error(request, "Lütfen geçerli bir sayı giriniz.")
            return redirect('mal_kabul', siparis_id=siparis.id)

        kalan_hak = siparis.kalan_miktar
        if gelen_miktar > (kalan_hak + 0.0001): 
            messages.error(request, f"⛔ HATA: Siparişten fazlasını alamazsınız! Maksimum alabileceğiniz miktar: {kalan_hak}")
            return redirect('mal_kabul', siparis_id=siparis.id)

        irsaliye_no = request.POST.get('irsaliye_no')
        depo_id = request.POST.get('depo_id')
        tarih = request.POST.get('tarih') or timezone.now()
        aciklama = request.POST.get('aciklama')

        secilen_depo = Depo.objects.get(id=depo_id)
        malzeme = siparis.teklif.malzeme
        
        if not malzeme:
             messages.error(request, "Hizmet kalemleri için mal kabulü yapılamaz.")
             return redirect('siparis_listesi')

        DepoHareket.objects.create(
            malzeme=malzeme,
            depo=secilen_depo,
            siparis=siparis,
            islem_turu='giris',
            miktar=gelen_miktar,
            tedarikci=siparis.teklif.tedarikci,
            irsaliye_no=irsaliye_no,
            tarih=tarih,
            aciklama=f"Sipariş Kabulü: {aciklama}"
        )

        siparis.teslim_edilen += gelen_miktar
        siparis.save()

        messages.success(request, f"✅ {gelen_miktar} birim giriş yapıldı. Kalan: {siparis.kalan_miktar}")
        
        if siparis.teslimat_durumu == 'tamamlandi':
            return redirect('siparis_listesi')
        else:
            return redirect('mal_kabul', siparis_id=siparis.id)

    return render(request, 'mal_kabul.html', {'siparis': siparis, 'depolar': depolar})


@login_required
def siparis_detay(request, siparis_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')
        
    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    hareketler = DepoHareket.objects.filter(siparis=siparis).order_by('-tarih')
    
    return render(request, 'siparis_detay.html', {
        'siparis': siparis,
        'hareketler': hareketler
    })

@login_required
def fatura_girisi(request, siparis_id):
    """
    GÜNCELLENMİŞ VERSİYON:
    - Form verileri (Miktar, Tutar, Tarih) artık %100 dolu gelir.
    - Fatura girildiği an stok otomatik işlenir.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    
    # --- 1. OTOMATİK VERİ HAZIRLAMA ---
    
    # Varsayılan değerler
    varsayilan_miktar = siparis.kalan_fatura_miktar
    varsayilan_tutar = 0
    varsayilan_depo = None
    
    # Tutar Hesabı (Hata önleyici float dönüşümleri ile)
    if varsayilan_miktar > 0:
        try:
            teklif = siparis.teklif
            birim_fiyat = float(teklif.birim_fiyat or 0)
            kur = float(teklif.kur_degeri or 1)
            kdv_orani = float(teklif.kdv_orani or 0)
            
            # Formül: Miktar x Birim Fiyat x Kur x (1 + KDV)
            tutar_tl = varsayilan_miktar * birim_fiyat * kur
            kdvli_tutar = tutar_tl * (1 + (kdv_orani / 100))
            
            varsayilan_tutar = round(kdvli_tutar, 2)
        except (ValueError, TypeError):
            varsayilan_tutar = 0

    # Depo Önerisi (Daha önce bu sipariş hangi depoya girdiyse onu getir)
    son_hareket = siparis.depo_hareketleri.filter(islem_turu='giris').last()
    if son_hareket and son_hareket.depo:
        varsayilan_depo = son_hareket.depo.id

    # Form için başlangıç verisi (Sözlük formatında)
    initial_data = {
        'miktar': varsayilan_miktar,
        'tutar': varsayilan_tutar,
        'tarih': timezone.now().strftime('%Y-%m-%d'), # HTML5 Date input için string format şart
        'depo': varsayilan_depo
    }

    if request.method == 'POST':
        form = FaturaGirisForm(request.POST, request.FILES)
        if form.is_valid():
            fatura = form.save(commit=False)
            fatura.satinalma = siparis
            fatura.save() # 1. Finansal Kayıt
            
            # 2. OTOMATİK STOK GİRİŞİ (Fatura Miktarı = Stok Miktarı)
            if fatura.miktar > 0 and siparis.teklif.malzeme:
                DepoHareket.objects.create(
                    malzeme=siparis.teklif.malzeme,
                    depo=fatura.depo,
                    siparis=siparis,
                    islem_turu='giris',
                    miktar=fatura.miktar,
                    tedarikci=siparis.teklif.tedarikci,
                    irsaliye_no=f"FATURA-{fatura.fatura_no}",
                    tarih=fatura.tarih,
                    aciklama=f"Fatura Girişi: {fatura.fatura_no}"
                )
                
                # Siparişin 'Teslim Edilen' (Stok) sayacını artır
                siparis.teslim_edilen += fatura.miktar
                siparis.save()
                
                messages.success(request, f"✅ Fatura işlendi. {fatura.miktar} adet stok {fatura.depo.isim} deposuna girdi.")
            else:
                messages.warning(request, "⚠️ Fatura kaydedildi ancak miktar 0 olduğu için stok oluşmadı.")
                
            return redirect('siparis_listesi')
    else:
        # GET isteğinde hesaplanan verileri forma bas
        form = FaturaGirisForm(initial=initial_data)

    context = {
        'form': form, 
        'siparis': siparis,
    }
    return render(request, 'fatura_girisi.html', context)

@login_required
def fatura_sil(request, fatura_id):
    """
    Fatura silindiğinde:
    1. O faturaya bağlı stok hareketi (Depo Girişi) silinir.
    2. Siparişin 'Teslim Edilen' ve 'Faturalanan' sayaçları geri alınır.
    3. En son Fatura kaydı silinir.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    fatura = get_object_or_404(Fatura, id=fatura_id)
    siparis = fatura.satinalma
    
    # 1. BAĞLI STOK HAREKETİNİ BUL VE SİL
    # Faturayı kaydederken "FATURA-{No}" formatında referans vermiştik.
    # Buna göre depodaki hareketi buluyoruz.
    stok_hareketi = DepoHareket.objects.filter(
        siparis=siparis,
        irsaliye_no=f"FATURA-{fatura.fatura_no}",
        islem_turu='giris'
    ).first()
    
    if stok_hareketi:
        # Stoğu siliyoruz
        stok_hareketi.delete()
        
        # Siparişin STOK sayacını geri alıyoruz
        siparis.teslim_edilen -= fatura.miktar
        if siparis.teslim_edilen < 0: siparis.teslim_edilen = 0

    # 2. SİPARİŞİN FİNANSAL SAYACINI GERİ AL
    siparis.faturalanan_miktar -= fatura.miktar
    if siparis.faturalanan_miktar < 0: siparis.faturalanan_miktar = 0
    
    # 3. SİPARİŞ DURUMUNU GÜNCELLE VE KAYDET
    siparis.save() # Modeldeki save() metodu durumu (bekliyor/kısmi) tekrar hesaplar

    # 4. FATURAYI SİL
    fatura_no = fatura.fatura_no
    fatura.delete()

    messages.warning(request, f"🗑️ Fatura #{fatura_no} ve bağlı stok girişi başarıyla silindi.")
    
    # Sipariş detayına veya listeye dön
    return redirect('siparis_listesi')


@login_required
def depo_transfer(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'DEPO_SORUMLUSU', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')

    siparis_id = request.GET.get('siparis_id') or request.POST.get('siparis_id')
    siparis = None
    
    # Dashboard Değişkenleri
    toplam_faturalanan = 0
    toplam_sevk_edilen = 0
    kalan_sevk_hakki = 0
    gecmis_hareketler = []
    
    initial_data = {'tarih': timezone.now().date()}

    if siparis_id:
        siparis = get_object_or_404(SatinAlma, id=siparis_id)
        
        # Hesaplamalar
        toplam_faturalanan = siparis.teslim_edilen 
        hareketler_query = DepoHareket.objects.filter(siparis=siparis, islem_turu='cikis').order_by('-tarih', '-id')
        gecmis_hareketler = list(hareketler_query)
        toplam_sevk_edilen = hareketler_query.aggregate(Sum('miktar'))['miktar__sum'] or 0
        kalan_sevk_hakki = toplam_faturalanan - toplam_sevk_edilen

        # Form Ön Hazırlığı
        if siparis.teklif.malzeme:
            initial_data['malzeme'] = siparis.teklif.malzeme
            sanal_depo = Depo.objects.filter(is_sanal=True).first()
            if sanal_depo: initial_data['kaynak_depo'] = sanal_depo
            fiziksel_depo = Depo.objects.filter(is_sanal=False).first()
            if fiziksel_depo: initial_data['hedef_depo'] = fiziksel_depo
            if kalan_sevk_hakki > 0: initial_data['miktar'] = kalan_sevk_hakki

    if request.method == 'POST':
        form = DepoTransferForm(request.POST)
        if form.is_valid():
            transfer = form.save(commit=False)
            
            # Stok Kontrolü
            mevcut_stok = transfer.malzeme.depo_stogu(transfer.kaynak_depo.id)
            if transfer.miktar > mevcut_stok:
                messages.error(request, f"⛔ HATA: Kaynak depoda yeterli stok yok! (Mevcut: {mevcut_stok})")
                return redirect(f"{request.path}?siparis_id={siparis_id}" if siparis_id else request.path)

            # --- SİPARİŞ BAĞLANTISI ---
            # Modeli kaydetmeden önce sipariş bilgisini "geçici" olarak nesneye ekliyoruz.
            # models.py içindeki save() metodu bu bilgiyi okuyacak.
            if siparis:
                transfer.bagli_siparis = siparis 
            
            transfer.save() # save() metodu çalışır ve hareketleri otomatik oluşturur.

            messages.success(request, f"✅ {transfer.miktar} adet ürün başarıyla sevk edildi.")
            
            if siparis:
                return redirect('siparis_listesi')
            return redirect('stok_listesi')
    else:
        form = DepoTransferForm(initial=initial_data)

    context = {
        'form': form,
        'siparis': siparis,
        'toplam_faturalanan': toplam_faturalanan,
        'toplam_sevk_edilen': toplam_sevk_edilen,
        'kalan_sevk_hakki': kalan_sevk_hakki,
        'gecmis_hareketler': gecmis_hareketler
    }
    return render(request, 'depo_transfer.html', context)

@login_required
def stok_hareketleri(request, malzeme_id):
    """
    Bir malzemenin detaylı hareket geçmişini (Loglarını) gösterir.
    Sipariş listesindeki "Geçmiş" butonuna basınca burası çalışacak.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')

    malzeme = get_object_or_404(Malzeme, id=malzeme_id)
    
    # O malzemeye ait tüm hareketleri çek (Tarihe göre yeni en üstte)
    hareketler = DepoHareket.objects.filter(malzeme=malzeme).order_by('-tarih', '-id')
    
    return render(request, 'stok_hareketleri.html', {
        'malzeme': malzeme,
        'hareketler': hareketler
    })

@login_required
def get_depo_stok(request):
    depo_id = request.GET.get('depo_id')
    malzeme_id = request.GET.get('malzeme_id')
    
    stok = 0
    if depo_id and malzeme_id:
        try:
            malzeme = Malzeme.objects.get(id=malzeme_id)
            stok = malzeme.depo_stogu(depo_id)
        except (Malzeme.DoesNotExist, ValueError):
            pass
            
    return JsonResponse({'stok': stok})

@login_required
def stok_rontgen(request, malzeme_id):
    if not request.user.is_superuser:
        return HttpResponse("Yetkiniz yok.")

    malzeme = get_object_or_404(Malzeme, id=malzeme_id)
    hareketler = DepoHareket.objects.filter(malzeme=malzeme).order_by('tarih', 'id')
    
    html = f"<h1>🛠️ STOK RÖNTGENİ: {malzeme.isim}</h1>"
    html += "<table border='1' cellpadding='5' style='border-collapse: collapse; width: 100%;'>"
    html += "<tr style='background:#eee;'><th>ID</th><th>Tarih</th><th>İşlem</th><th>Depo</th><th>Miktar</th><th>Sipariş ID (Bağlantı)</th><th>Açıklama</th><th>Eylem</th></tr>"
    
    toplam_stok = 0
    for h in hareketler:
        renk = "red" if h.islem_turu == 'cikis' else "green"
        etki = -h.miktar if h.islem_turu == 'cikis' else h.miktar
        toplam_stok += etki
        
        siparis_durumu = f"✅ #{h.siparis.id}" if h.siparis else "⚠️ <b>YOK (SAHİPSİZ)</b>"
        
        html += f"<tr>"
        html += f"<td>{h.id}</td>"
        html += f"<td>{h.tarih}</td>"
        html += f"<td style='color:{renk}; font-weight:bold;'>{h.get_islem_turu_display()}</td>"
        html += f"<td>{h.depo.isim if h.depo else '-'}</td>"
        html += f"<td>{h.miktar}</td>"
        html += f"<td>{siparis_durumu}</td>"
        html += f"<td>{h.aciklama}</td>"
        html += f"<td><a href='/admin/core/depohareket/{h.id}/delete/' target='_blank'>SİL (Admin)</a></td>"
        html += f"</tr>"
        
    html += "</table>"
    html += f"<h3>MATEMATİKSEL SONUÇ (STOK): {toplam_stok}</h3>"
    
    return HttpResponse(html)

@login_required
def envanter_raporu(request):
    """
    Tüm depoların stok durumunu detaylı gösteren rapor.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI', 'MUHASEBE_FINANS']):
        return redirect('erisim_engellendi')

    depolar = Depo.objects.all()
    rapor_data = []

    for depo in depolar:
        malzemeler = Malzeme.objects.all()
        depo_stoklari = []
        
        for malz in malzemeler:
            stok = malz.depo_stogu(depo.id)
            if stok != 0: # Sadece hareketi olanları listele
                depo_stoklari.append({
                    'malzeme': malz,
                    'miktar': stok
                })
        
        if depo_stoklari:
            rapor_data.append({
                'depo': depo,
                'stoklar': depo_stoklari
            })

    return render(request, 'envanter_raporu.html', {'rapor_data': rapor_data})

def cikis_yap(request):
    logout(request)
    return redirect('/admin/login/')