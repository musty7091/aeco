from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import (
    Kategori, IsKalemi, Tedarikci, Teklif, GiderKategorisi, Harcama, Odeme, 
    Malzeme, DepoHareket, Hakedis, MalzemeTalep
)
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


# --- TEKLİF YÖNETİMİ (GÜNCELLENDİ) ---
@admin.register(Teklif)
class TeklifAdmin(admin.ModelAdmin):
    # GÜNCELLEME: 'toplam_fiyat_tl_goster' yerine 'toplam_fiyat_orijinal_goster' kullandık.
    list_display = ('is_kalemi', 'tedarikci', 'birim_fiyat_goster', 'kdv_orani_goster', 'toplam_fiyat_orijinal_goster', 'durum')
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

    # --- YENİ EKLENEN PARA BİRİMİ GÖSTERİMİ ---
    def toplam_fiyat_orijinal_goster(self, obj):
        # Bu fonksiyonun çalışması için models.py içinde 'toplam_fiyat_orijinal' property'si olmalıdır.
        return f"{obj.toplam_fiyat_orijinal:,.2f} {obj.para_birimi}"
    
    toplam_fiyat_orijinal_goster.short_description = "Toplam Tutar (Orijinal)"


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


# --- ÖDEME YÖNETİMİ ---
@admin.register(Odeme)
class OdemeAdmin(admin.ModelAdmin):
    list_display = ('tedarikci', 'tutar', 'para_birimi', 'odeme_turu', 'tarih', 'ilgili_is_goster')
    list_filter = ('odeme_turu', 'tedarikci', 'tarih')
    search_fields = ('tedarikci__firma_unvani', 'aciklama', 'cek_numarasi')
    
    readonly_fields = ('akilli_panel', 'kur_degeri')

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
                'akilli_panel',
                ('tedarikci', 'tarih'),
                'ilgili_teklif', 
                ('tutar', 'para_birimi', 'kur_degeri'),
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

# --- YENİ EKLENEN ŞANTİYE & DEPO MODÜLLERİ ---

@admin.register(Malzeme)
class MalzemeAdmin(admin.ModelAdmin):
    list_display = ('isim', 'birim', 'kritik_stok')
    search_fields = ('isim',)

@admin.register(DepoHareket)
class DepoHareketAdmin(admin.ModelAdmin):
    list_display = ('tarih', 'islem_turu', 'malzeme', 'miktar', 'tedarikci', 'iade_durumu_goster')
    list_filter = ('islem_turu', 'malzeme', 'tedarikci')
    search_fields = ('malzeme__isim', 'irsaliye_no', 'tedarikci__firma_unvani')
    
    def iade_durumu_goster(self, obj):
        if obj.islem_turu == 'iade':
            if obj.iade_aksiyonu == 'degisim':
                return "🔄 Değişim (Yenisi Bekleniyor)"
            elif obj.iade_aksiyonu == 'iptal':
                return "⛔ İptal (Borçtan Düşüldü)"
            return "⚠️ Aksiyon Bekliyor"
        return "-"
    iade_durumu_goster.short_description = "İade Durumu"

@admin.register(Hakedis)
class HakedisAdmin(admin.ModelAdmin):
    list_display = ('hakedis_no', 'teklif', 'donem_baslangic', 'donem_bitis', 'tamamlanma_orani', 'odenecek_goster')
    list_filter = ('onay_durumu', 'teklif__tedarikci')
    
    def odenecek_goster(self, obj):
        return f"{obj.odenecek_net_tutar:,.2f} ₺"
    odenecek_goster.short_description = "Net Ödenecek"

# --- MALZEME TALEP YÖNETİMİ ---

@admin.register(MalzemeTalep)
class MalzemeTalepAdmin(admin.ModelAdmin):
    list_display = ('tarih', 'malzeme', 'miktar_goster', 'oncelik_durumu', 'durum_goster', 'talep_eden', 'proje_yeri')
    list_filter = ('durum', 'oncelik', 'malzeme')
    search_fields = ('malzeme__isim', 'aciklama', 'proje_yeri')
    
    # -----------------------------------------------------------
    # GÜNCEL: ALANLARI KİLİTLEME MANTIĞI (READ-ONLY)
    # -----------------------------------------------------------
    def get_readonly_fields(self, request, obj=None):
        # 1. Standart Kilitler: Talep Eden ve Tarihçeler ELLE DEĞİŞTİRİLEMEZ (Sistem atar)
        readonly_fields = ['talep_eden', 'onay_tarihi', 'temin_tarihi']
        
        # Kullanıcı SAHA_EKIBI grubunda mı?
        is_saha_ekibi = request.user.groups.filter(name='SAHA_EKIBI').exists()
        
        # SENARYO 1: Yeni kayıt oluşturuluyor
        if obj is None:
            # Yeni kayıtta DURUM değiştirilemesin (Otomatik 'Bekliyor' başlasın)
            readonly_fields.append('durum')
            
        # SENARYO 2: Saha Ekibi düzenleme yapıyor
        elif is_saha_ekibi:
            # Saha ekibi durumu sonradan değiştiremez (Sadece Ofis onaylar)
            readonly_fields.append('durum')
            
        return readonly_fields
    # -----------------------------------------------------------

    def save_model(self, request, obj, form, change):
        # 1. İlk Kayıt: Talep Edeni Ata
        if not obj.pk: 
            obj.talep_eden = request.user
        
        # 2. Durum Değişikliği Kontrolü (Timeline)
        if change: # Eğer kayıt güncelleniyorsa
            try:
                eski_kayit = MalzemeTalep.objects.get(pk=obj.pk)
                
                # Durum 'Bekliyor' -> 'Onaylandı' olduysa saati bas
                if eski_kayit.durum != 'onaylandi' and obj.durum == 'onaylandi':
                    obj.onay_tarihi = timezone.now()
                
                # Durum -> 'Tamamlandı' olduysa saati bas
                if eski_kayit.durum != 'tamamlandi' and obj.durum == 'tamamlandi':
                    obj.temin_tarihi = timezone.now()
            except MalzemeTalep.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

    # --- Kaydettikten Sonra Fiş Yazdırma Ekranına Git ---
    def response_change(self, request, obj):
        if "_continue" in request.POST:
            return super().response_change(request, obj)
        return redirect('islem_sonuc', model_name='malzemetalep', pk=obj.pk)

    def response_add(self, request, obj, post_url_continue=None):
        if "_continue" in request.POST:
            return super().response_add(request, obj, post_url_continue)
        return redirect('islem_sonuc', model_name='malzemetalep', pk=obj.pk)
    # ----------------------------------------------------

    def miktar_goster(self, obj):
        return f"{obj.miktar} {obj.malzeme.get_birim_display()}"
    miktar_goster.short_description = "Miktar"

    def oncelik_durumu(self, obj):
        renk = "black"
        if obj.oncelik == 'acil': renk = "orange"
        if obj.oncelik == 'cok_acil': renk = "red"
        return mark_safe(f'<span style="color:{renk}; font-weight:bold;">{obj.get_oncelik_display()}</span>')
    oncelik_durumu.short_description = "Aciliyet"

    def durum_goster(self, obj):
        ikon = "⏳"
        if obj.durum == 'onaylandi': ikon = "✅"
        if obj.durum == 'tamamlandi': ikon = "📦"
        if obj.durum == 'red': ikon = "❌"
        return f"{ikon} {obj.get_durum_display()}"
    durum_goster.short_description = "Durum"