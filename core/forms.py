from django import forms
from decimal import Decimal
from .models import (
    Depo, DepoTransfer, Teklif, Malzeme, IsKalemi,
    Tedarikci, MalzemeTalep, Fatura, Hakedis, Odeme,
    Kategori, DepoTuru, ParaBirimi, Birimler,
    KDV_ORANLARI
)

# ========================================================
# 1. TANIMLAMA FORMLARI
# ========================================================

class KategoriForm(forms.ModelForm):
    class Meta:
        model = Kategori
        fields = ['isim']
        widgets = {
            'isim': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Kaba İnşaat'}),
        }

class DepoForm(forms.ModelForm):
    class Meta:
        model = Depo
        fields = ['isim', 'tur', 'adres']
        widgets = {
            'isim': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Depo Adı'}),
            'tur': forms.Select(attrs={'class': 'form-select'}),
            'adres': forms.TextInput(attrs={'class': 'form-control'}),
        }

class TedarikciForm(forms.ModelForm):
    class Meta:
        model = Tedarikci
        fields = ['firma_unvani', 'yetkili', 'telefon']
        widgets = {
            'firma_unvani': forms.TextInput(attrs={'class': 'form-control'}),
            'yetkili': forms.TextInput(attrs={'class': 'form-control'}),
            'telefon': forms.TextInput(attrs={'class': 'form-control'}),
        }

class MalzemeForm(forms.ModelForm):
    class Meta:
        model = Malzeme
        # 'kdv_orani' alanını buraya ekliyoruz:
        fields = ['isim', 'marka', 'birim', 'kritik_stok', 'kdv_orani']
        widgets = {
            'isim': forms.TextInput(attrs={'class': 'form-control'}),
            'marka': forms.TextInput(attrs={'class': 'form-control'}),
            'birim': forms.Select(attrs={'class': 'form-select'}),
            'kritik_stok': forms.NumberInput(attrs={'class': 'form-control'}),
            # KDV seçimi için açılır kutu:
            'kdv_orani': forms.Select(attrs={'class': 'form-select'}),
        }

class IsKalemiForm(forms.ModelForm):
    class Meta:
        model = IsKalemi
        fields = ['kategori', 'isim', 'birim', 'aciklama']
        widgets = {
            'kategori': forms.Select(attrs={'class': 'form-select'}),
            'isim': forms.TextInput(attrs={'class': 'form-control'}),
            'birim': forms.Select(attrs={'class': 'form-select'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

# ========================================================
# 2. DEPO TRANSFER FORMU
# ========================================================

class DepoTransferForm(forms.ModelForm):
    class Meta:
        model = DepoTransfer
        fields = ['kaynak_depo', 'hedef_depo', 'malzeme', 'miktar', 'aciklama', 'tarih']
        widgets = {
            'kaynak_depo': forms.Select(attrs={'class': 'form-select'}),
            'hedef_depo': forms.Select(attrs={'class': 'form-select'}),
            'malzeme': forms.Select(attrs={'class': 'form-select select2'}),
            'miktar': forms.NumberInput(attrs={'class': 'form-control'}),
            'aciklama': forms.TextInput(attrs={'class': 'form-control'}),
            'tarih': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super(DepoTransferForm, self).__init__(*args, **kwargs)
        # Otomatik Seçim Mantığı (Merkez -> Şantiye gibi)
        try:
            merkez = Depo.objects.filter(tur=DepoTuru.MERKEZ).first()
            santiye = Depo.objects.filter(tur=DepoTuru.KULLANIM).first()
            
            if merkez and not self.initial.get('kaynak_depo'):
                self.fields['kaynak_depo'].initial = merkez
            if santiye and not self.initial.get('hedef_depo'):
                self.fields['hedef_depo'].initial = santiye
        except:
            pass

    def clean(self):
        cleaned_data = super().clean()
        kaynak = cleaned_data.get('kaynak_depo')
        hedef = cleaned_data.get('hedef_depo')
        malzeme = cleaned_data.get('malzeme')
        miktar = cleaned_data.get('miktar')

        if not (kaynak and hedef and malzeme and miktar):
            return cleaned_data

        if kaynak == hedef:
            raise forms.ValidationError("Kaynak ve Hedef depo aynı olamaz.")

        # Stok Kontrolü
        stok = malzeme.depo_stogu(kaynak.id)
        if stok < miktar:
            raise forms.ValidationError(f"Yetersiz Stok! {kaynak.isim} deposunda sadece {stok} adet var.")
            
        return cleaned_data

# ========================================================
# 3. TALEP VE TEKLİF FORMLARI
# ========================================================

class TalepForm(forms.ModelForm):
    class Meta:
        model = MalzemeTalep
        fields = ['malzeme', 'miktar', 'proje_yeri', 'aciklama']
        widgets = {
            'malzeme': forms.Select(attrs={'class': 'form-select select2'}),
            'miktar': forms.NumberInput(attrs={'class': 'form-control'}),
            'proje_yeri': forms.TextInput(attrs={'class': 'form-control'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class TeklifForm(forms.ModelForm):
    class Meta:
        model = Teklif
        fields = ['tedarikci', 'fiyat', 'para_birimi', 'kdv_orani', 'kdv_dahil_mi']
        widgets = {
            'tedarikci': forms.Select(attrs={'class': 'form-select form-select-lg'}), # Büyük seçim kutusu
            'fiyat': forms.NumberInput(attrs={'class': 'form-control form-control-lg', 'placeholder': '0.00', 'oninput': 'hesapla()'}),
            'para_birimi': forms.Select(attrs={'class': 'form-select', 'onchange': 'kurKontrol()'}),
            'kdv_orani': forms.Select(attrs={'class': 'form-select', 'onchange': 'hesapla()'}),
            'kdv_dahil_mi': forms.CheckboxInput(attrs={'class': 'form-check-input', 'onchange': 'hesapla()', 'style': 'transform: scale(1.5); margin-left: 10px;'}),
        }

# ========================================================
# 4. FİNANSAL FORMLAR
# ========================================================

class FaturaGirisForm(forms.ModelForm):
    class Meta:
        model = Fatura
        fields = [
            'fatura_no', 'tedarikci', 'tarih', 'son_odeme_tarihi',
            'tutar_kdv_haric', 'kdv_tutari', 'toplam_tutar',
            'para_birimi', 'dosya'
        ]
        widgets = {
            'fatura_no': forms.TextInput(attrs={'class': 'form-control'}),
            'tedarikci': forms.Select(attrs={'class': 'form-select'}),
            'tarih': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'son_odeme_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tutar_kdv_haric': forms.NumberInput(attrs={'class': 'form-control'}),
            'kdv_tutari': forms.NumberInput(attrs={'class': 'form-control'}),
            'toplam_tutar': forms.NumberInput(attrs={'class': 'form-control'}),
            'para_birimi': forms.Select(attrs={'class': 'form-select'}),
            'dosya': forms.FileInput(attrs={'class': 'form-control'}),
        }

class HakedisForm(forms.ModelForm):
    class Meta:
        model = Hakedis
        fields = ['bu_donem_yuzde', 'hakedis_tutari', 'kesintiler_toplami', 'tarih']
        widgets = {
            'bu_donem_yuzde': forms.NumberInput(attrs={'class': 'form-control'}),
            'hakedis_tutari': forms.NumberInput(attrs={'class': 'form-control'}),
            'kesintiler_toplami': forms.NumberInput(attrs={'class': 'form-control'}),
            'tarih': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

class OdemeForm(forms.ModelForm):
    # String olarak alıp Decimal'e çevirmek için
    tutar = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Odeme
        fields = [
            'tedarikci', 'tarih', 'odeme_turu', 'tutar', 'para_birimi',
            'banka_adi', 'cek_no', 'vade_tarihi', 'aciklama'
        ]
        widgets = {
            'tedarikci': forms.Select(attrs={'class': 'form-select'}),
            'tarih': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'odeme_turu': forms.Select(attrs={'class': 'form-select'}),
            'para_birimi': forms.Select(attrs={'class': 'form-select'}),
            'banka_adi': forms.TextInput(attrs={'class': 'form-control'}),
            'cek_no': forms.TextInput(attrs={'class': 'form-control'}),
            'vade_tarihi': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'aciklama': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_tutar(self):
        data = self.cleaned_data['tutar']
        if isinstance(data, str):
            data = data.replace(',', '.')
        try:
            return Decimal(data)
        except:
            raise forms.ValidationError("Geçerli bir sayı giriniz.")