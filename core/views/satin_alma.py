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
        if siparis.teslimat_durumu != 'tamamlandi' or siparis.sanal_depoda_bekleyen > 0:
            bekleyenler.append(siparis)
        else:
            bitenler.append(siparis)

    return render(request, 'siparis_listesi.html', {'bekleyenler': bekleyenler, 'bitenler': bitenler[:20]})

@login_required
def mal_kabul(request, siparis_id):
    if not yetki_kontrol(request.user, ['SAHA_VE_DEPO', 'OFIS_VE_SATINALMA', 'YONETICI']):
        return redirect('erisim_engellendi')
    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    depolar = Depo.objects.all()

    if request.method == 'POST':
        try: 
            # Miktar Decimal olmalı
            gelen_miktar = Decimal(request.POST.get('gelen_miktar').replace(',', '.'))
        except:
            messages.error(request, "Lütfen geçerli bir sayı giriniz.")
            return redirect('mal_kabul', siparis_id=siparis.id)

        # Decimal Karşılaştırma
        if gelen_miktar > (to_decimal(siparis.kalan_miktar) + Decimal('0.0001')): 
            messages.error(request, f"⛔ HATA: Maksimum alabileceğiniz miktar: {siparis.kalan_miktar}")
            return redirect('mal_kabul', siparis_id=siparis.id)

        if not siparis.teklif.malzeme:
             messages.error(request, "Hizmet kalemleri için mal kabulü yapılamaz.")
             return redirect('siparis_listesi')

        DepoHareket.objects.create(
            malzeme=siparis.teklif.malzeme,
            depo_id=request.POST.get('depo_id'),
            siparis=siparis,
            islem_turu='giris',
            miktar=gelen_miktar,
            tedarikci=siparis.teklif.tedarikci,
            irsaliye_no=request.POST.get('irsaliye_no'),
            tarih=request.POST.get('tarih') or timezone.now(),
            aciklama=f"Sipariş Kabulü: {request.POST.get('aciklama')}"
        )
        
        # Miktar güncelleme (Decimal olarak)
        siparis.teslim_edilen = to_decimal(siparis.teslim_edilen) + gelen_miktar
        siparis.save()
        
        messages.success(request, f"✅ {gelen_miktar} birim giriş yapıldı.")
        
        return redirect('siparis_listesi') if siparis.teslimat_durumu == 'tamamlandi' else redirect('mal_kabul', siparis_id=siparis.id)

    return render(request, 'mal_kabul.html', {'siparis': siparis, 'depolar': depolar})

@login_required
def siparis_detay(request, siparis_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']):
        return redirect('erisim_engellendi')
    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    hareketler = DepoHareket.objects.filter(siparis=siparis).order_by('-tarih')
    return render(request, 'siparis_detay.html', {'siparis': siparis, 'hareketler': hareketler})

@login_required
def fatura_girisi(request, siparis_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    
    # Decimal Hesaplama
    varsayilan_miktar = to_decimal(siparis.kalan_fatura_miktar)
    varsayilan_tutar = Decimal('0.00')
    varsayilan_depo = None
    
    if varsayilan_miktar > 0:
        try:
            t = siparis.teklif
            bf = to_decimal(t.birim_fiyat)
            kur = to_decimal(t.kur_degeri)
            kdv = to_decimal(t.kdv_orani)
            
            # Formül: Miktar * BF * Kur * (1 + KDV/100)
            ara_toplam = varsayilan_miktar * bf * kur
            kdvli_tutar = ara_toplam * (1 + (kdv / 100))
            
            varsayilan_tutar = kdvli_tutar.quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)
        except Exception as e: 
            print(f"Hesap Hatası: {e}")

    son_hareket = siparis.depo_hareketleri.filter(islem_turu='giris').last()
    if son_hareket and son_hareket.depo: varsayilan_depo = son_hareket.depo.id

    initial_data = {'miktar': varsayilan_miktar, 'tutar': varsayilan_tutar, 'tarih': timezone.now().strftime('%Y-%m-%d'), 'depo': varsayilan_depo}

    if request.method == 'POST':
        form = FaturaGirisForm(request.POST, request.FILES)
        if form.is_valid():
            fatura = form.save(commit=False)
            fatura.satinalma = siparis
            fatura.save() 
            
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
                siparis.teslim_edilen = to_decimal(siparis.teslim_edilen) + to_decimal(fatura.miktar)
                siparis.save()
                messages.success(request, f"✅ Fatura işlendi. {fatura.miktar} adet stok girişi yapıldı.")
            else:
                messages.warning(request, "⚠️ Fatura kaydedildi ancak stok oluşmadı.")
            return redirect('siparis_listesi')
    else:
        form = FaturaGirisForm(initial=initial_data)

    return render(request, 'fatura_girisi.html', {'form': form, 'siparis': siparis})

@login_required
def fatura_sil(request, fatura_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')
    fatura = get_object_or_404(Fatura, id=fatura_id)
    siparis = fatura.satinalma
    
    stok_hareketi = DepoHareket.objects.filter(siparis=siparis, irsaliye_no=f"FATURA-{fatura.fatura_no}", islem_turu='giris').first()
    if stok_hareketi:
        stok_hareketi.delete()
        # Decimal işlem
        yeni_teslim = to_decimal(siparis.teslim_edilen) - to_decimal(fatura.miktar)
        siparis.teslim_edilen = max(Decimal('0'), yeni_teslim)

    yeni_faturalanan = to_decimal(siparis.faturalanan_miktar) - to_decimal(fatura.miktar)
    siparis.faturalanan_miktar = max(Decimal('0'), yeni_faturalanan)
    
    siparis.save()
    fatura.delete()
    messages.warning(request, f"🗑️ Fatura ve bağlı stok girişi silindi.")
    return redirect('siparis_listesi')