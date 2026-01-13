from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views 

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # 1. Ana Karşılama
    path('', views.dashboard, name='dashboard'),
    path('erisim-engellendi/', views.erisim_engellendi, name='erisim_engellendi'),

    # 2. Modüller (İcmal & Teklif)
    path('icmal/', views.icmal_raporu, name='icmal_raporu'),
    path('teklif/ekle/', views.teklif_ekle, name='teklif_ekle'),
    
    # 3. Dashboardlar
    path('finans-dashboard/', views.finans_dashboard, name='finans_dashboard'),
    path('depo-dashboard/', views.depo_dashboard, name='depo_dashboard'),
    path('odeme-dashboard/', views.odeme_dashboard, name='odeme_dashboard'),
    
    # 4. Detaylar
    path('finans/detay-ozet/', views.finans_ozeti, name='finans_ozeti'),
    path('cek-takibi/', views.cek_takibi, name='cek_takibi'),
    
    # 5. İşlemler (Finans & Teklif)
    path('cek-durum/<int:odeme_id>/', views.cek_durum_degistir, name='cek_durum_degistir'),
    path('tedarikci/<int:tedarikci_id>/', views.tedarikci_ekstresi, name='tedarikci_ekstresi'),
    path('teklif/durum/<int:teklif_id>/<str:yeni_durum>/', views.teklif_durum_guncelle, name='teklif_durum_guncelle'),
    
    # 6. Hızlı Tanımlamalar (Popup/Yeni Sekme)
    path('tedarikci/ekle/', views.tedarikci_ekle, name='tedarikci_ekle'),
    path('malzeme/ekle/', views.malzeme_ekle, name='malzeme_ekle'),
    
    # 7. Talep Yönetimi (YENİ EKLENENLER)
    path('talep/yeni/', views.talep_olustur, name='talep_olustur'),
    path('talep/onayla/<int:talep_id>/', views.talep_onayla, name='talep_onayla'),
    path('talep/tamamla/<int:talep_id>/', views.talep_tamamla, name='talep_tamamla'),
    path('talep/sil/<int:talep_id>/', views.talep_sil, name='talep_sil'),
    path('arsiv/', views.arsiv_raporu, name='arsiv_raporu'),
    path('talep/geri-al/<int:talep_id>/', views.talep_arsivden_cikar, name='talep_arsivden_cikar'),
    
    # 8. Yazdırma & Çıktı
    path('islem-sonuc/<str:model_name>/<int:pk>/', views.islem_sonuc, name='islem_sonuc'),
    path('yazdir/<str:model_name>/<int:pk>/', views.belge_yazdir, name='belge_yazdir'),
    
    # 9. Oturum
    path('cikis/', views.cikis_yap, name='cikis_yap'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)