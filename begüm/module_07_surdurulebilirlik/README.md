# Modül 7 — Akademik Program Sürdürülebilirlik Analizi

PDF **Bölüm 7 – Academic Program Sustainability Analysis** karşılığı modül.

> ⚠️ **Kapsam düzeltmesi:** Bu modülün ilk sürümü (`sustainability.py`) mobilya
> ürünlerinin geri dönüşüm oranını ve karbon ayak izini hesaplıyordu — yani yeşil kampüs
> / çevresel sürdürülebilirlik. PDF'in 7. bölümü ise **akademik programların ayakta
> kalabilirliğini** ister: öğrenci talebi, doluluk, mezuniyet, gelir-gider dengesi gibi
> kriterlerle programın sürdürülebilir olup olmadığı. Modül bu doğru kapsamda yeniden
> yazılmıştır; eski dosya kaldırılmıştır (git geçmişinde mevcuttur).

## Ana Sorumluluk

Her akademik programı 11 kriterle değerlendirip 0-100 arası ağırlıklı bir
sürdürülebilirlik puanı üretmek ve programı PDF'te sayılan beş kategoriden birine
yerleştirmek.

## 11 Kriter ve Kaynakları

| Kriter | Ağırlık | Kaynak |
| :--- | ---: | :--- |
| `student_demand` | 15 | **Hesaplanan** — Modül 3 taban puan + talep trendi |
| `occupancy_rate` | 15 | **Hesaplanan** — Modül 3 doluluk oranı |
| `graduation_rate` | 10 | **Hesaplanan** — Modül 3 mezuniyet oranı |
| `graduate_employability` | 10 | Dış girdi — mezun istihdam takibi |
| `academic_staff_quality` | 10 | Dış girdi — Modül 4 |
| `research_performance` | 10 | Dış girdi — Modül 4 |
| `revenue_expenditure_balance` | 12 | Dış girdi — Modül 5 |
| `physical_resource_requirement` | 5 | Dış girdi — Modül 5 |
| `strategic_contribution` | 5 | Dış girdi — Modül 8 |
| `regional_contribution` | 4 | Dış girdi — kurumsal değerlendirme |
| `reputation_contribution` | 4 | Dış girdi — kurumsal itibar |

Ağırlıklar `config/weights.json` dosyasından değiştirilebilir — PDF'in "ağırlıklar
kurumun stratejik önceliklerine göre yapılandırılabilir olmalıdır" maddesinin karşılığı.

## Eksik Veri Yaklaşımı

11 kriterin yalnızca 3'ü şu an hesaplanabiliyor (toplam ağırlığın %40'ı). Eksik kriterler
**uydurulmaz**: ağırlıklar mevcut kriterler üzerinde yeniden normalize edilir ve yanıta
`data_completeness_percent` alanı eklenir. Böylece modül tek başına da çalışır, diğer
modüller bağlandığında puan kendiliğinden zenginleşir.

`POST /api/program-sustainability/scores` ucuna dış kriter puanları gönderilerek bu
zenginleşme demoda canlı gösterilebilir.

## Kategoriler (PDF Bölüm 7)

| Kategori | Koşul |
| :--- | :--- |
| Büyüme potansiyeli olan program | Puan ≥ 75 |
| Güçlendirilmesi gereken program | 60 ≤ Puan < 75 |
| Stratejik kurumsal destek gerektiren program | Puan < 60 **ve** stratejik katkı ≥ 60 |
| Birleştirme/konsolidasyon için uygun program | Puan < 60, doluluk < %40 **ve** öğrenci sayısı < 150 |
| Yeniden yapılandırılması gereken program | Puan < 60, diğer koşullar sağlanmıyor |

Kategori sırf puana değil, programın büyüklüğüne ve stratejik katkısına da bakar:
küçük ve boş bir program birleştirme adayıyken, aynı puana sahip büyük bir program
yeniden yapılandırma adayıdır.

## Dosyalar

| Katman | Dosya |
| :--- | :--- |
| Yapılandırma | `config/weights.json` |
| Servis | `services/sustainability_service.py` |
| Şema | `schemas/sustainability.py` |
| Router | `routers/sustainability.py` |

## Endpoint'ler

```
GET  /api/program-sustainability/weights
GET  /api/program-sustainability/scores?academic_year=2026-2027
POST /api/program-sustainability/scores      # dış girdilerle yeniden puanlama
GET  /api/program-sustainability/scores/{program_code}
GET  /api/program-sustainability/categories
```

## Durum

Çalışıyor — 5 endpoint, HTTP üzerinden doğrulandı.
