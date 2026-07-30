import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

print("=== MODÜL 3: ÖĞRENCİ ANALİTİĞİ VE DOLULUK ORANLARI ===")

# Örnek veri setleri
students_data = {
    'student_number': [101, 102, 103, 104, 105],
    'is_international': ['yes', 'no', 'no', 'yes', 'no'],
    'scholarship_rate_percent': [50, 100, 25, 0, 75],
    'preparatory_school': ['no', 'yes', 'yes', 'no', 'no']
}
students_df = pd.DataFrame(students_data)

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
plt.figure(figsize=(7, 4))
sns.barplot(data=snapshots_df, x='academic_program_code', y='occupancy_rate', hue='academic_program_code', palette='Blues_d', legend=False)
plt.xlabel('Program Kodu')
plt.ylabel('Doluluk Oranı (%)')
plt.title('Modül 3 - Akademik Programlar Doluluk Oranı')
plt.ylim(0, 100)
plt.savefig('program_doluluk_orani.png', dpi=300, bbox_inches='tight')
print("\n[Bilgi] 'program_doluluk_orani.png' başarıyla kaydedildi.")
plt.show()
