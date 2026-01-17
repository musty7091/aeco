from decimal import Decimal, ROUND_HALF_UP
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from core.models import SatinAlma, Depo, DepoHareket, Fatura
from core.forms import FaturaGirisForm
from .guvenlik import yetki_kontrol
from core.utils import to_decimal

@login_required
def siparis_listesi(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')
    
    tum_siparisler = SatinAlma.objects.select_related(
        'teklif__tedarikci', 'teklif__malzeme', 'teklif__is_kalemi'
    ).prefetch_related('depo_hareketleri', 'depo_hareketleri__depo').order_by('-created_at')

    bekleyenler, bitenler = [], []
    for siparis in tum_siparisler:
        # Sanal depoda mal varsa veya fatura kesilmemiş miktar varsa işlem bitmemiştir.
        if siparis.sanal_depoda_bekleyen > 0 or siparis.kalan_fatura_miktar > 0:
            bekleyenler.append(siparis)
        else:
            bitenler.append(siparis)

    return render(request, 'siparis_listesi.html', {'bekleyenler': bekleyenler, 'bitenler': bitenler[:20]})

@login_required
def fatura_girisi(request, siparis_id):
    """
    ADIM 1: FATURA GİRİŞİ (STOK GİRİŞİ BAŞLATIR)
    Kullanıcı faturayı girdiği an, mal 'Sanal Depo'ya girer.
    """
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    
    # Otomatik Sanal Depo Seçimi
    sanal_depo = Depo.objects.filter(is_sanal=True).first()
    
    if not sanal_depo:
        messages.error(request, "Sistemde 'Sanal Depo' (Tedarikçi Deposu) bulunamadı! Lütfen yönetici ile görüşün.")
        return redirect('siparis_listesi')

    varsayilan_miktar = to_decimal(siparis.kalan_fatura_miktar)
    varsayilan_tutar = Decimal('0.00')

    if varsayilan_miktar > 0:
        try:
            t = siparis.teklif
            bf = to_decimal(t.birim_fiyat)
            kur = to_decimal(t.kur_degeri)
            kdv = to_decimal(t.kdv_orani)
            varsayilan_tutar = (varsayilan_miktar * bf * kur * (1 + (kdv / 100))).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)
        except: pass

    # Depo formda seçili gelsin
    initial_data = {
        'miktar': varsayilan_miktar, 
        'tutar': varsayilan_tutar, 
        'tarih': timezone.now().strftime('%Y-%m-%d'), 
        'depo': sanal_depo.id 
    }

    if request.method == 'POST':
        form = FaturaGirisForm(request.POST, request.FILES)
        if form.is_valid():
            fatura = form.save(commit=False)
            fatura.satinalma = siparis
            
            # Kullanıcı değiştirmeye çalışsa bile biz yine de Sanal Depo'ya zorluyoruz
            # (veya formdaki disabled alandan gelen veriyi kullanıyoruz)
            if not fatura.depo:
                fatura.depo = sanal_depo

            fatura.save() # Fatura kaydedildi (Finansal)

            # --- SANAL STOK GİRİŞİ ---
            if fatura.miktar > 0 and siparis.teklif.malzeme:
                DepoHareket.objects.create(
                    malzeme=siparis.teklif.malzeme,
                    depo=fatura.depo, # Sanal Depo
                    siparis=siparis,
                    islem_turu='giris',
                    miktar=fatura.miktar,
                    tedarikci=siparis.teklif.tedarikci,
                    irsaliye_no=f"FAT-{fatura.fatura_no}",
                    tarih=fatura.tarih,
                    aciklama=f"Fatura ile Sanal Stok ({fatura.fatura_no})"
                )
                messages.success(request, f"✅ Fatura işlendi. {fatura.miktar} birim 'Sanal Depo'ya eklendi.")
            else:
                messages.warning(request, "⚠️ Fatura kaydedildi (Stoksuz).")
                
            return redirect('siparis_listesi')
    else:
        form = FaturaGirisForm(initial=initial_data)

    return render(request, 'fatura_girisi.html', {'form': form, 'siparis': siparis})

@login_required
def mal_kabul(request, siparis_id):
    """
    ADIM 2: SEVKİYAT / TRANSFER
    Sanal Depo'dan -> Fiziksel Depo'ya transfer.
    """
    if not yetki_kontrol(request.user, ['SAHA_VE_DEPO', 'OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')
    
    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    fiziksel_depolar = Depo.objects.filter(is_sanal=False)
    sanal_depo = Depo.objects.filter(is_sanal=True).first()

    if request.method == 'POST':
        try: 
            ham_miktar = request.POST.get('gelen_miktar', '0').replace(',', '.')
            transfer_miktar = Decimal(ham_miktar)
        except:
            messages.error(request, "Geçersiz miktar.")
            return redirect('mal_kabul', siparis_id=siparis.id)

        hedef_depo_id = request.POST.get('depo_id')
        
        if not sanal_depo:
            messages.error(request, "Sanal depo bulunamadı.")
            return redirect('siparis_listesi')

        bekleyen = siparis.sanal_depoda_bekleyen
        if transfer_miktar > (bekleyen + Decimal('0.0001')):
            messages.error(request, f"HATA: Sanal depoda sadece {bekleyen} birim mal görünüyor.")
            return redirect('mal_kabul', siparis_id=siparis.id)

        # 1. Sanal Depodan ÇIKIŞ
        DepoHareket.objects.create(
            malzeme=siparis.teklif.malzeme,
            depo=sanal_depo,
            siparis=siparis,
            islem_turu='cikis',
            miktar=transfer_miktar,
            tedarikci=siparis.teklif.tedarikci,
            irsaliye_no=request.POST.get('irsaliye_no'),
            tarih=request.POST.get('tarih') or timezone.now(),
            aciklama=f"Sevkiyat Çıkışı: {request.POST.get('aciklama')}"
        )
        
        # 2. Fiziksel Depoya GİRİŞ
        DepoHareket.objects.create(
            malzeme=siparis.teklif.malzeme,
            depo_id=hedef_depo_id,
            siparis=siparis,
            islem_turu='giris',
            miktar=transfer_miktar,
            tedarikci=siparis.teklif.tedarikci,
            irsaliye_no=request.POST.get('irsaliye_no'),
            tarih=request.POST.get('tarih') or timezone.now(),
            aciklama=f"Saha Girişi: {request.POST.get('aciklama')}"
        )
        
        # Fiziksel teslimat miktarını güncelle
        siparis.teslim_edilen = to_decimal(siparis.teslim_edilen) + transfer_miktar
        siparis.save()
        
        messages.success(request, f"✅ {transfer_miktar} birim sahaya indirildi.")
        return redirect('siparis_listesi')

    return render(request, 'mal_kabul.html', {'siparis': siparis, 'depolar': fiziksel_depolar})

@login_required
def siparis_detay(request, siparis_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')
    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    hareketler = DepoHareket.objects.filter(siparis=siparis).order_by('-tarih')
    faturalar = siparis.faturalar.all().order_by('-tarih')
    
    return render(request, 'siparis_detay.html', {
        'siparis': siparis, 
        'hareketler': hareketler,
        'faturalar': faturalar
    })

@login_required
def fatura_sil(request, fatura_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')
    
    fatura = get_object_or_404(Fatura, id=fatura_id)
    siparis = fatura.satinalma
    
    # Bağlı sanal stok girişini sil
    bagli_hareket = DepoHareket.objects.filter(
        siparis=siparis, 
        irsaliye_no=f"FAT-{fatura.fatura_no}",
        islem_turu='giris'
    ).first()
    
    if bagli_hareket:
        bagli_hareket.delete()

    yeni_faturalanan = to_decimal(siparis.faturalanan_miktar) - to_decimal(fatura.miktar)
    siparis.faturalanan_miktar = max(Decimal('0'), yeni_faturalanan)
    siparis.save()
    
    fatura.delete()
    messages.warning(request, f"🗑️ Fatura ve sanal stok kaydı silindi.")
    return redirect('siparis_listesi')