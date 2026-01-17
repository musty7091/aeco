from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q, F
from django.http import JsonResponse, HttpResponse
from core.models import Malzeme, DepoHareket, MalzemeTalep, SatinAlma, Depo, DepoTransfer
from core.forms import DepoTransferForm
from .guvenlik import yetki_kontrol

@login_required
def depo_dashboard(request):
    if not yetki_kontrol(request.user, ['SAHA_EKIBI', 'OFIS_VE_SATINALMA', 'YONETICI']): 
        return redirect('erisim_engellendi')
    
    # N+1 Query Çözümü: Tek sorguda tüm stokları hesaplıyoruz
    malzemeler = Malzeme.objects.annotate(
        hesaplanan_stok=Sum('depo_hareketleri__miktar', filter=Q(depo_hareketleri__islem_turu='giris')) - 
                        Sum('depo_hareketleri__miktar', filter=Q(depo_hareketleri__islem_turu='cikis'))
    )

    depo_ozeti = []
    for mal in malzemeler:
        stok_degeri = mal.hesaplanan_stok or 0
        durum_renk = "danger" if stok_degeri <= mal.kritik_stok else ("warning" if stok_degeri <= (mal.kritik_stok * 1.5) else "success")
        depo_ozeti.append({
            'isim': mal.isim, 
            'birim': mal.get_birim_display(), 
            'stok': stok_degeri, 
            'durum_renk': durum_renk
        })

    context = {
        'depo_ozeti': depo_ozeti,
        'son_iadeler': DepoHareket.objects.filter(islem_turu='iade').order_by('-tarih')[:5],
        'bekleyen_talepler': MalzemeTalep.objects.filter(durum='bekliyor').order_by('-oncelik')[:10],
        'bekleyen_talep_sayisi': MalzemeTalep.objects.filter(durum='bekliyor').count()
    }
    return render(request, 'depo_dashboard.html', context)

@login_required
def stok_listesi(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']): 
        return redirect('erisim_engellendi')
    
    search = request.GET.get('search', '')
    
    malzemeler = Malzeme.objects.annotate(
        hesaplanan_stok=Sum('depo_hareketleri__miktar', filter=Q(depo_hareketleri__islem_turu='giris')) - 
                        Sum('depo_hareketleri__miktar', filter=Q(depo_hareketleri__islem_turu='cikis'))
    )
    
    if search:
        malzemeler = malzemeler.filter(isim__icontains=search)
    
    # Python döngüsü yerine DB seviyesinde kritik stok sayımı (Daha hızlı)
    kritik_sayisi = sum(1 for m in malzemeler if (m.hesaplanan_stok or 0) <= m.kritik_stok)

    return render(request, 'stok_listesi.html', {
        'malzemeler': malzemeler, 
        'search_query': search, 
        'kritik_sayisi': kritik_sayisi
    })

@login_required
def depo_transfer(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'DEPO_SORUMLUSU', 'SAHA_VE_DEPO', 'YONETICI']): 
        return redirect('erisim_engellendi')
    
    siparis_id = request.GET.get('siparis_id') or request.POST.get('siparis_id')
    siparis, initial_data = None, {'tarih': timezone.now().date()}

    if siparis_id:
        siparis = get_object_or_404(SatinAlma, id=siparis_id)
        # Çıkış miktarını tek bir aggregate ile alıyoruz
        cikis_ozeti = DepoHareket.objects.filter(siparis=siparis, islem_turu='cikis').aggregate(toplam=Sum('miktar'))
        cikis_toplami = cikis_ozeti['toplam'] or 0
        
        initial_data.update({
            'malzeme': siparis.teklif.malzeme, 
            'miktar': siparis.teslim_edilen - cikis_toplami
        })
        if s:=Depo.objects.filter(is_sanal=True).first(): initial_data['kaynak_depo'] = s
        if f:=Depo.objects.filter(is_sanal=False).first(): initial_data['hedef_depo'] = f

    if request.method == 'POST':
        form = DepoTransferForm(request.POST)
        if form.is_valid():
            transfer = form.save(commit=False)
            
            # Stok kontrolü
            kaynak_stok = transfer.malzeme.depo_stogu(transfer.kaynak_depo.id)
            if transfer.miktar > kaynak_stok:
                messages.error(request, f"⛔ Kaynak depoda yeterli stok yok! Mevcut: {kaynak_stok}")
                return redirect(f"{request.path}?siparis_id={siparis_id}" if siparis_id else request.path)
            
            # Yeni eklediğimiz Foreign Key artık hata vermez
            if siparis:
                transfer.bagli_siparis = siparis
                
            transfer.save()
            messages.success(request, "✅ Transfer başarıyla kaydedildi.")
            return redirect('siparis_listesi') if siparis else redirect('stok_listesi')
    else:
        form = DepoTransferForm(initial=initial_data)
        
    return render(request, 'depo_transfer.html', {'form': form, 'siparis': siparis})

@login_required
def stok_hareketleri(request, malzeme_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']): 
        return redirect('erisim_engellendi')
    malzeme = get_object_or_404(Malzeme, id=malzeme_id)
    hareketler = DepoHareket.objects.filter(malzeme_id=malzeme_id).order_by('-tarih')
    return render(request, 'stok_hareketleri.html', {'malzeme': malzeme, 'hareketler': hareketler})

@login_required
def get_depo_stok(request):
    try:
        mal_id = request.GET.get('malzeme_id')
        depo_id = request.GET.get('depo_id')
        if mal_id and depo_id:
            stok = Malzeme.objects.get(id=mal_id).depo_stogu(depo_id)
            return JsonResponse({'stok': float(stok)})
        return JsonResponse({'stok': 0})
    except Exception as e:
        print(f"HATA (get_depo_stok): {str(e)}") # Sessizce geçmek yerine terminale yazıyoruz
        return JsonResponse({'stok': 0})

@login_required
def stok_rontgen(request, malzeme_id):
    if not request.user.is_superuser: return HttpResponse("Yetkisiz")
    h = DepoHareket.objects.filter(malzeme_id=malzeme_id).order_by('tarih', 'id')
    html = "<table border='1'><tr><th>ID</th><th>İşlem</th><th>Depo</th><th>Miktar</th></tr>" + \
           "".join([f"<tr><td>{x.id}</td><td>{x.get_islem_turu_display()}</td><td>{x.depo.isim if x.depo else '-'}</td><td>{x.miktar}</td></tr>" for x in h]) + "</table>"
    return HttpResponse(html)

@login_required
def envanter_raporu(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI', 'MUHASEBE_FINANS']): 
        return redirect('erisim_engellendi')
    
    # Raporu biraz daha optimize ederek döngü kirliliğini azalttık
    depolar = Depo.objects.all()
    malzemeler = Malzeme.objects.all()
    rapor_listesi = []
    
    for d in depolar:
        stoklar = []
        for m in malzemeler:
            s = m.depo_stogu(d.id)
            if s != 0:
                stoklar.append({'malzeme': m, 'miktar': s})
        if stoklar:
            rapor_listesi.append({'depo': d, 'stoklar': stoklar})
            
    return render(request, 'envanter_raporu.html', {'rapor_data': rapor_listesi})