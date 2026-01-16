from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from core.models import Depo, Malzeme, DepoHareket, DepoTransfer
from core.forms import DepoTransferForm

# --- DEPO LİSTESİ ---
@login_required
def depo_listesi(request):
    depolar = Depo.objects.all().order_by('tur', 'isim')
    context = {'depolar': depolar}
    return render(request, 'depo_listesi.html', context)

# --- DEPO DETAY ---
@login_required
def depo_detay(request, depo_id):
    depo = get_object_or_404(Depo, id=depo_id)
    # Son 50 hareket (Son hareket en üstte olsun diye burada ters sıralı kalabilir veya düzeltebiliriz)
    # Kullanıcı genel geçmişte eskiden-yeniye istedi, burada son durumu görmek ister.
    hareketler = DepoHareket.objects.filter(depo=depo).order_by('-tarih')[:50]
    
    stoklar = []
    # Sadece hareketi olan malzemeleri getir
    malzemeler = Malzeme.objects.filter(hareketler__depo=depo).distinct()
    
    for m in malzemeler:
        miktar = m.depo_stogu(depo.id)
        if miktar != 0:
            stoklar.append({'malzeme': m, 'miktar': miktar})
            
    context = {'depo': depo, 'hareketler': hareketler, 'stoklar': stoklar}
    return render(request, 'stok_listesi.html', context)

# --- TRANSFER ---
@login_required
def depo_transfer(request):
    if request.method == 'POST':
        form = DepoTransferForm(request.POST)
        if form.is_valid():
            try:
                transfer = form.save()
                messages.success(request, f"{transfer.miktar} {transfer.malzeme.get_birim_display()} transfer edildi.")
                return redirect('depo_listesi')
            except Exception as e:
                messages.error(request, f"Hata: {e}")
    else:
        # URL'den gelen 'kaynak' parametresini al
        ilk_depo = request.GET.get('kaynak')
        initial_data = {}
        if ilk_depo:
            try:
                initial_data['kaynak_depo'] = Depo.objects.get(id=ilk_depo)
            except:
                pass
        form = DepoTransferForm(initial=initial_data)
    
    return render(request, 'depo_transfer.html', {'form': form})

# --- STOK GEÇMİŞİ (BAKİYELİ) ---
@login_required
def stok_hareketleri(request):
    # 1. Filtreleri Al
    secilen_malzeme_id = request.GET.get('malzeme_id', '')
    secilen_depo_id = request.GET.get('depo_id', '')
    
    # 2. Temel Sorgu: Tarihe göre ESKİDEN -> YENİYE
    hareketler = DepoHareket.objects.all().order_by('tarih', 'id')
    
    # Filtreleme
    if secilen_depo_id:
        hareketler = hareketler.filter(depo_id=secilen_depo_id)
    else:
        # Depo seçilmediyse SADECE ANA STOKLARI (Merkez+Bağlantı) getir
        # Çünkü şantiyeye giden mal envanterden düşmelidir.
        hareketler = hareketler.filter(depo__tur__in=['merkez', 'baglanti'])

    if secilen_malzeme_id:
        hareketler = hareketler.filter(malzeme_id=secilen_malzeme_id)

    # 3. BAKİYE HESABI (YÖN GARANTİLİ)
    hareket_listesi = []
    bakiye = 0
    bakiye_goster = bool(secilen_malzeme_id)

    for h in hareketler:
        # Miktarın mutlak değerini al (Örn: -20 ise 20, 20 ise 20 olur)
        miktar_mutlak = abs(h.miktar)
        degisim = 0

        # KURAL SETİ: İşlem türüne göre yön tayini
        if h.islem_turu == 'giris':
            # Giriş her zaman ARTIRIR (+)
            degisim = miktar_mutlak
            h.gorunum_sinif = "text-success"
            h.gorunum_ikon = "fa-arrow-down"
            h.islem_adi = "Giriş"
            
        elif h.islem_turu == 'cikis':
            # Çıkış her zaman AZALTIR (-)
            degisim = -miktar_mutlak
            h.gorunum_sinif = "text-danger"
            h.gorunum_ikon = "fa-arrow-up"
            h.islem_adi = "Çıkış"

        elif h.islem_turu == 'transfer':
            # Transferde veritabanındaki işarete güveniyoruz
            # (Kaynak depoda -, Hedef depoda + kayıtlıdır)
            degisim = h.miktar 
            if degisim > 0:
                h.gorunum_sinif = "text-success"
                h.gorunum_ikon = "fa-exchange-alt"
                h.islem_adi = "Transfer (Giriş)"
            else:
                h.gorunum_sinif = "text-danger"
                h.gorunum_ikon = "fa-exchange-alt"
                h.islem_adi = "Transfer (Çıkış)"

        elif h.islem_turu == 'iade':
             # İade genelde depoya geri geliştir (Giriş gibi)
             degisim = miktar_mutlak
             h.gorunum_sinif = "text-warning"
             h.gorunum_ikon = "fa-undo"
             h.islem_adi = "İade"

        # Bakiyeyi Güncelle
        bakiye += degisim
        
        # Görünüm için verileri hazırla
        h.gorunum_miktar = f"{degisim:+g}" # Başına + veya - koyar (Örn: +100, -20)
        
        # Hareket Noktası Metni
        if h.transfer:
             kaynak = h.transfer.kaynak_depo.isim
             hedef = h.transfer.hedef_depo.isim
             h.hareket_noktasi = f"{kaynak} -> {hedef}"
        elif h.islem_turu == 'giris':
             h.hareket_noktasi = f"Tedarikçi -> {h.depo.isim}"
        elif h.islem_turu == 'cikis':
             h.hareket_noktasi = f"{h.depo.isim} -> Kullanım/Proje"
        else:
             h.hareket_noktasi = "-"

        if bakiye_goster:
            h.kümülatif_bakiye = bakiye
        
        hareket_listesi.append(h)

    # Context Verileri
    depolar = Depo.objects.filter(tur__in=['merkez', 'baglanti'])
    malzemeler = Malzeme.objects.all().order_by('isim')
    
    context = {
        'hareketler': hareket_listesi,
        'depolar': depolar,
        'malzemeler': malzemeler,
        'bakiye_goster': bakiye_goster,
        'secilen_malzeme_id': int(secilen_malzeme_id) if secilen_malzeme_id else None,
        'secilen_depo_id': int(secilen_depo_id) if secilen_depo_id else None,
    }
    return render(request, 'stok_hareketleri.html', context)