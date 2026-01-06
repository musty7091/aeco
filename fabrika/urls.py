from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

# --- İŞTE BU SATIR EKSİK OLDUĞU İÇİN HATA ALIYORDUNUZ ---
from core import views 
# --------------------------------------------------------

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Ana Sayfa ve Raporlar
    path('', views.dashboard, name='dashboard'),
    path('icmal/', views.icmal_raporu, name='icmal_raporu'),
    path('finans/', views.finans_ozeti, name='finans_ozeti'),
    path('cek-takibi/', views.cek_takibi, name='cek_takibi'),
    path('cek-durum/<int:odeme_id>/', views.cek_durum_degistir, name='cek_durum_degistir'),
    
    # Detay ve İşlem Sayfaları
    path('tedarikci/<int:tedarikci_id>/', views.tedarikci_ekstresi, name='tedarikci_ekstresi'),
    path('teklif/durum/<int:teklif_id>/<str:yeni_durum>/', views.teklif_durum_guncelle, name='teklif_durum_guncelle'),
    
    # --- YENİ EKLENEN YAZDIRMA YOLLARI ---
    path('islem-sonuc/<str:model_name>/<int:pk>/', views.islem_sonuc, name='islem_sonuc'),
    path('yazdir/<str:model_name>/<int:pk>/', views.belge_yazdir, name='belge_yazdir'),
    path('cikis/', views.cikis_yap, name='cikis_yap'),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)