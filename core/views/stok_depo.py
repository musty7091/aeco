from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from django.http import JsonResponse, HttpResponse
from core.models import Malzeme, Depo, DepoHareket, MalzemeTalep, SatinAlma
from core.forms import DepoTransferForm
from .guvenlik import yetki_kontrol

@login_required
def depo_dashboard(request):
    if not yetki_kontrol(request.user, ['SAHA_EKIBI', 'OFIS_VE_SATINALMA', 'YONETICI']): return redirect('erisim_engellendi')
    depo_ozeti = []
    for mal in Malzeme.objects.all():
        durum_renk = "danger" if mal.stok <= mal.kritik_stok else ("warning" if mal.stok <= (mal.kritik_stok * 1.5) else "success")
        depo_ozeti.append({'isim': mal.isim, 'birim': mal.get_birim_display(), 'stok': mal.stok, 'durum_renk': durum_renk})
    context = {
        'depo_ozeti': depo_ozeti,
        'son_iadeler': DepoHareket.objects.filter(islem_turu='iade').order_by('-tarih')[:5],
        'bekleyen_talepler': MalzemeTalep.objects.filter(durum='bekliyor').order_by('-oncelik')[:10],
        'bekleyen_talep_sayisi': MalzemeTalep.objects.filter(durum='bekliyor').count()
    }
    return render(request, 'depo_dashboard.html', context)

@login_required
def stok_listesi(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']): return redirect('erisim_engellendi')
    search = request.GET.get('search', '')
    malzemeler = Malzeme.objects.filter(isim__icontains=search) if search else Malzeme.objects.all()
    kritik = sum(1 for m in malzemeler if m.stok <= m.kritik_stok)
    return render(request, 'stok_listesi.html', {'malzemeler': malzemeler, 'search_query': search, 'kritik_sayisi': kritik})

@login_required
def depo_transfer(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'DEPO_SORUMLUSU', 'SAHA_VE_DEPO', 'YONETICI']): return redirect('erisim_engellendi')
    siparis_id = request.GET.get('siparis_id') or request.POST.get('siparis_id')
    siparis, initial_data = None, {'tarih': timezone.now().date()}

    if siparis_id:
        siparis = get_object_or_404(SatinAlma, id=siparis_id)
        initial_data.update({'malzeme': siparis.teklif.malzeme, 'miktar': siparis.teslim_edilen - (DepoHareket.objects.filter(siparis=siparis, islem_turu='cikis').aggregate(Sum('miktar'))['miktar__sum'] or 0)})
        if s:=Depo.objects.filter(is_sanal=True).first(): initial_data['kaynak_depo'] = s
        if f:=Depo.objects.filter(is_sanal=False).first(): initial_data['hedef_depo'] = f

    if request.method == 'POST':
        form = DepoTransferForm(request.POST)
        if form.is_valid():
            transfer = form.save(commit=False)
            if transfer.miktar > transfer.malzeme.depo_stogu(transfer.kaynak_depo.id):
                messages.error(request, "⛔ Kaynak depoda yeterli stok yok!")
                return redirect(f"{request.path}?siparis_id={siparis_id}" if siparis_id else request.path)
            if siparis: transfer.bagli_siparis = siparis
            transfer.save()
            messages.success(request, "✅ Transfer başarılı.")
            return redirect('siparis_listesi') if siparis else redirect('stok_listesi')
    else:
        form = DepoTransferForm(initial=initial_data)
    return render(request, 'depo_transfer.html', {'form': form, 'siparis': siparis})

@login_required
def stok_hareketleri(request, malzeme_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI']): return redirect('erisim_engellendi')
    return render(request, 'stok_hareketleri.html', {'malzeme': get_object_or_404(Malzeme, id=malzeme_id), 'hareketler': DepoHareket.objects.filter(malzeme_id=malzeme_id).order_by('-tarih')})

@login_required
def get_depo_stok(request):
    try: return JsonResponse({'stok': Malzeme.objects.get(id=request.GET.get('malzeme_id')).depo_stogu(request.GET.get('depo_id'))})
    except: return JsonResponse({'stok': 0})

@login_required
def stok_rontgen(request, malzeme_id):
    if not request.user.is_superuser: return HttpResponse("Yetkisiz")
    h = DepoHareket.objects.filter(malzeme_id=malzeme_id).order_by('tarih', 'id')
    html = "<table border='1'><tr><th>ID</th><th>İşlem</th><th>Depo</th><th>Miktar</th></tr>" + "".join([f"<tr><td>{x.id}</td><td>{x.get_islem_turu_display()}</td><td>{x.depo.isim if x.depo else '-'}</td><td>{x.miktar}</td></tr>" for x in h]) + "</table>"
    return HttpResponse(html)

@login_required
def envanter_raporu(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'SAHA_VE_DEPO', 'YONETICI', 'MUHASEBE_FINANS']): return redirect('erisim_engellendi')
    rapor = [{'depo': d, 'stoklar': [{'malzeme': m, 'miktar': s} for m in Malzeme.objects.all() if (s:=m.depo_stogu(d.id)) != 0]} for d in Depo.objects.all()]
    return render(request, 'envanter_raporu.html', {'rapor_data': [r for r in rapor if r['stoklar']]})