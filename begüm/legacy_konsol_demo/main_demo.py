import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

print("==================================================")
print("       BEGÜM - 1. HAFTA PROJE DEMOSU BAŞLIYOR       ")
print("==================================================")

# --------------------------------------------------
# MODÜL 3: ÖĞRENCİ ANALİTİĞİ VE DOLULUK ORANLARI
# --------------------------------------------------
print("\n[1/3] Modül 3 Çalıştırılıyor: Öğrenci Analitiği...")

snapshots_data = {
    'academic_program_code': ['IE', 'CENG', 'EE', 'ME'],
    'quota': [60, 80, 50, 40],
    'enrolled_student_count': [58, 80, 42, 30]
}
snapshots_df = pd.DataFrame(snapshots_data)
snapshots_df['occupancy_rate'] = (snapshots_df['enrolled_student_count'] / snapshots_df['quota']) * 100

print("\n--- Program Bazlı Doluluk Tablosu ---")
print(snapshots_df[['academic_program_code', 'quota', 'enrolled_student_count', 'occupancy_rate']].to_string(index=False))

# Grafik oluşturma
plt.figure(figsize=(6, 3))
sns.barplot(data=snapshots_df, x='academic_program_code', y='occupancy_rate', hue='academic_program_code', palette='Blues_d', legend=False)
plt.xlabel('Program Kodu')
plt.ylabel('Doluluk Oranı (%)')
plt.title('Modül 3 - Akademik Programlar Doluluk Oranı')
plt.ylim(0, 100)
plt.savefig('program_doluluk_orani.png', dpi=300, bbox_inches='tight')
print("[Bilgi] Modül 3 grafiği 'program_doluluk_orani.png' olarak kaydedildi.")


# --------------------------------------------------
# MODÜL 7: SÜRDÜRÜLEBİLİRLİK VE YEŞİL KAMPÜS
# --------------------------------------------------
print("\n--------------------------------------------------")
print("[2/3] Modül 7 Çalıştırılıyor: Sürdürülebilirlik Analitiği...")

sustainability_data = {
    'product_name': ['Akıllı Sehpa', 'Modüler Ofis Koltuğu (Optisit)', 'Dönüştürülebilir Masa'],
    'recyclable_material_ratio_percent': [85, 95, 90],
    'carbon_footprint_score_kg': [12.5, 8.0, 10.2],
    'circular_economy_compliance': ['Yüksek', 'Çok Yüksek', 'Yüksek']
}
sus_df = pd.DataFrame(sustainability_data)
print("\n--- Ürün Bazlı Sürdürülebilirlik Raporu ---")
print(sus_df.to_string(index=False))


# --------------------------------------------------
# MODÜL 11: ERKEN UYARI VE RİSK ANALİZİ
# --------------------------------------------------
print("\n--------------------------------------------------")
print("[3/3] Modül 11 Çalıştırılıyor: Erken Uyarı Mekanizması...")

warning_data = {
    'student_number': [101, 102, 103, 104, 105],
    'cumulative_gpa': [3.45, 1.85, 2.10, 1.60, 3.00],
    'registration_renewed': ['evet', 'hayır', 'evet', 'hayır', 'evet']
}
warning_df = pd.DataFrame(warning_data)
warning_df['risk_status'] = warning_df.apply(
    lambda row: 'YÜKSEK RİSK (Uyarı Gönderildi)' if row['cumulative_gpa'] < 2.0 or row['registration_renewed'] == 'hayır' else 'Normal', 
    axis=1
)

print("\n--- Öğrenci Erken Uyarı ve Risk Tarama Raporu ---")
print(warning_df.to_string(index=False))

print("\n==================================================")
print("         DEMO BAŞARIYLA TAMAMLANDI!               ")
print("==================================================")
