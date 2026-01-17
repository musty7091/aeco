from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views as core_views # Import ismini 'core_views' yaptık

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # 1. Ana Karşılama
    path('', core_views.dashboard, name='dashboard'),
    path('erisim-engellendi/', core_views.erisim_engellendi, name='erisim_engellendi'),

    # 2. Modüller (İcmal & Teklif)
    path('icmal/', core_views.icmal_raporu, name='icmal_raporu'),
    path('teklif/ekle/', core_views.teklif_ekle, name='teklif_ekle'),
    
    # 3. Dashboardlar
    path('finans-dashboard/', core_views.finans_dashboard, name='finans_dashboard'),
    path('depo-dashboard/', core_views.depo_dashboard, name='depo_dashboard'),
    path('odeme-dashboard/', core_views.odeme_dashboard, name='odeme_dashboard'),
    
    # 4. Detaylar
    path('finans/detay-ozet/', core_views.finans_ozeti, name='finans_ozeti'),
    path('cek-takibi/', core_views.cek_takibi, name='cek_takibi'),
    
    # 5. İşlemler (Finans & Teklif)
    path('cek-durum/<int:odeme_id>/', core_views.cek_durum_degistir, name='cek_durum_degistir'),
    path('tedarikci/<int:tedarikci_id>/', core_views.tedarikci_ekstresi, name='tedarikci_ekstresi'),
    path('teklif/durum/<int:teklif_id>/<str:yeni_durum>/', core_views.teklif_durum_guncelle, name='teklif_durum_guncelle'),
    path('odeme/sil/<int:odeme_id>/', core_views.odeme_sil, name='odeme_sil'), # EKSİK OLAN SİLME YOLU EKLENDİ
    
    # 6. Hızlı Tanımlamalar (Popup/Yeni Sekme)
    path('tedarikci/ekle/', core_views.tedarikci_ekle, name='tedarikci_ekle'),
    path('malzeme/ekle/', core_views.malzeme_ekle, name='malzeme_ekle'),
    
    # 7. Talep Yönetimi & Stok & Depo
    path('talep/yeni/', core_views.talep_olustur, name='talep_olustur'),
    path('talep/onayla/<int:talep_id>/', core_views.talep_onayla, name='talep_onayla'),
    path('talep/tamamla/<int:talep_id>/', core_views.talep_tamamla, name='talep_tamamla'),
    path('talep/sil/<int:talep_id>/', core_views.talep_sil, name='talep_sil'),
    path('arsiv/', core_views.arsiv_raporu, name='arsiv_raporu'),
    path('talep/geri-al/<int:talep_id>/', core_views.talep_arsivden_cikar, name='talep_arsivden_cikar'),
    path('stok-listesi/', core_views.stok_listesi, name='stok_listesi'),
    path('hizmet-listesi/', core_views.hizmet_listesi, name='hizmet_listesi'),
    path('hizmet/ekle/', core_views.hizmet_ekle, name='hizmet_ekle'),
    path('hizmet/duzenle/<int:pk>/', core_views.hizmet_duzenle, name='hizmet_duzenle'),
    path('hizmet/sil/<int:pk>/', core_views.hizmet_sil, name='hizmet_sil'),
    
    path('siparisler/', core_views.siparis_listesi, name='siparis_listesi'),
    path('mal-kabul/<int:siparis_id>/', core_views.mal_kabul, name='mal_kabul'),
    path('siparis/detay/<int:siparis_id>/', core_views.siparis_detay, name='siparis_detay'),
    path('fatura-gir/<int:siparis_id>/', core_views.fatura_girisi, name='fatura_girisi'),
    path('fatura/sil/<int:fatura_id>/', core_views.fatura_sil, name='fatura_sil'),
    path('depo/transfer/', core_views.depo_transfer, name='depo_transfer'),
    path('api/depo-stok/', core_views.get_depo_stok, name='get_depo_stok'),
    
    path('debug/stok/<int:malzeme_id>/', core_views.stok_rontgen),
    path('stok/gecmis/<int:malzeme_id>/', core_views.stok_hareketleri, name='stok_hareketleri'),
    path('rapor/envanter/', core_views.envanter_raporu, name='envanter_raporu'),
    
    path('hakedis/ekle/<int:siparis_id>/', core_views.hakedis_ekle, name='hakedis_ekle'),
    path('odeme/yap/', core_views.odeme_yap, name='odeme_yap'),
    path('cari/ekstre/<int:tedarikci_id>/', core_views.cari_ekstre, name='cari_ekstre'),
    
    # 8. Tanımlar & Kategori & Depo
    path('tanim-yonetimi/', core_views.tanim_yonetimi, name='tanim_yonetimi'),
    path('kategori/ekle/', core_views.kategori_ekle, name='kategori_ekle'),
    path('depo/ekle/', core_views.depo_ekle, name='depo_ekle'),
    path('kategoriler/', core_views.kategori_listesi, name='kategori_listesi'),
    path('kategori/duzenle/<int:pk>/', core_views.kategori_duzenle, name='kategori_duzenle'),
    path('kategori/sil/<int:pk>/', core_views.kategori_sil, name='kategori_sil'),
    path('depolar/', core_views.depo_listesi, name='depo_listesi'),
    path('depo/duzenle/<int:pk>/', core_views.depo_duzenle, name='depo_duzenle'),
    path('depo/sil/<int:pk>/', core_views.depo_sil, name='depo_sil'),
    path('tedarikciler/', core_views.tedarikci_listesi, name='tedarikci_listesi'),
    path('tedarikci/duzenle/<int:pk>/', core_views.tedarikci_duzenle, name='tedarikci_duzenle'),
    path('tedarikci/sil/<int:pk>/', core_views.tedarikci_sil, name='tedarikci_sil'),
    path('malzeme/duzenle/<int:pk>/', core_views.malzeme_duzenle, name='malzeme_duzenle'),
    path('malzeme/sil/<int:pk>/', core_views.malzeme_sil, name='malzeme_sil'),
    
    # 9. Belge & Sonuç & Yazdırma
    path('islem-sonuc/<str:model_name>/<int:pk>/', core_views.islem_sonuc, name='islem_sonuc'),
    path('yazdir/<str:model_name>/<int:pk>/', core_views.belge_yazdir, name='belge_yazdir'),
    path('api/tedarikci-bakiye/<int:tedarikci_id>/', core_views.get_tedarikci_bakiye, name='api_tedarikci_bakiye'),
    
    # 10. Oturum
    path('cikis/', core_views.cikis_yap, name='cikis_yap'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)