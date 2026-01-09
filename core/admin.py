from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.db.models import Sum # Stok hesabı için
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


# --- TEKLİF YÖNETİMİ (HİBRİT YAPI & KİLİTLEME EKLENDİ) ---
@admin.register(Teklif)
class TeklifAdmin(admin.ModelAdmin):
    list_display = ('kalem_veya_malzeme', 'tedarikci', 'miktar', 'birim_fiyat_goster', 'toplam_fiyat_orijinal_goster', 'durum')
    list_filter = ('durum', 'tedarikci', 'is_kalemi__kategori')
    list_editable = ('durum',)
    search_fields = ('is_kalemi__isim', 'malzeme__isim', 'tedarikci__firma_unvani')
    
    readonly_fields = ('akilli_panel', 'kur_degeri', 'birim_fiyat_kdvli_goster') 

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

                // 1. KUR GÜNCELLEME SCRIPTİ
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

                // 2. İŞ KALEMİ / MALZEME KİLİTLEME (YENİ EKLENEN KISIM)
                // Django admin ID'leri: id_is_kalemi, id_malzeme
                const isKalemiSelect = document.getElementById('id_is_kalemi');
                const malzemeSelect = document.getElementById('id_malzeme');

                function toggleFields() {{
                    if (!isKalemiSelect || !malzemeSelect) return;

                    const isKalemiVal = isKalemiSelect.value;
                    const malzemeVal = malzemeSelect.value;

                    // İş Kalemi seçiliyse, Malzeme'yi kilitle
                    if (isKalemiVal) {{
                        malzemeSelect.disabled = true;
                        malzemeSelect.style.backgroundColor = '#e9ecef'; // Gri renk
                        malzemeSelect.style.cursor = 'not-allowed';
                    }} else {{
                        malzemeSelect.disabled = false;
                        malzemeSelect.style.backgroundColor = '';
                        malzemeSelect.style.cursor = 'default';
                    }}

                    // Malzeme seçiliyse, İş Kalemi'ni kilitle
                    if (malzemeVal) {{
                        isKalemiSelect.disabled = true;
                        isKalemiSelect.style.backgroundColor = '#e9ecef';
                        isKalemiSelect.style.cursor = 'not-allowed';
                    }} else {{
                        isKalemiSelect.disabled = false;
                        isKalemiSelect.style.backgroundColor = '';
                        isKalemiSelect.style.cursor = 'default';
                    }}
                }}

                if (isKalemiSelect && malzemeSelect) {{
                    // Olay dinleyicileri ekle
                    isKalemiSelect.addEventListener('change', toggleFields);
                    malzemeSelect.addEventListener('change', toggleFields);
                    
                    // Sayfa açıldığında durumu kontrol et (Edit durumu için)
                    toggleFields();
                }}
            }});
        </script>
        """
        return mark_safe(html)

    akilli_panel.short_description = "Otomatik İşlemler"

    fieldsets = (
        ('TEKLİF GİRİŞ FORMU', {
            'fields': (
                'akilli_panel',
                'is_kalemi', 
                'malzeme',
                'tedarikci',
                'miktar',
                ('birim_fiyat', 'para_birimi', 'kur_degeri'),
                'birim_fiyat_kdvli_goster',
                ('kdv_dahil_mi', 'kdv_orani'),
                ('teklif_dosyasi', 'durum')
            ),
            'description': mark_safe('<div class="alert alert-warning" role="alert"><i class="fas fa-exclamation-triangle"></i> <b>DİKKAT:</b> Lütfen ya bir <u>Taşeron İş Kalemi</u> ya da bir <u>Malzeme</u> seçiniz. İkisini birden seçmeyiniz.</div>')
        }),
    )
    
    def kalem_veya_malzeme(self, obj):
        if obj.is_kalemi:
            return f"🏗️ {obj.is_kalemi.isim}"
        elif obj.malzeme:
            return f"📦 {obj.malzeme.isim}"
        return "-"
    kalem_veya_malzeme.short_description = "Hizmet / Malzeme"

    def birim_fiyat_goster(self, obj): return f"{obj.birim_fiyat:,.2f} {obj.para_birimi}"
    def kdv_orani_goster(self, obj): return f"%{obj.kdv_orani}"
    
    def toplam_fiyat_orijinal_goster(self, obj):
        return f"{obj.toplam_fiyat_orijinal:,.2f} {obj.para_birimi}"
    toplam_fiyat_orijinal_goster.short_description = "Toplam Tutar (Orijinal)"

    def birim_fiyat_kdvli_goster(self, obj):
        if obj.pk:
            kdvli_fiyat = float(obj.birim_fiyat) * (1 + (obj.kdv_orani / 100))
            return mark_safe(f'<b style="color:#27ae60; font-size:1.1em;">{kdvli_fiyat:,.2f} {obj.para_birimi}</b> (KDV Dahil)')
        return "-"
    birim_fiyat_kdvli_goster.short_description = "Birim Fiyat (KDV DAHİL)"


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
            return str(obj.ilgili_teklif)
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

# --- ŞANTİYE & DEPO MODÜLLERİ ---

@admin.register(Malzeme)
class MalzemeAdmin(admin.ModelAdmin):
    list_display = ('isim', 'birim', 'kritik_stok', 'anlik_stok_durumu')
    search_fields = ('isim',)

    def anlik_stok_durumu(self, obj):
        stok = obj.stok 
        if stok <= obj.kritik_stok:
            return mark_safe(f'<span style="color:red; font-weight:bold;">{stok} (KRİTİK)</span>')
        elif stok <= (obj.kritik_stok * 1.5):
            return mark_safe(f'<span style="color:orange; font-weight:bold;">{stok} (Azalıyor)</span>')
        else:
            return mark_safe(f'<span style="color:green;">{stok}</span>')
    
    anlik_stok_durumu.short_description = "Anlık Stok"

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
    
    def get_readonly_fields(self, request, obj=None):
        readonly_fields = ['talep_eden', 'onay_tarihi', 'temin_tarihi']
        is_saha_ekibi = request.user.groups.filter(name='SAHA_EKIBI').exists()
        
        if obj is None:
            readonly_fields.append('durum')
        elif is_saha_ekibi:
            readonly_fields.append('durum')
            
        return readonly_fields

    def save_model(self, request, obj, form, change):
        if not obj.pk: 
            obj.talep_eden = request.user
        
        if change: 
            try:
                eski_kayit = MalzemeTalep.objects.get(pk=obj.pk)
                if eski_kayit.durum != 'onaylandi' and obj.durum == 'onaylandi':
                    obj.onay_tarihi = timezone.now()
                if eski_kayit.durum != 'tamamlandi' and obj.durum == 'tamamlandi':
                    obj.temin_tarihi = timezone.now()
            except MalzemeTalep.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

    def response_change(self, request, obj):
        if "_continue" in request.POST:
            return super().response_change(request, obj)
        return redirect('islem_sonuc', model_name='malzemetalep', pk=obj.pk)

    def response_add(self, request, obj, post_url_continue=None):
        if "_continue" in request.POST:
            return super().response_add(request, obj, post_url_continue)
        return redirect('islem_sonuc', model_name='malzemetalep', pk=obj.pk)

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