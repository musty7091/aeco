from django.core.management.base import BaseCommand
from core.models import (
    Depo, Malzeme, Tedarikci, Kategori, 
    DepoHareket, DepoTuru, IslemTuru, Birimler
)
import random

class Command(BaseCommand):
    help = 'Sisteme test verileri yükler (Fabrika Kurulumu)'

    def handle(self, *args, **kwargs):
        self.stdout.write('🧹 Eski/Hatalı veriler temizleniyor...')
        # Önce hareketleri sil ki ilişki hatası olmasın
        DepoHareket.objects.all().delete()
        Malzeme.objects.all().delete()
        Depo.objects.all().delete()
        Tedarikci.objects.all().delete()
        Kategori.objects.all().delete()

        self.stdout.write('🏗️ Depolar kuruluyor...')
        merkez = Depo.objects.create(isim="Ana Merkez Depo", tur=DepoTuru.MERKEZ, adres="İstanbul Lojistik Merkezi")
        santiye = Depo.objects.create(isim="Şantiye A Blok", tur=DepoTuru.KULLANIM, adres="Kadıköy Şantiye Sahası")
        baglanti = Depo.objects.create(isim="Tedarikçi Deposu", tur=DepoTuru.BAGLANTI, adres="Sanal Depo")

        self.stdout.write('📂 Kategoriler tanımlanıyor...')
        k_insaat = Kategori.objects.create(isim="Kaba İnşaat")
        k_elektrik = Kategori.objects.create(isim="Elektrik")
        k_mekanik = Kategori.objects.create(isim="Mekanik")

        self.stdout.write('🚚 Tedarikçiler ekleniyor...')
        t1 = Tedarikci.objects.create(firma_unvani="Akçansa Beton A.Ş.", yetkili="Ahmet Yılmaz", telefon="0532 100 20 30")
        t2 = Tedarikci.objects.create(firma_unvani="Öznur Kablo", yetkili="Mehmet Demir", telefon="0533 900 80 70")
        t3 = Tedarikci.objects.create(firma_unvani="Kardemir Demir Çelik", yetkili="Ayşe Kaya", telefon="0212 444 55 66")

        self.stdout.write('📦 Malzemeler ve Stoklar giriliyor...')
        
        # Malzeme 1: Beton
        m1 = Malzeme.objects.create(isim="C35 Hazır Beton", birim=Birimler.M3, marka="Akçansa", kritik_stok=100)
        # Merkeze 500 m3 giriş
        DepoHareket.objects.create(malzeme=m1, depo=merkez, islem_turu=IslemTuru.GIRIS, miktar=500, aciklama="Açılış Stoğu")
        
        # Malzeme 2: Demir
        m2 = Malzeme.objects.create(isim="Ø16 Nervürlü Demir", birim=Birimler.TON, marka="Kardemir", kritik_stok=50)
        # Merkeze 200 Ton giriş
        DepoHareket.objects.create(malzeme=m2, depo=merkez, islem_turu=IslemTuru.GIRIS, miktar=200, aciklama="Satınalma Girişi")
        # Şantiyeye 20 Ton sevk edilmiş (Stoktan düşer, kullanım deposuna girer)
        # Not: Transfer mantığıyla değil, manuel giriş simülasyonuyla yapıyoruz
        DepoHareket.objects.create(malzeme=m2, depo=merkez, islem_turu=IslemTuru.CIKIS, miktar=20, aciklama="Şantiyeye Sevk")
        DepoHareket.objects.create(malzeme=m2, depo=santiye, islem_turu=IslemTuru.GIRIS, miktar=20, aciklama="Merkezden Gelen")

        # Malzeme 3: Kablo
        m3 = Malzeme.objects.create(isim="3x2.5 NYM Kablo", birim=Birimler.MT, marka="Öznur", kritik_stok=1000)
        # Kritik Stok testi için az stok girelim
        DepoHareket.objects.create(malzeme=m3, depo=merkez, islem_turu=IslemTuru.GIRIS, miktar=800, aciklama="Kritik seviye altı test")

        self.stdout.write(self.style.SUCCESS('✅ SİSTEM HAZIR! Fabrika verileri başarıyla yüklendi.'))