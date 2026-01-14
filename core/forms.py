from django import forms
from .models import (
    DepoTransfer, Depo, Teklif, Malzeme, 
    IsKalemi, Tedarikci, MalzemeTalep, KDV_ORANLARI, Fatura
)

# ========================================================
# 1. DEPO TRANSFER FORMU
# ========================================================

class DepoTransferForm(forms.ModelForm):
    class Meta:
        model = DepoTransfer
        fields = ['kaynak_depo', 'hedef_depo', 'malzeme', 'miktar', 'aciklama', 'tarih']
        widgets = {
            'kaynak_depo': forms.Select(attrs={'class': 'form-select'}),
            'hedef_depo': forms.Select(attrs={'class': 'form-select'}),
            'malzeme': forms.Select(attrs={'class': 'form-select select2'}), # Arama yapılabilir olsun
            'miktar': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Transfer Miktarı'}),
            'aciklama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Şantiyeye Sevk'}),
            'tarih': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super(DepoTransferForm, self).__init__(*args, **kwargs)
        
        sanal_depo = Depo.objects.filter(is_sanal=True).first()
        fiziksel_depo = Depo.objects.filter(is_sanal=False).first()
        
        if sanal_depo and not self.initial.get('kaynak_depo'):
            self.fields['kaynak_depo'].initial = sanal_depo
        if fiziksel_depo and not self.initial.get('hedef_depo'):
            self.fields['hedef_depo'].initial = fiziksel_depo

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

        # Eksi Stok Kontrolü: Olmayan malı gönderemezsin
        try:
            mevcut_stok = malzeme.depo_stogu(kaynak.id)
            if mevcut_stok < miktar:
                raise forms.ValidationError(
                    f"Hata: Kaynak depoda ({kaynak.isim}) yeterli stok yok! Mevcut: {mevcut_stok}"
                )
        except AttributeError:
            pass
            
        return cleaned_data

# ========================================================
# 2. TEKLİF GİRİŞ FORMU
# ========================================================

class TeklifForm(forms.ModelForm):
    # KDV Seçimi: Varsayılan (initial) kaldırıldı, 'Seçiniz' eklendi.
    kdv_orani_secimi = forms.ChoiceField(
        choices=[('', 'Seçiniz...')] + list(KDV_ORANLARI), 
        label="KDV Oranı", 
        required=True, # Kullanıcı seçim yapmak zorunda
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Teklif
        fields = [
            'tedarikci', 
            'malzeme', 'is_kalemi',
            'miktar', 'birim_fiyat', 'para_birimi', 
            'kdv_dahil_mi', 'teklif_dosyasi'
        ]
        
        widgets = {
            'tedarikci': forms.Select(attrs={'class': 'form-select select2'}),
            'malzeme': forms.Select(attrs={'class': 'form-select'}),
            'is_kalemi': forms.Select(attrs={'class': 'form-select'}),
            'miktar': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Miktar giriniz'}),
            'birim_fiyat': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'para_birimi': forms.Select(attrs={'class': 'form-select'}),
            'kdv_dahil_mi': forms.CheckboxInput(attrs={'class': 'form-check-input', 'style': 'width: 20px; height: 20px;'}),
            'teklif_dosyasi': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        malzeme = cleaned_data.get('malzeme')
        is_kalemi = cleaned_data.get('is_kalemi')

        if not malzeme and not is_kalemi:
            raise forms.ValidationError("Lütfen ya bir Malzeme ya da bir İş Kalemi seçiniz.")
        if malzeme and is_kalemi:
            raise forms.ValidationError("Hem malzeme hem hizmet seçemezsiniz. Sadece birini seçin.")
        return cleaned_data

# ========================================================
# 3. TANIMLAMA FORMLARI
# ========================================================

class TedarikciForm(forms.ModelForm):
    class Meta:
        model = Tedarikci
        fields = ['firma_unvani', 'yetkili_kisi', 'telefon', 'adres']
        widgets = {
            'firma_unvani': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: ABC İnşaat Ltd. Şti.'}),
            'yetkili_kisi': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ad Soyad'}),
            'telefon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '05XX XXX XX XX'}),
            'adres': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class MalzemeForm(forms.ModelForm):
    class Meta:
        model = Malzeme
        fields = ['kategori', 'isim', 'marka', 'birim', 'kdv_orani', 'kritik_stok', 'aciklama']
        widgets = {
            'kategori': forms.Select(attrs={'class': 'form-select'}),
            'isim': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Saten Alçı'}),
            'marka': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Knauf'}),
            'birim': forms.Select(attrs={'class': 'form-select'}),
            'kdv_orani': forms.Select(attrs={'class': 'form-select'}),
            'kritik_stok': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '10'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Varsa ölçü, renk veya teknik kod...'}),
        }

# ========================================================
# 4. TALEP FORMLARI
# ========================================================

class TalepForm(forms.ModelForm):
    class Meta:
        model = MalzemeTalep
        fields = ['malzeme', 'is_kalemi', 'miktar', 'oncelik', 'proje_yeri', 'aciklama']
        
        widgets = {
            'malzeme': forms.Select(attrs={'class': 'form-select select2'}),
            'is_kalemi': forms.Select(attrs={'class': 'form-select select2'}), 
            'miktar': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Örn: 100'}),
            'oncelik': forms.Select(attrs={'class': 'form-select'}),
            'proje_yeri': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: A Blok - 1. Kat'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        malzeme = cleaned_data.get('malzeme')
        is_kalemi = cleaned_data.get('is_kalemi')

        if not malzeme and not is_kalemi:
            raise forms.ValidationError("Lütfen Malzeme veya İş Kalemi alanlarından birini seçiniz.")
        if malzeme and is_kalemi:
            raise forms.ValidationError("İkisini aynı anda seçemezsiniz.")
        
        return cleaned_data

class IsKalemiForm(forms.ModelForm):
    class Meta:
        model = IsKalemi
        fields = ['kategori', 'isim', 'birim', 'hedef_miktar', 'kdv_orani', 'aciklama']
        widgets = {
            'kategori': forms.Select(attrs={'class': 'form-select'}),
            'isim': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Temel Kazısı'}),
            'birim': forms.Select(attrs={'class': 'form-select'}),
            'hedef_miktar': forms.NumberInput(attrs={'class': 'form-control'}),
            'kdv_orani': forms.Select(attrs={'class': 'form-select'}),
            'aciklama': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Yapılacak işin detayı...'}),
        }

class FaturaGirisForm(forms.ModelForm):
    class Meta:
        model = Fatura
        fields = ['fatura_no', 'tarih', 'depo', 'miktar', 'tutar', 'dosya']
        widgets = {
            'fatura_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Fatura No'}),
            'tarih': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'depo': forms.Select(attrs={'class': 'form-select'}),
            'miktar': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tutar': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'dosya': forms.FileInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super(FaturaGirisForm, self).__init__(*args, **kwargs)
        # Depo seçimi ZORUNLU. Fatura girildiği an stok oluşacak.
        self.fields['depo'].required = True
        self.fields['depo'].empty_label = "Depo Seçiniz (Zorunlu)"