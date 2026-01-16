from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, F
from django.http import JsonResponse
from core.models import Tedarikci, Fatura, Odeme, Kategori, GiderKategorisi, Hakedis, SatinAlma
from core.forms import OdemeForm, HakedisForm
from core.utils import tcmb_kur_getir
from .guvenlik import yetki_kontrol

@login_required
def finans_dashboard(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')
    guncel_kurlar = tcmb_kur_getir()
    kur_usd, kur_eur, kur_gbp = float(guncel_kurlar.get('USD', 1)), float(guncel_kurlar.get('EUR', 1)), float(guncel_kurlar.get('GBP', 1))
    
    def cevir(tl): return {'usd': tl/kur_usd, 'eur': tl/kur_eur, 'gbp': tl/kur_gbp}
    
    imalat_maliyeti = harcama_tutari = 0
    imalat_labels, imalat_data, gider_labels, gider_data = [], [], [], []
    toplam_kalem = dolu_kalem = 0

    for kat in Kategori.objects.prefetch_related('kalemler__teklifler').all():
        kat_toplam = 0
        for kalem in kat.kalemler.all():
            toplam_kalem += 1
            onayli = kalem.teklifler.filter(durum='onaylandi').first()
            if onayli:
                kat_toplam += onayli.toplam_fiyat_tl
                dolu_kalem += 1
            elif kalem.teklifler.filter(durum='beklemede').exists():
                kat_toplam += min(t.toplam_fiyat_tl for t in kalem.teklifler.filter(durum='beklemede'))
                dolu_kalem += 1
        if kat_toplam > 0:
            imalat_labels.append(kat.isim)
            imalat_data.append(round(kat_toplam, 2))
            imalat_maliyeti += kat_toplam

    for gk in GiderKategorisi.objects.prefetch_related('harcamalar').all():
        gt = sum(h.tl_tutar for h in gk.harcamalar.all())
        if gt > 0:
            gider_labels.append(gk.isim)
            gider_data.append(round(gt, 2))
            harcama_tutari += gt

    toplam_onaylanan_borc = sum(t.toplam_fiyat_tl for t in Tedarikci.objects.all() for t in t.teklifler.filter(durum='onaylandi'))
    toplam_odenen = float(Odeme.objects.aggregate(Sum('tutar'))['tutar__sum'] or 0)
    
    context = {
        'imalat_maliyeti': imalat_maliyeti, 'harcama_tutari': harcama_tutari,
        'genel_toplam': imalat_maliyeti + harcama_tutari, 'kalan_borc': toplam_onaylanan_borc - toplam_odenen,
        'oran': int((dolu_kalem/toplam_kalem)*100) if toplam_kalem else 0,
        'doviz_genel': cevir(imalat_maliyeti + harcama_tutari),
        'imalat_labels': imalat_labels, 'imalat_data': imalat_data, 'gider_labels': gider_labels, 'gider_data': gider_data,
        'kurlar': guncel_kurlar,
    }
    return render(request, 'finans_dashboard.html', context)

@login_required
def finans_ozeti(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')
    finans_verisi = []
    genel_borc = genel_odenen = genel_bakiye = 0
    for ted in Tedarikci.objects.all():
        borc = sum(f.tutar for f in Fatura.objects.filter(satinalma__teklif__tedarikci=ted))
        odenen = float(sum(o.tutar for o in ted.odemeler.all()))
        if borc > 0 or odenen > 0:
            finans_verisi.append({'id': ted.id, 'firma': ted.firma_unvani, 'borc': borc, 'odenen': odenen, 'bakiye': borc - odenen})
            genel_borc += borc; genel_odenen += odenen; genel_bakiye += (borc - odenen)
    return render(request, 'finans_ozeti.html', {'veriler': finans_verisi, 'toplam_borc': genel_borc, 'toplam_odenen': genel_odenen, 'toplam_bakiye': genel_bakiye})

@login_required
def odeme_dashboard(request):
    if not yetki_kontrol(request.user, ['MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')
    hakedis_toplam = float(Hakedis.objects.filter(onay_durumu=True).aggregate(Sum('odenecek_net_tutar'))['odenecek_net_tutar__sum'] or 0)
    malzeme_borcu = 0
    for sip in SatinAlma.objects.filter(teklif__malzeme__isnull=False):
        try: malzeme_borcu += (float(sip.teslim_edilen) * float(sip.teklif.birim_fiyat) * float(sip.teklif.kur_degeri)) * (1 + (float(sip.teklif.kdv_orani)/100))
        except: pass
    toplam_odenen = float(Odeme.objects.aggregate(Sum('tutar'))['tutar__sum'] or 0)
    
    context = {
        'hakedis_toplam': hakedis_toplam, 'malzeme_borcu': malzeme_borcu,
        'toplam_borc': (hakedis_toplam + malzeme_borcu) - toplam_odenen,
        'son_hakedisler': Hakedis.objects.order_by('-tarih')[:5],
        'son_alimlar': SatinAlma.objects.filter(teklif__malzeme__isnull=False).order_by('-created_at')[:5]
    }
    return render(request, 'odeme_dashboard.html', context)

@login_required
def cek_takibi(request):
    if not yetki_kontrol(request.user, ['MUHASEBE_FINANS', 'YONETICI']): return redirect('erisim_engellendi')
    bugun = timezone.now().date()
    cekler = Odeme.objects.filter(odeme_turu='cek').order_by('cek_vade_tarihi')
    context = {
        'gecikmisler': cekler.filter(vade_tarihi__lt=bugun),
        'yaklasanlar': cekler.filter(vade_tarihi__gte=bugun, vade_tarihi__lte=bugun+timezone.timedelta(days=30)),
        'ileri_tarihliler': cekler.filter(vade_tarihi__gt=bugun+timezone.timedelta(days=30)),
        'toplam_risk': float(sum(c.tutar for c in cekler)), 'bugun': bugun
    }
    return render(request, 'cek_takibi.html', context)

@login_required
def cek_durum_degistir(request, odeme_id):
    messages.info(request, "Çek durumu değiştirme özelliği henüz aktif değil.")
    return redirect('cek_takibi')

@login_required
def tedarikci_ekstresi(request, tedarikci_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']): return redirect('erisim_engellendi')
    tedarikci = get_object_or_404(Tedarikci, id=tedarikci_id)
    hareketler = []
    for t in tedarikci.teklifler.filter(durum='onaylandi'):
        isim = t.malzeme.isim if t.malzeme else (t.is_kalemi.isim if t.is_kalemi else "-")
        hareketler.append({'tarih': t.olusturulma_tarihi.date(), 'tur': 'BORÇ', 'aciklama': f"{isim}", 'borc': t.toplam_fiyat_tl, 'alacak': 0})
    for o in tedarikci.odemeler.all():
        hareketler.append({'tarih': o.tarih, 'tur': f'ÖDEME ({o.odeme_turu})', 'aciklama': o.aciklama, 'borc': 0, 'alacak': float(o.tutar)})
    
    hareketler.sort(key=lambda x: x['tarih'])
    bakiye = 0
    for h in hareketler:
        bakiye += (h['borc'] - h['alacak'])
        h['bakiye'] = bakiye

    return render(request, 'tedarikci_ekstre.html', {'tedarikci': tedarikci, 'hareketler': hareketler, 'son_bakiye': bakiye})

@login_required
def hakedis_ekle(request, siparis_id):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']): return redirect('erisim_engellendi')
    siparis = get_object_or_404(SatinAlma, id=siparis_id)
    if siparis.teklif.malzeme:
        messages.warning(request, "Malzeme siparişleri için Hakediş değil, Fatura girmelisiniz.")
        return redirect('fatura_girisi', siparis_id=siparis.id)

    if request.method == 'POST':
        form = HakedisForm(request.POST)
        if form.is_valid():
            hakedis = form.save(commit=False)
            hakedis.satinalma = siparis; hakedis.onay_durumu = True; hakedis.save()
            try:
                siparis.teslim_edilen += (float(siparis.toplam_miktar) * float(hakedis.tamamlanma_orani)) / 100.0
                siparis.faturalanan_miktar += (float(siparis.toplam_miktar) * float(hakedis.tamamlanma_orani)) / 100.0
                siparis.save()
            except: pass
            messages.success(request, f"✅ Hakediş #{hakedis.hakedis_no} onaylandı.")
            return redirect('siparis_listesi')
    else:
        form = HakedisForm(initial={'tarih': timezone.now().date(), 'hakedis_no': Hakedis.objects.filter(satinalma=siparis).count() + 1})
    return render(request, 'hakedis_ekle.html', {'form': form, 'siparis': siparis})

@login_required
def odeme_yap(request):
    if not yetki_kontrol(request.user, ['MUHASEBE_FINANS', 'YONETICI']): return redirect('erisim_engellendi')
    tedarikci_id = request.GET.get('tedarikci_id') or request.POST.get('tedarikci')
    acik_kalemler, secilen_tedarikci, toplam_borc = [], None, 0
    
    if tedarikci_id:
        try:
            secilen_tedarikci = Tedarikci.objects.get(id=tedarikci_id)
            for hk in Hakedis.objects.filter(onay_durumu=True, satinalma__teklif__tedarikci=secilen_tedarikci).annotate(kalan=F('odenecek_net_tutar')-F('fiili_odenen_tutar')).filter(kalan__gt=0.1):
                acik_kalemler.append({'id': hk.id, 'tip': 'hakedis', 'tarih': hk.tarih, 'aciklama': f"Hakediş #{hk.hakedis_no}", 'kalan_tutar': hk.kalan})
                toplam_borc += float(hk.kalan)
            for mal in SatinAlma.objects.filter(teklif__tedarikci=secilen_tedarikci, teklif__malzeme__isnull=False).exclude(teslimat_durumu='bekliyor'):
                try:
                    ft = float(mal.teslim_edilen)*float(mal.teklif.birim_fiyat)*float(mal.teklif.kur_degeri)*(1+float(mal.teklif.kdv_orani)/100)
                    kalan = ft - float(mal.fiili_odenen_tutar)
                    if kalan > 1: acik_kalemler.append({'id': mal.id, 'tip': 'malzeme', 'tarih': mal.created_at.date(), 'aciklama': f"{mal.teklif.malzeme.isim}", 'kalan_tutar': kalan}); toplam_borc += kalan
                except: pass
        except: pass

    if request.method == 'POST':
        form = OdemeForm(request.POST)
        if form.is_valid():
            odeme = form.save(commit=False)
            try: odeme.tutar = float(str(form.cleaned_data['tutar']).replace(',', '.'))
            except: pass
            odeme.save()
            dagitilacak = float(odeme.tutar)
            secilenler = request.POST.getlist('secilen_kalem')
            if len(secilenler)==1 and secilenler[0].startswith('hakedis_'):
                try: odeme.bagli_hakedis_id = int(secilenler[0].split('_')[1]); odeme.save()
                except: pass
            
            for secim in secilenler:
                if dagitilacak <= 0: break
                tip, id_str = secim.split('_')
                if tip == 'hakedis':
                    hk = Hakedis.objects.get(id=id_str)
                    odenen = min(dagitilacak, float(hk.odenecek_net_tutar)-float(hk.fiili_odenen_tutar))
                    hk.fiili_odenen_tutar = float(hk.fiili_odenen_tutar) + odenen; hk.save()
                    dagitilacak -= odenen
                elif tip == 'malzeme':
                    mal = SatinAlma.objects.get(id=id_str)
                    ft = float(mal.teslim_edilen)*float(mal.teklif.birim_fiyat)*float(mal.teklif.kur_degeri)*(1+float(mal.teklif.kdv_orani)/100)
                    odenen = min(dagitilacak, ft-float(mal.fiili_odenen_tutar))
                    mal.fiili_odenen_tutar = float(mal.fiili_odenen_tutar)+odenen; mal.save()
                    dagitilacak -= odenen
            
            messages.success(request, f"✅ Ödeme kaydedildi.")
            return redirect(f"/odeme/yap/?tedarikci_id={odeme.tedarikci.id}")
    else:
        form = OdemeForm(initial={'tarih': timezone.now().date(), 'tedarikci': secilen_tedarikci})

    return render(request, 'odeme_yap.html', {'form': form, 'tedarikciler': Tedarikci.objects.all(), 'secilen_tedarikci': secilen_tedarikci, 'acik_kalemler': acik_kalemler, 'toplam_borc': toplam_borc})

@login_required
def cari_ekstre(request, tedarikci_id):
    tedarikci = get_object_or_404(Tedarikci, id=tedarikci_id)
    hareketler = []
    for h in Hakedis.objects.filter(satinalma__teklif__tedarikci=tedarikci, onay_durumu=True):
        hareketler.append({'tarih': h.tarih, 'aciklama': f"Hakediş #{h.hakedis_no}", 'borc': h.odenecek_net_tutar, 'alacak': 0})
    for m in SatinAlma.objects.filter(teklif__tedarikci=tedarikci, teklif__malzeme__isnull=False).exclude(teslimat_durumu='bekliyor'):
        try:
            t = float(m.teslim_edilen)*float(m.teklif.birim_fiyat)*float(m.teklif.kur_degeri)
            if t>0: hareketler.append({'tarih': m.created_at.date(), 'aciklama': m.teklif.malzeme.isim, 'borc': t, 'alacak': 0})
        except: pass
    for o in Odeme.objects.filter(tedarikci=tedarikci):
        hareketler.append({'tarih': o.tarih, 'aciklama': f"Ödeme ({o.odeme_turu})", 'borc': 0, 'alacak': o.tutar})
    hareketler.sort(key=lambda x: x['tarih'])
    bakiye = 0
    for h in hareketler: bakiye += (float(h['borc'])-float(h['alacak'])); h['bakiye'] = bakiye
    return render(request, 'cari_ekstre.html', {'tedarikci': tedarikci, 'hareketler': hareketler})

@login_required
def get_tedarikci_bakiye(request, tedarikci_id):
    try:
        tedarikci = Tedarikci.objects.get(id=tedarikci_id)
        borc = sum(float(h.odenecek_net_tutar) for h in Hakedis.objects.filter(satinalma__teklif__tedarikci=tedarikci, onay_durumu=True))
        odenen = float(Odeme.objects.filter(tedarikci=tedarikci).aggregate(t=Sum('tutar'))['t'] or 0)
        return JsonResponse({'success': True, 'kalan_bakiye': round(borc-odenen, 2)})
    except Exception as e: return JsonResponse({'success': False, 'error': str(e)})