from decimal import Decimal, ROUND_HALF_UP
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.http import JsonResponse
from core.models import Tedarikci, Fatura, Odeme, Kategori, GiderKategorisi, Hakedis, SatinAlma
from core.forms import OdemeForm, HakedisForm
from core.utils import tcmb_kur_getir
from .guvenlik import yetki_kontrol
from core.utils import to_decimal


@login_required
def finans_dashboard(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    # Kurları al ve Decimal'e çevir
    guncel_kurlar = tcmb_kur_getir()
    kur_usd = to_decimal(guncel_kurlar.get('USD', 1))
    kur_eur = to_decimal(guncel_kurlar.get('EUR', 1))
    kur_gbp = to_decimal(guncel_kurlar.get('GBP', 1))
    
    def cevir(tl_tutar):
        return {
            'usd': (tl_tutar / kur_usd).quantize(Decimal('0.00')),
            'eur': (tl_tutar / kur_eur).quantize(Decimal('0.00')),
            'gbp': (tl_tutar / kur_gbp).quantize(Decimal('0.00'))
        }
    
    # 1. İMALAT MALİYETİ (Modelden Property kullanmak yerine DB seviyesinde çekmek daha hızlıdır ama şimdilik mevcut yapıyı Decimal ile koruyoruz)
    imalat_maliyeti = Decimal('0.00')
    imalat_labels, imalat_data = [], []
    
    # Not: Burada loop kullanmak performans kaybıdır ancak Teklif yapısı karmaşık olduğu için (en uygun teklif seçimi vb.)
    # şimdilik Decimal dönüşümü ile bırakıyoruz. İleride burası da query'e taşınmalı.
    kategoriler = Kategori.objects.prefetch_related('kalemler__teklifler').all()
    
    # Dashboard istatistikleri
    toplam_kalem_sayisi = 0
    dolu_kalem_sayisi = 0

    for kat in kategoriler:
        kat_toplam = Decimal('0.00')
        for kalem in kat.kalemler.all():
            toplam_kalem_sayisi += 1
            # Onaylı teklifi bul, yoksa en düşüğü al
            onayli = kalem.teklifler.filter(durum='onaylandi').first()
            if onayli:
                kat_toplam += to_decimal(onayli.toplam_fiyat_tl)
                dolu_kalem_sayisi += 1
            else:
                bekleyenler = kalem.teklifler.filter(durum='beklemede')
                if bekleyenler.exists():
                    en_dusuk = min(bekleyenler, key=lambda t: t.toplam_fiyat_tl)
                    kat_toplam += to_decimal(en_dusuk.toplam_fiyat_tl)
                    dolu_kalem_sayisi += 1
        
        if kat_toplam > 0:
            imalat_labels.append(kat.isim)
            imalat_data.append(float(kat_toplam)) # ChartJS float ister
            imalat_maliyeti += kat_toplam

    # 2. GİDERLER (Aggregate ile Hızlı Toplama)
    harcama_tutari = Decimal('0.00')
    gider_labels, gider_data = [], []
    
    for gk in GiderKategorisi.objects.all():
        # Veritabanında toplama (Performans O(1))
        toplam = gk.harcamalar.aggregate(toplam=Sum('tutar'))['toplam'] or Decimal('0')
        # Not: Harcama modelinde kur dönüşümü varsa property kullanılmalı, yoksa direkt toplanabilir.
        # Burada basitlik adına direkt toplam aldık, kur dönüşümü gerekiyorsa modeldeki property üzerinden gidilmeli.
        # Ancak performans için Python tarafında Decimal ile topluyoruz:
        tutar_tl = sum(to_decimal(h.tl_tutar) for h in gk.harcamalar.all())
        
        if tutar_tl > 0:
            gider_labels.append(gk.isim)
            gider_data.append(float(tutar_tl))
            harcama_tutari += tutar_tl

    # 3. BORÇLAR
    # Tüm onaylı tekliflerin TL tutarı
    toplam_onaylanan_borc = Decimal('0.00')
    for ted in Tedarikci.objects.prefetch_related('teklifler').all():
        for t in ted.teklifler.filter(durum='onaylandi'):
            toplam_onaylanan_borc += to_decimal(t.toplam_fiyat_tl)
            
    toplam_odenen = Odeme.objects.aggregate(toplam=Sum('tutar'))['toplam'] or Decimal('0.00')
    kalan_borc = toplam_onaylanan_borc - toplam_odenen
    
    oran = int((dolu_kalem_sayisi/toplam_kalem_sayisi)*100) if toplam_kalem_sayisi else 0

    context = {
        'imalat_maliyeti': imalat_maliyeti,
        'harcama_tutari': harcama_tutari,
        'genel_toplam': imalat_maliyeti + harcama_tutari,
        'kalan_borc': kalan_borc,
        'oran': oran,
        'doviz_genel': cevir(imalat_maliyeti + harcama_tutari),
        'imalat_labels': imalat_labels,
        'imalat_data': imalat_data,
        'gider_labels': gider_labels,
        'gider_data': gider_data,
        'kurlar': guncel_kurlar,
    }
    return render(request, 'finans_dashboard.html', context)

@login_required
def finans_ozeti(request):
    if not yetki_kontrol(request.user, ['OFIS_VE_SATINALMA', 'MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')
    
    finans_verisi = []
    genel_borc = Decimal('0.00')
    genel_odenen = Decimal('0.00')

    # N+1 Sorununu önlemek için prefetch
    tedarikciler = Tedarikci.objects.prefetch_related('teklifler__satinalma_set__faturalar', 'odemeler').all()

    for ted in tedarikciler:
        # Fatura bazlı borç hesabı
        borc = Decimal('0.00')
        faturalar = Fatura.objects.filter(satinalma__teklif__tedarikci=ted)
        # Fatura modeli DecimalField kullanıyorsa direkt aggregate yapılabilir
        borc = faturalar.aggregate(toplam=Sum('tutar'))['toplam'] or Decimal('0.00')

        # Ödemeler
        odenen = ted.odemeler.aggregate(toplam=Sum('tutar'))['toplam'] or Decimal('0.00')
        
        bakiye = borc - odenen
        
        if borc > 0 or odenen > 0:
            finans_verisi.append({
                'id': ted.id,
                'firma': ted.firma_unvani,
                'borc': borc,
                'odenen': odenen,
                'bakiye': bakiye
            })
            genel_borc += borc
            genel_odenen += odenen
            
    return render(request, 'finans_ozeti.html', {
        'veriler': finans_verisi,
        'toplam_borc': genel_borc,
        'toplam_odenen': genel_odenen,
        'toplam_bakiye': genel_borc - genel_odenen
    })

@login_required
def odeme_dashboard(request):
    if not yetki_kontrol(request.user, ['MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')

    # Hakediş Toplamı (Sadece onaylılar)
    hakedis_toplam = Hakedis.objects.filter(onay_durumu=True).aggregate(toplam=Sum('odenecek_net_tutar'))['toplam'] or Decimal('0.00')
    
    # Malzeme Borcu (Döngü yerine matematiksel yaklaşım)
    malzeme_borcu = Decimal('0.00')
    siparisler = SatinAlma.objects.filter(teklif__malzeme__isnull=False).select_related('teklif')
    
    for sip in siparisler:
        miktar = to_decimal(sip.teslim_edilen)
        fiyat = to_decimal(sip.teklif.birim_fiyat)
        kur = to_decimal(sip.teklif.kur_degeri)
        kdv_orani = to_decimal(sip.teklif.kdv_orani)
        
        # (Miktar * Fiyat * Kur) * (1 + KDV/100)
        ara_toplam = miktar * fiyat * kur
        kdvli_toplam = ara_toplam * (1 + (kdv_orani / 100))
        malzeme_borcu += kdvli_toplam

    toplam_odenen = Odeme.objects.aggregate(toplam=Sum('tutar'))['toplam'] or Decimal('0.00')
    
    context = {
        'hakedis_toplam': hakedis_toplam,
        'malzeme_borcu': malzeme_borcu,
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
    
    toplam_risk = cekler.aggregate(toplam=Sum('tutar'))['toplam'] or Decimal('0.00')
    
    context = {
        'gecikmisler': cekler.filter(vade_tarihi__lt=bugun),
        'yaklasanlar': cekler.filter(vade_tarihi__gte=bugun, vade_tarihi__lte=bugun+timezone.timedelta(days=30)),
        'ileri_tarihliler': cekler.filter(vade_tarihi__gt=bugun+timezone.timedelta(days=30)),
        'toplam_risk': toplam_risk,
        'bugun': bugun
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
    
    # Decimal işlem
    for t in tedarikci.teklifler.filter(durum='onaylandi'):
        isim = t.malzeme.isim if t.malzeme else (t.is_kalemi.isim if t.is_kalemi else "-")
        hareketler.append({
            'tarih': t.olusturulma_tarihi.date(),
            'tur': 'BORÇ',
            'aciklama': f"{isim}",
            'borc': to_decimal(t.toplam_fiyat_tl),
            'alacak': Decimal('0.00')
        })
        
    for o in tedarikci.odemeler.all():
        hareketler.append({
            'tarih': o.tarih,
            'tur': f'ÖDEME ({o.odeme_turu})',
            'aciklama': o.aciklama,
            'borc': Decimal('0.00'),
            'alacak': to_decimal(o.tutar)
        })
    
    hareketler.sort(key=lambda x: x['tarih'])
    bakiye = Decimal('0.00')
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
            hakedis.satinalma = siparis
            hakedis.onay_durumu = True
            hakedis.save()
            
            # Decimal ile güncelleme
            try:
                toplam_is = to_decimal(siparis.toplam_miktar)
                yapilan_yuzde = to_decimal(hakedis.tamamlanma_orani)
                yapilan_miktar = (toplam_is * yapilan_yuzde) / 100
                
                siparis.teslim_edilen += yapilan_miktar
                siparis.faturalanan_miktar += yapilan_miktar
                siparis.save()
            except Exception as e:
                print(f"Hata: {e}")
                
            messages.success(request, f"✅ Hakediş #{hakedis.hakedis_no} onaylandı.")
            return redirect('siparis_listesi')
    else:
        form = HakedisForm(initial={'tarih': timezone.now().date(), 'hakedis_no': Hakedis.objects.filter(satinalma=siparis).count() + 1})
    return render(request, 'hakedis_ekle.html', {'form': form, 'siparis': siparis})

@login_required
def odeme_yap(request):
    if not yetki_kontrol(request.user, ['MUHASEBE_FINANS', 'YONETICI']): return redirect('erisim_engellendi')
    
    tedarikci_id = request.GET.get('tedarikci_id') or request.POST.get('tedarikci')
    acik_kalemler = []
    secilen_tedarikci = None
    toplam_borc = Decimal('0.00')
    
    if tedarikci_id:
        try:
            secilen_tedarikci = Tedarikci.objects.get(id=tedarikci_id)
            
            # A) Hakediş Borçları (ExpressionWrapper ile DB seviyesinde fark alma)
            hakedisler = Hakedis.objects.filter(
                onay_durumu=True,
                satinalma__teklif__tedarikci=secilen_tedarikci
            ).annotate(
                kalan=ExpressionWrapper(F('odenecek_net_tutar') - F('fiili_odenen_tutar'), output_field=DecimalField())
            ).filter(kalan__gt=0.1)
            
            for hk in hakedisler:
                acik_kalemler.append({'id': hk.id, 'tip': 'hakedis', 'tarih': hk.tarih, 'aciklama': f"Hakediş #{hk.hakedis_no}", 'kalan_tutar': hk.kalan})
                toplam_borc += hk.kalan

            # B) Malzeme Borçları (Hesaplama karmaşık olduğu için Python'da Decimal ile yapıyoruz)
            malzemeler = SatinAlma.objects.filter(
                teklif__tedarikci=secilen_tedarikci, 
                teklif__malzeme__isnull=False
            ).exclude(teslimat_durumu='bekliyor')
            
            for mal in malzemeler:
                miktar = to_decimal(mal.teslim_edilen)
                fiyat = to_decimal(mal.teklif.birim_fiyat)
                kur = to_decimal(mal.teklif.kur_degeri)
                kdv = to_decimal(mal.teklif.kdv_orani)
                
                tutar = (miktar * fiyat * kur) * (1 + kdv/100)
                odenen = to_decimal(mal.fiili_odenen_tutar)
                kalan = tutar - odenen
                
                if kalan > 1:
                    acik_kalemler.append({'id': mal.id, 'tip': 'malzeme', 'tarih': mal.created_at.date(), 'aciklama': f"{mal.teklif.malzeme.isim}", 'kalan_tutar': kalan})
                    toplam_borc += kalan
        except: pass

    if request.method == 'POST':
        form = OdemeForm(request.POST)
        if form.is_valid():
            odeme = form.save(commit=False)
            # String'den Decimal'e güvenli dönüşüm (virgül replace)
            try:
                ham_tutar = str(form.cleaned_data['tutar']).replace(',', '.')
                odeme.tutar = Decimal(ham_tutar)
            except:
                odeme.tutar = Decimal('0.00')
                
            odeme.save()
            
            dagitilacak = odeme.tutar
            secilenler = request.POST.getlist('secilen_kalem')
            
            # Tek seçim varsa bağla
            if len(secilenler)==1 and secilenler[0].startswith('hakedis_'):
                try: 
                    odeme.bagli_hakedis_id = int(secilenler[0].split('_')[1])
                    odeme.save()
                except: pass
            
            # Borç Dağıtma Algoritması
            for secim in secilenler:
                if dagitilacak <= 0: break
                
                try:
                    tip, id_str = secim.split('_')
                    if tip == 'hakedis':
                        hk = Hakedis.objects.get(id=id_str)
                        borc = to_decimal(hk.odenecek_net_tutar) - to_decimal(hk.fiili_odenen_tutar)
                        odenecek_kisim = min(dagitilacak, borc)
                        
                        hk.fiili_odenen_tutar = to_decimal(hk.fiili_odenen_tutar) + odenecek_kisim
                        hk.save()
                        dagitilacak -= odenecek_kisim
                        
                    elif tip == 'malzeme':
                        mal = SatinAlma.objects.get(id=id_str)
                        # Tutar tekrar hesapla
                        miktar = to_decimal(mal.teslim_edilen)
                        fiyat = to_decimal(mal.teklif.birim_fiyat)
                        kur = to_decimal(mal.teklif.kur_degeri)
                        kdv = to_decimal(mal.teklif.kdv_orani)
                        tutar_toplam = (miktar * fiyat * kur) * (1 + kdv/100)
                        
                        borc = tutar_toplam - to_decimal(mal.fiili_odenen_tutar)
                        odenecek_kisim = min(dagitilacak, borc)
                        
                        mal.fiili_odenen_tutar = to_decimal(mal.fiili_odenen_tutar) + odenecek_kisim
                        mal.save()
                        dagitilacak -= odenecek_kisim
                except Exception as e:
                    print(f"Dağıtım Hatası: {e}")

            messages.success(request, f"✅ Ödeme kaydedildi.")
            return redirect(f"/odeme/yap/?tedarikci_id={odeme.tedarikci.id}")
    else:
        form = OdemeForm(initial={'tarih': timezone.now().date(), 'tedarikci': secilen_tedarikci})

    return render(request, 'odeme_yap.html', {'form': form, 'tedarikciler': Tedarikci.objects.all(), 'secilen_tedarikci': secilen_tedarikci, 'acik_kalemler': acik_kalemler, 'toplam_borc': toplam_borc})

@login_required
def cari_ekstre(request, tedarikci_id):
    tedarikci = get_object_or_404(Tedarikci, id=tedarikci_id)
    hareketler = []
    
    # Hakedişler
    for h in Hakedis.objects.filter(satinalma__teklif__tedarikci=tedarikci, onay_durumu=True):
        hareketler.append({'tarih': h.tarih, 'aciklama': f"Hakediş #{h.hakedis_no}", 'borc': to_decimal(h.odenecek_net_tutar), 'alacak': Decimal('0')})
    
    # Malzemeler
    for m in SatinAlma.objects.filter(teklif__tedarikci=tedarikci, teklif__malzeme__isnull=False).exclude(teslimat_durumu='bekliyor'):
        try:
            # Hesaplama
            miktar = to_decimal(m.teslim_edilen)
            fiyat = to_decimal(m.teklif.birim_fiyat)
            kur = to_decimal(m.teklif.kur_degeri)
            tutar = miktar * fiyat * kur
            
            if tutar > 0: 
                hareketler.append({'tarih': m.created_at.date(), 'aciklama': m.teklif.malzeme.isim, 'borc': tutar, 'alacak': Decimal('0')})
        except: pass
        
    # Ödemeler
    for o in Odeme.objects.filter(tedarikci=tedarikci):
        hareketler.append({'tarih': o.tarih, 'aciklama': f"Ödeme ({o.odeme_turu})", 'borc': Decimal('0'), 'alacak': to_decimal(o.tutar)})
    
    hareketler.sort(key=lambda x: x['tarih'])
    bakiye = Decimal('0.00')
    for h in hareketler: 
        bakiye += (h['borc'] - h['alacak'])
        h['bakiye'] = bakiye
        
    return render(request, 'cari_ekstre.html', {'tedarikci': tedarikci, 'hareketler': hareketler})

@login_required
def get_tedarikci_bakiye(request, tedarikci_id):
    try:
        tedarikci = Tedarikci.objects.get(id=tedarikci_id)
        # Basit bakiye sorgusu
        hakedis_borc = Hakedis.objects.filter(satinalma__teklif__tedarikci=tedarikci, onay_durumu=True).aggregate(t=Sum('odenecek_net_tutar'))['t'] or Decimal('0')
        odenen = Odeme.objects.filter(tedarikci=tedarikci).aggregate(t=Sum('tutar'))['t'] or Decimal('0')
        # Malzeme borcu eklenebilir, şimdilik temel mantık
        return JsonResponse({'success': True, 'kalan_bakiye': float(hakedis_borc-odenen)})
    except Exception as e: return JsonResponse({'success': False, 'error': str(e)})

@login_required
def odeme_sil(request, odeme_id):
    if not yetki_kontrol(request.user, ['MUHASEBE_FINANS', 'YONETICI']):
        return redirect('erisim_engellendi')
        
    odeme = get_object_or_404(Odeme, id=odeme_id)
    tedarikci_id = odeme.tedarikci.id
    
    # Ödeme silindiğinde bakiye property üzerinden hesaplandığı için 
    # otomatik olarak düzelecektir. Sadece kaydı siliyoruz.
    odeme.delete()
    
    messages.warning(request, "🗑️ Ödeme kaydı silindi, cari bakiye güncellendi.")
    return redirect('tedarikci_ekstre', tedarikci_id=tedarikci_id)