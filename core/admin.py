from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Kategori, IsKalemi, Tedarikci, Teklif, GiderKategorisi, Harcama, Odeme
from .utils import tcmb_kur_getir 
import json
from decimal import Decimal

# --- YARDIMCI MODELLER ---
class IsKalemiInline(admin.TabularInline):
    model = IsKalemi
    extra = 1

@admin.register(Kategori)
class KategoriAdmin(admin.ModelAdmin):
    inlines = [IsKalemiInline]

@admin.register(IsKalemi)
class IsKalemiAdmin(admin.ModelAdmin):
    list_display = ('isim', 'kategori', 'hedef_miktar', 'birim')
    list_filter = ('kategori',)
    search_fields = ('isim',)

@admin.register(Tedarikci)
class TedarikciAdmin(admin.ModelAdmin):
    list_display = ('firma_unvani', 'yetkili_kisi', 'telefon')
    search_fields = ('firma_unvani',)


# --- ORTAK YÖNLENDİRME FONKSİYONU ---
def ozel_yonlendirme(model_name, obj):
    return redirect('islem_sonuc', model_name=model_name, pk=obj.pk)


# --- TEKLİF YÖNETİMİ ---
@admin.register(Teklif)
class TeklifAdmin(admin.ModelAdmin):
    list_display = ('is_kalemi', 'tedarikci', 'birim_fiyat_goster', 'kdv_orani_goster', 'toplam_fiyat_tl_goster', 'durum')
    list_filter = ('durum', 'tedarikci', 'is_kalemi__kategori')
    list_editable = ('durum',)
    search_fields = ('is_kalemi__isim', 'tedarikci__firma_unvani')
    
    readonly_fields = ('akilli_panel', 'kur_degeri') 

    def save_model(self, request, obj, form, change):
        guncel_kurlar = tcmb_kur_getir()
        secilen_para = obj.para_birimi
        yeni_kur = guncel_kurlar.get(secilen_para, 1.0)
        obj.kur_degeri = Decimal(yeni_kur)
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        return ozel_yonlendirme('teklif', obj)

    def response_change(self, request, obj):
        return ozel_yonlendirme('teklif', obj)

    def akilli_panel(self, obj):
        try:
            kurlar = tcmb_kur_getir()
            kurlar_js = {k: float(v) for k, v in kurlar.items()}
            kurlar_js['TRY'] = 1.0
            json_kurlar = json.dumps(kurlar_js)
        except:
            json_kurlar = "{}"

        html = f"""
        <div style="background-color: #e3f2fd; border-left: 5px solid #2196f3; padding: 15px; margin-bottom: 20px; color: #0d47a1; border-radius: 4px;">
            <div style="display:flex; align-items:center;">
                <div style="font-size: 24px; margin-right: 15px;">ℹ️</div>
                <div>
                    <b>OTOMATİK KUR SİSTEMİ:</b><br>
                    Seçtiğiniz para birimine göre güncel kur <b>arka planda otomatik</b> işlenecektir.
                </div>
            </div>
        </div>

        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                const kurlar = {json_kurlar};
                const paraSelect = document.getElementById('id_para_birimi');
                const kurInput = document.querySelector('.field-kur_degeri .readonly'); 

                if (paraSelect && kurInput) {{
                    paraSelect.addEventListener('change', function() {{
                        const secilen = this.value;
                        if (kurlar[secilen]) {{
                            kurInput.innerHTML = kurlar[secilen]; 
                            kurInput.style.backgroundColor = '#d4edda';
                            setTimeout(() => {{ kurInput.style.backgroundColor = 'transparent'; }}, 600);
                        }}
                    }});
                }}
            }});
        </script>
        """
        return mark_safe(html)

    akilli_panel.short_description = "Otomatik İşlemler"

    fieldsets = (
        ('TEKLİF DETAYLARI', {
            'fields': (
                'akilli_panel',
                'is_kalemi', 
                'tedarikci', 
                ('birim_fiyat', 'para_birimi', 'kur_degeri'),
                ('kdv_dahil_mi', 'kdv_orani'),
                ('teklif_dosyasi', 'durum')
            ),
        }),
    )
    
    def birim_fiyat_goster(self, obj): return f"{obj.birim_fiyat:,.2f} {obj.para_birimi}"
    def kdv_orani_goster(self, obj): return f"%{obj.kdv_orani}"
    def toplam_fiyat_tl_goster(self, obj): return f"{obj.toplam_fiyat_tl:,.2f} ₺"


# --- GİDER YÖNETİMİ ---
@admin.register(GiderKategorisi)
class GiderKategorisiAdmin(admin.ModelAdmin):
    pass

@admin.register(Harcama)
class HarcamaAdmin(admin.ModelAdmin):
    list_display = ('aciklama', 'tutar', 'kategori', 'tarih')
    list_filter = ('kategori', 'tarih')

    def response_add(self, request, obj, post_url_continue=None):
        return ozel_yonlendirme('harcama', obj)

    def response_change(self, request, obj):
        return ozel_yonlendirme('harcama', obj)


# --- ÖDEME YÖNETİMİ (GÜNCELLENDİ: AKILLI KUR EKLENDİ) ---
@admin.register(Odeme)
class OdemeAdmin(admin.ModelAdmin):
    list_display = ('tedarikci', 'tutar', 'para_birimi', 'odeme_turu', 'tarih', 'ilgili_is_goster')
    list_filter = ('odeme_turu', 'tedarikci', 'tarih')
    search_fields = ('tedarikci__firma_unvani', 'aciklama', 'cek_numarasi')
    
    # Yeni: Kur alanı kilitli ve Akıllı Panel eklendi
    readonly_fields = ('akilli_panel', 'kur_degeri')

    # Yeni: Kaydederken güncel kuru çek
    def save_model(self, request, obj, form, change):
        guncel_kurlar = tcmb_kur_getir()
        secilen_para = obj.para_birimi
        yeni_kur = guncel_kurlar.get(secilen_para, 1.0)
        obj.kur_degeri = Decimal(yeni_kur)
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        return ozel_yonlendirme('odeme', obj)

    def response_change(self, request, obj):
        return ozel_yonlendirme('odeme', obj)

    def ilgili_is_goster(self, obj):
        if obj.ilgili_teklif:
            return f"🏗️ {obj.ilgili_teklif.is_kalemi.isim}"
        return "-"
    ilgili_is_goster.short_description = "İlgili Hakediş / İş"

    # Yeni: Akıllı Panel Scripti (Teklif ile aynı)
    def akilli_panel(self, obj):
        try:
            kurlar = tcmb_kur_getir()
            kurlar_js = {k: float(v) for k, v in kurlar.items()}
            kurlar_js['TRY'] = 1.0
            json_kurlar = json.dumps(kurlar_js)
        except:
            json_kurlar = "{}"

        html = f"""
        <div style="background-color: #e3f2fd; border-left: 5px solid #2196f3; padding: 15px; margin-bottom: 20px; color: #0d47a1; border-radius: 4px;">
            <div style="display:flex; align-items:center;">
                <div style="font-size: 24px; margin-right: 15px;">ℹ️</div>
                <div>
                    <b>OTOMATİK KUR SİSTEMİ:</b><br>
                    Ödeme yaparken seçtiğiniz para birimine göre (USD, EUR, GBP) kur otomatik çekilecektir.
                </div>
            </div>
        </div>
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                const kurlar = {json_kurlar};
                const paraSelect = document.getElementById('id_para_birimi');
                const kurInput = document.querySelector('.field-kur_degeri .readonly'); 

                if (paraSelect && kurInput) {{
                    paraSelect.addEventListener('change', function() {{
                        const secilen = this.value;
                        if (kurlar[secilen]) {{
                            kurInput.innerHTML = kurlar[secilen]; 
                            kurInput.style.backgroundColor = '#d4edda';
                            setTimeout(() => {{ kurInput.style.backgroundColor = 'transparent'; }}, 600);
                        }}
                    }});
                }}
            }});
        </script>
        """
        return mark_safe(html)

    akilli_panel.short_description = "Bilgilendirme"

    fieldsets = (
        ('ÖDEME DETAYLARI', {
            'fields': (
                'akilli_panel', # Paneli en üste koyduk
                ('tedarikci', 'tarih'),
                'ilgili_teklif', 
                ('tutar', 'para_birimi', 'kur_degeri'), # Kur'u buraya ekledik
                'odeme_turu',
                'aciklama'
            )
        }),
        ('ÇEK DETAYLARI (Sadece Çek İse)', {
            'fields': (
                ('cek_vade_tarihi', 'cek_numarasi'), 
                ('cek_banka', 'cek_sube'), 
                'cek_gorseli'
            ),
            'classes': ('collapse',), 
        }),
        ('BELGELER', {
            'fields': ('dekont',)
        }),
    )