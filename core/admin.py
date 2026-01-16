from django.contrib import admin
from django.utils.safestring import mark_safe
from django.db.models import Sum
from .models import (
    Kategori, IsKalemi, Tedarikci, Teklif, SatinAlma, 
    GiderKategorisi, Harcama, Odeme, Malzeme, 
    DepoHareket, Hakedis, MalzemeTalep, Depo, DepoTransfer,
    Fatura
)
from .forms import DepoTransferForm 

# --- YARDIMCI GÖRÜNÜMLER ---

class IsKalemiInline(admin.TabularInline):
    model = IsKalemi
    extra = 1

@admin.register(Kategori)
class KategoriAdmin(admin.ModelAdmin):
    inlines = [IsKalemiInline]
    list_display = ('isim',)

@admin.register(IsKalemi)
class IsKalemiAdmin(admin.ModelAdmin):
    list_display = ('isim', 'kategori', 'birim')
    list_filter = ('kategori',)
    search_fields = ('isim',)

@admin.register(Tedarikci)
class TedarikciAdmin(admin.ModelAdmin):
    list_display = ('firma_unvani', 'yetkili', 'telefon', 'bakiye_durumu')
    search_fields = ('firma_unvani', 'yetkili')

    def bakiye_durumu(self, obj):
        # Basit bir hesaplama veya placeholder
        return "-" 
    bakiye_durumu.short_description = "Bakiye"

# --- DEPO VE MALZEME YÖNETİMİ ---

@admin.register(Depo)
class DepoAdmin(admin.ModelAdmin):
    list_display = ('isim', 'adres', 'depo_turu_goster')
    list_filter = ('tur',)
    search_fields = ('isim',) 
    
    def depo_turu_goster(self, obj):
        renk = "gray"
        ikon = "🏭"
        if obj.tur == 'merkez': 
            renk = "blue"; ikon = "🏢"
        elif obj.tur == 'baglanti': 
            renk = "purple"; ikon = "🔗"
        elif obj.tur == 'kullanim': 
            renk = "orange"; ikon = "🔨"
            
        return mark_safe(f'<span style="color:{renk}; font-weight:bold;">{ikon} {obj.get_tur_display()}</span>')
    depo_turu_goster.short_description = "Depo Türü"

@admin.register(Malzeme)
class MalzemeAdmin(admin.ModelAdmin):
    list_display = ('isim', 'marka', 'birim', 'stok_durumu', 'kritik_stok')
    search_fields = ('isim', 'marka')
    
    def stok_durumu(self, obj):
        try:
            stok = obj.stok # Modeldeki property
        except:
            stok = 0
            
        renk = "green"
        if stok <= obj.kritik_stok:
            renk = "red"
        elif stok <= obj.kritik_stok * 1.2: # %20 fazlasıysa uyar
            renk = "orange"
        
        return mark_safe(f'<span style="color:{renk}; font-weight:bold; font-size:1.1em;">{stok} {obj.get_birim_display()}</span>')
    stok_durumu.short_description = "Anlık Stok"

@admin.register(DepoTransfer)
class DepoTransferAdmin(admin.ModelAdmin):
    form = DepoTransferForm
    list_display = ('tarih', 'malzeme', 'miktar', 'kaynak_depo', 'hedef_depo')
    list_filter = ('kaynak_depo', 'hedef_depo')
    # autocomplete_fields = ['malzeme'] # Search tanımlıysa açılabilir

@admin.register(DepoHareket)
class DepoHareketAdmin(admin.ModelAdmin):
    # Yeni modelde 'tedarikci' alanı yok, o yüzden kaldırdık
    list_display = ('tarih', 'islem_turu_goster', 'depo', 'malzeme', 'miktar')
    list_filter = ('islem_turu', 'depo')
    search_fields = ('malzeme__isim', 'aciklama')
    
    def islem_turu_goster(self, obj):
        renk = "black"
        if obj.islem_turu == 'giris': renk="green"
        elif obj.islem_turu == 'cikis': renk="red"
        elif obj.islem_turu == 'transfer': renk="blue"
        return mark_safe(f'<span style="color:{renk}">{obj.get_islem_turu_display()}</span>')
    islem_turu_goster.short_description = "İşlem"

# --- TALEP YÖNETİMİ ---

@admin.register(MalzemeTalep)
class MalzemeTalepAdmin(admin.ModelAdmin):
    # 'oncelik' ve 'is_kalemi' yeni modelde yok, güncelledik
    list_display = ('malzeme', 'miktar_goster', 'talep_eden', 'durum_goster', 'tarih')
    list_filter = ('durum',)
    search_fields = ('malzeme__isim', 'aciklama')
    
    def miktar_goster(self, obj):
        return f"{obj.miktar} {obj.malzeme.get_birim_display()}"
    miktar_goster.short_description = "Miktar"

    def durum_goster(self, obj):
        ikon = "⏳"
        renk = "orange"
        if obj.durum == 'islemde': ikon = "⚙️"; renk="blue"
        if obj.durum == 'tamamlandi': ikon = "✅"; renk="green"
        if obj.durum == 'iptal': ikon = "❌"; renk="red"
        
        return mark_safe(f'<span style="color:{renk}">{ikon} {obj.get_durum_display()}</span>')
    durum_goster.short_description = "Durum"

# --- TEKLİF VE SATINALMA ---

@admin.register(Teklif)
class TeklifAdmin(admin.ModelAdmin):
    list_display = ('tedarikci', 'malzeme_veya_is', 'fiyat_goster', 'durum_goster')
    list_filter = ('durum', 'tedarikci')
    
    def malzeme_veya_is(self, obj):
        if obj.malzeme: return f"📦 {obj.malzeme.isim}"
        if obj.is_kalemi: return f"🏗️ {obj.is_kalemi.isim}"
        return "-"
    malzeme_veya_is.short_description = "Kapsam"

    def fiyat_goster(self, obj):
        return f"{obj.fiyat} {obj.para_birimi}"
    fiyat_goster.short_description = "Birim Fiyat"
    
    def durum_goster(self, obj):
        renk = "black"
        if obj.durum == 'onaylandi': renk = "green"
        if obj.durum == 'reddedildi': renk = "red"
        return mark_safe(f'<span style="color:{renk}; font-weight:bold;">{obj.get_durum_display()}</span>')
    durum_goster.short_description = "Durum"

@admin.register(SatinAlma)
class SatinAlmaAdmin(admin.ModelAdmin):
    list_display = ('teklif', 'siparis_tarihi', 'ilerleme_durumu', 'kalan_bilgisi')
    
    def ilerleme_durumu(self, obj):
        # İlerleme çubuğunu yeni veritabanına göre tekrar hesaplıyoruz
        if obj.toplam_miktar > 0:
            yuzde = (obj.teslim_edilen / obj.toplam_miktar) * 100
        else:
            yuzde = 0
            
        renk = "success" if yuzde >= 100 else ("warning" if yuzde > 0 else "danger")
        
        html = f'''
            <div style="width:100px; background:#e9ecef; border-radius:3px; height:15px; border:1px solid #ccc;">
                <div style="width:{yuzde}%; background-color:var(--bs-{renk}, {renk}); height:100%; border-radius:1px;"></div>
            </div>
            <div style="font-size:0.8em; margin-top:2px;">%{yuzde:.1f} Tamamlandı</div>
        '''
        return mark_safe(html)
    ilerleme_durumu.short_description = "Teslimat İlerlemesi"

    def kalan_bilgisi(self, obj):
        return f"{obj.kalan_miktar} Kaldı"
    kalan_bilgisi.short_description = "Kalan"

# --- FİNANS ---

@admin.register(Fatura)
class FaturaAdmin(admin.ModelAdmin):
    list_display = ('fatura_no', 'tedarikci', 'toplam_tutar_goster', 'tarih')
    list_filter = ('tedarikci',)
    
    def toplam_tutar_goster(self, obj):
        return f"{obj.toplam_tutar} {obj.para_birimi}"
    toplam_tutar_goster.short_description = "Tutar"

@admin.register(Odeme)
class OdemeAdmin(admin.ModelAdmin):
    list_display = ('tedarikci', 'tutar', 'odeme_turu', 'durum_goster', 'tarih')
    list_filter = ('odeme_turu', 'cek_durumu')
    
    def durum_goster(self, obj):
        if obj.odeme_turu == 'cek':
            return f"Çek: {obj.get_cek_durumu_display()}"
        return "Ödendi"
    durum_goster.short_description = "Durum"

@admin.register(Harcama)
class HarcamaAdmin(admin.ModelAdmin):
    list_display = ('aciklama', 'tutar', 'kategori', 'tarih')
    list_filter = ('kategori',)

@admin.register(GiderKategorisi)
class GiderKategorisiAdmin(admin.ModelAdmin):
    pass

@admin.register(Hakedis)
class HakedisAdmin(admin.ModelAdmin):
    list_display = ('sozlesme', 'hakedis_no', 'tarih', 'onaylandi', 'tutar_goster')
    
    def tutar_goster(self, obj):
        return f"{obj.odenmesi_gereken} TL"
    tutar_goster.short_description = "Ödenecek"