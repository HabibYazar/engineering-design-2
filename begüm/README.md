# Begüm

Modül 3,7 ve 11 için çalışma bölümü.
# Modül 3, 7 ve 11: Öğrenci ve Sürdürülebilirlik Analitiği

Bu klasör, Stratejik Üniversite Yönetimi ve Karar Destek Sistemi projesinin öğrenci analitiği, program sürdürülebilirliği ve erken uyarı mekanizmalarına ait prototip çalışmalarını içerir.

## 📊 Modül Özeti

| Modül / Bölüm | Adı | Ana Sorumluluk | Dosya / Çıktı | Durum |
| :--- | :--- | :--- | :--- | :--- |
| **Bölüm 3** | Strategic Education and Student Analytics | Toplam öğrenci, kayıt, hazırlık, yabancı oranları ve doluluk analizi | `analiz.py` | Tamamlandı |
| **Bölüm 7** | Academic Program Sustainability Analysis | Çok boyutlu program sürdürülebilirlik puanı ve kategorizasyonu | `ogrenci_analiz.json` | Tasarım Aşamasında |
| **Bölüm 11** | Risk and Early Warning System | Doluluk düşüşleri ve öğrenci kayıpları için tetikleyici alarmlar | Algoritma Hazırlığı | Planlanıyor |

---

## 🛠️ Teknik Altyapı ve Kullanılan Kütüphaneler

* **Dil:** Python 3.x
* **Veri İşleme:** Pandas (Excel veri setlerinin okunması ve metrik hesaplanması)
* **Görselleştirme:** Matplotlib & Seaborn (Program doluluk oranlarının çubuk grafik olarak modellenmesi)
* **Veri Formatı:** JSON (Modüller arası veri aktarım şablonu)

---

## 📈 Çıktılar ve Görseller

1. **Konsol Raporu:** Üniversite geneli temel metrikler ve program bazlı doluluk oranları.
2. **Grafik Çıktısı:** `program_doluluk_orani.png` (Yüksek çözünürlüklü yönetim paneli görseli).
## 🔄 Modül İş Akışı
1. **Veri Girişi:** SIS / Örnek Excel verilerinin (`students_sample.xlsx`, `snapshots`) okunması.
2. **Analiz Katmanı:** Pandas ile toplam öğrenci, hazırlık, yabancı oranı ve doluluk hesaplamaları (`analiz.py`).
3. **Çıktı & Görselleştirme:** Konsol tablosu ve otomatik kaydedilen yönetim paneli grafiği (`program_doluluk_orani.png`).
4. **Entegrasyon:** Gelecek aşamada JSON şablonu üzerinden erken uyarı mekanizmasına veri aktarımı.
