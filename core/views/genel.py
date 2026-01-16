from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.db.models import Sum
from core.models import (
    SatinAlma, Fatura, MalzemeTalep, 
    Depo, Malzeme, DepoTuru
)

def erisim_engellendi(request):
    return render(request, 'erisim_engellendi.html')

def cikis_yap(request):
    logout(request)
    return redirect('/admin/')  # Çıkış yapınca admin paneline veya login'e atar

@login_required
@login_required
def dashboard(request):
    # 1. Bekleyen İşler (Onay bekleyenler)
    bekleyen_talepler = MalzemeTalep.objects.filter(durum='bekliyor').count()
    
    # YENİ EKLENEN: Teklif/Fiyatlandırma Bekleyenler (Durumu 'islemde' olanlar)
    teklif_bekleyenler = MalzemeTalep.objects.filter(durum='islemde').count()
    
    # Siparişi verilmiş ama teslim alınmamışlar
    bekleyen_siparisler = SatinAlma.objects.filter(teslim_edilen=0).count()
    
    # 2. Finansal Özet
    toplam_fatura_tutari = Fatura.objects.aggregate(t=Sum('toplam_tutar'))['t'] or 0
    
    # 3. Depo Durumu
    merkez_depo_sayisi = Depo.objects.filter(tur=DepoTuru.MERKEZ).count()
    santiye_depo_sayisi = Depo.objects.filter(tur=DepoTuru.KULLANIM).count()
    
    # Kritik Stok
    kritik_stok_sayisi = 0
    for m in Malzeme.objects.all():
        if m.stok <= m.kritik_stok:
            kritik_stok_sayisi += 1

    context = {
        'bekleyen_talepler': bekleyen_talepler,
        'teklif_bekleyenler': teklif_bekleyenler, # HTML'e gönderiyoruz
        'bekleyen_siparisler': bekleyen_siparisler,
        'toplam_borc': toplam_fatura_tutari,
        'merkez_depo_sayisi': merkez_depo_sayisi,
        'santiye_depo_sayisi': santiye_depo_sayisi,
        'kritik_stok_sayisi': kritik_stok_sayisi,
    }
    
    return render(request, 'dashboard.html', context)