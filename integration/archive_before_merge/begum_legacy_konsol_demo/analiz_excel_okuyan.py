import pandas as pd

# 1. Veri setlerini yükleme
students_df = pd.read_excel('students_sample.xlsx')
snapshots_df = pd.read_excel('program_enrollment_snapshots_sample.xlsx')

# 2. Temel Öğrenci Metrikleri Analizi
total_students = len(students_df)
international_count = students_df['is_international'].apply(lambda x: str(x).lower() in ['evet', 'yes', 'true', '1']).sum()
scholarship_avg = students_df['scholarship_rate_percent'].mean()
prep_count = students_df['preparatory_school'].apply(lambda x: str(x).lower() in ['evet', 'yes', 'true', '1']).sum()

print(f"--- Üniversite Geneli Temel Öğrenci Metrikleri ---")
print(f"Toplam Öğrenci Sayısı: {total_students}")
print(f"Uluslararası Öğrenci Oranı: %{(international_count/total_students*100):.1f}")
print(f"Ortalama Burs Oranı: %{scholarship_avg:.1f}")
print(f"Hazırlık Sınıfındaki Öğrenci Sayısı: {prep_count}")

# 3. Program Doluluk (Occupancy) Oranları Analizi
snapshots_df['occupancy_rate'] = (snapshots_df['enrolled_student_count'] / snapshots_df['quota']) * 100

print(f"\n--- Program Bazlı Doluluk ve Durum Raporu ---")
print(snapshots_df[['academic_program_code', 'quota', 'enrolled_student_count', 'occupancy_rate', 'graduated_student_count', 'dropped_out_student_count']])

import pandas as pd

print("=== 1. HAFTA: TEMEL ÖĞRENCİ VE PROGRAM ANALİZİ ===\n")

# 1. Veri setlerini yükleme
students_df = pd.read_excel('students_sample.xlsx')
snapshots_df = pd.read_excel('program_enrollment_snapshots_sample.xlsx')
acad_df = pd.read_excel('student_academic_records_sample.xlsx')

# 2. Üniversite Geneli Temel Öğrenci Metrikleri
total_students = len(students_df)
international_count = students_df['is_international'].apply(lambda x: str(x).lower() in ['evet', 'yes', 'true', '1']).sum()
scholarship_avg = students_df['scholarship_rate_percent'].mean()
prep_count = students_df['preparatory_school'].apply(lambda x: str(x).lower() in ['evet', 'yes', 'true', '1']).sum()

print("--- Üniversite Geneli Temel Öğrenci Metrikleri ---")
print(f"Toplam Öğrenci Sayısı: {total_students}")
print(f"Uluslararası Öğrenci Oranı: %{(international_count/total_students*100):.1f}")
print(f"Ortalama Burs Oranı: %{scholarship_avg:.1f}")
print(f"Hazırlık Sınıfındaki Öğrenci Sayısı: {prep_count}\n")

# 3. Program Doluluk ve Durum Analizi
snapshots_df['occupancy_rate'] = (snapshots_df['enrolled_student_count'] / snapshots_df['quota']) * 100

print("--- Program Bazlı Doluluk ve Durum Raporu ---")
print(snapshots_df[['academic_program_code', 'quota', 'enrolled_student_count', 'occupancy_rate', 'graduated_student_count', 'dropped_out_student_count']])

# 4. Akademik Başarı ve GNO Özeti
print("\n--- Öğrenci Akademik Başarı ve GNO Özeti ---")
print(acad_df[['student_number', 'academic_year', 'semester', 'cumulative_gpa', 'registration_renewed']])

print("\n=== 1. HAFTA ANALİZİ BAŞARIYLA TAMAMLANDI ===")

import matplotlib.pyplot as plt
import seaborn as sns

# Tablo Verilerini Düzenli Yazdırma
print("\n=== PROGRAM DOLULUK TABLOSU ===")
summary_table = snapshots_df[['academic_program_code', 'quota', 'enrolled_student_count', 'occupancy_rate']].copy()
print(summary_table.to_string(index=False))

# Görsel Grafik Oluşturma (Doluluk Oranları Çubuğu)
plt.figure(figsize=(8, 5))
sns.barplot(data=snapshots_df, x='academic_program_code', y='occupancy_rate', hue='academic_program_code', palette='Blues_d', legend=False)
plt.xlabel('Program Kodu')
plt.ylabel('Doluluk Oranı (%)')
plt.ylim(0, 100)

# Grafiği Kaydetme
plt.savefig('program_doluluk_orani.png', dpi=300, bbox_inches='tight')
print("\n[Bilgi] 'program_doluluk_orani.png' dosyası olarak grafik başarıyla kaydedildi!")

# Grafiği Ekranda Gösterme
plt.show()
# Dosyaların tam yolunu buraya yazıyoruz
