from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views 

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # 1. GENEL
    path('', views.dashboard, name='dashboard'),
    path('erisim-engellendi/', views.erisim_engellendi, name='erisim_engellendi'),
    path('cikis/', views.cikis_yap, name='cikis_yap'),

    # 2. DEPO VE STOK (Aktif Olanlar)
    path('depolar/', views.depo_listesi, name='depo_listesi'),
    path('depo/detay/<int:depo_id>/', views.depo_detay, name='depo_detay'), # Yeni detay view'ı
    path('depo/transfer/', views.depo_transfer, name='depo_transfer'),
    path('stok/hareketleri/', views.stok_hareketleri, name='stok_hareketleri'),

    path('talep/yeni/', views.talep_olustur, name='talep_olustur'),
    path('talep/sil/<int:talep_id>/', views.talep_sil, name='talep_sil'),
    path('talepler/', views.talep_listesi, name='talep_listesi'),
    path('talep/durum/<int:talep_id>/<str:yeni_durum>/', views.talep_durum_degistir, name='talep_durum'),

    path('talep/teklifler/<int:talep_id>/', views.teklif_yonetimi, name='teklif_yonetimi'),
    path('talep/teklif-ekle/<int:talep_id>/', views.teklif_ekle, name='teklif_ekle'),
    path('teklif/onayla/<int:teklif_id>/', views.teklif_onayla, name='teklif_onayla'),

    # Diğer modüller (Finans, Satınalma vb.) yazıldıkça buraya eklenecek.
    # Şimdilik hata vermemesi için kapalı tutuyoruz.

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)