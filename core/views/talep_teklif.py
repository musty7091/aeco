import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from core.models import MalzemeTalep, Malzeme, Teklif
from core.forms import TalepForm, TeklifForm


@login_required
def talep_olustur(request):
    if request.method == 'POST':
        form = TalepForm(request.POST)
        if form.is_valid():
            talep = form.save(commit=False)
            talep.talep_eden = request.user
            talep.durum = 'bekliyor'
            talep.save()
            
            messages.success(request, f"{talep.malzeme.isim} için talep oluşturuldu.")
            return redirect('dashboard')
        else:
            messages.error(request, "Formda hata var.")
    else:
        form = TalepForm()

    # EKLENEN KISIM: Malzeme ID -> Birim eşleşmesi
    # Örn: {1: 'Adet', 2: 'M3', 5: 'Kg'} gibi bir sözlük hazırlayıp sayfaya gönderiyoruz.
    birim_sozlugu = {m.id: m.get_birim_display() for m in Malzeme.objects.all()}

    context = {
        'form': form,
        'birim_json': json.dumps(birim_sozlugu) # JavaScript okusun diye JSON'a çevirdik
    }

    return render(request, 'talep_olustur.html', context)

# Talebi silme/iptal etme (Opsiyonel ama gerekli)
@login_required
def talep_sil(request, talep_id):
    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    
    # Sadece kendi talebini veya admin silebilir kuralı eklenebilir
    if talep.durum == 'bekliyor':
        talep.delete()
        messages.info(request, "Talep silindi.")
    else:
        messages.error(request, "İşleme alınmış talep silinemez!")
        
    return redirect('dashboard')

@login_required
def talep_listesi(request):
    # Talepleri tarihe göre (en yeni en üstte) sırala
    talepler = MalzemeTalep.objects.all().order_by('-tarih')
    
    # İsteğe bağlı filtreleme (Örn: ?durum=bekliyor)
    durum_filtresi = request.GET.get('durum')
    if durum_filtresi:
        talepler = talepler.filter(durum=durum_filtresi)

    context = {
        'talepler': talepler
    }
    return render(request, 'talep_listesi.html', context)

# --- TALEP DURUM DEĞİŞTİRME (ONAY/RED) ---
@login_required
def talep_durum_degistir(request, talep_id, yeni_durum):
    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    
    # Sadece geçerli durumlar
    if yeni_durum in ['islemde', 'red', 'bekliyor']:
        talep.durum = yeni_durum
        talep.save()
        
        msg = "Talep onaylandı ve işleme alındı." if yeni_durum == 'islemde' else "Talep reddedildi."
        if yeni_durum == 'bekliyor': msg = "Talep tekrar beklemeye alındı."
        
        messages.success(request, f"{talep.malzeme.isim} - {msg}")
    
    return redirect('talep_listesi')

@login_required
def teklif_yonetimi(request, talep_id):
    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    teklifler = Teklif.objects.filter(talep=talep).order_by('fiyat') # En ucuz en üstte
    
    context = {
        'talep': talep,
        'teklifler': teklifler
    }
    return render(request, 'teklif_yonetimi.html', context)

# --- YENİ TEKLİF GİR ---
@login_required
def teklif_ekle(request, talep_id):
    talep = get_object_or_404(MalzemeTalep, id=talep_id)
    
    if request.method == 'POST':
        form = TeklifForm(request.POST)
        if form.is_valid():
            teklif = form.save(commit=False)
            teklif.talep = talep 
            teklif.save()
            messages.success(request, "Fiyat teklifi kaydedildi.")
            return redirect('teklif_yonetimi', talep_id=talep.id)
    else:
        # DEĞİŞİKLİK BURADA:
        # Malzemenin kendi kartındaki 'kdv_orani' bilgisini alıp forma koyuyoruz.
        initial_data = {
            'kdv_orani': talep.malzeme.kdv_orani,  # Malzeme kartından gelen oran
            'para_birimi': 'TRY'
        }
        form = TeklifForm(initial=initial_data)

    return render(request, 'teklif_ekle.html', {
        'form': form, 
        'talep': talep
    })

@login_required
def teklif_onayla(request, teklif_id):
    secilen_teklif = get_object_or_404(Teklif, id=teklif_id)
    talep = secilen_teklif.talep
    
    # 1. Bu talebe ait diğer tüm teklifleri reddet, bunu onayla
    Teklif.objects.filter(talep=talep).update(durum='reddedildi')
    secilen_teklif.durum = 'onaylandi'
    secilen_teklif.save()
    
    # 2. Talebin durumunu 'tamamlandi' yap (Artık sipariş aşamasına geçecek)
    talep.durum = 'tamamlandi'
    talep.save()
    
    messages.success(request, f"{secilen_teklif.tedarikci} firmasından gelen teklif onaylandı! Sipariş oluşturulabilir.")
    return redirect('teklif_yonetimi', talep_id=talep.id)