import pandas as pd

print("=== MODÜL 11: ERKEN UYARI VE RİSK ANALİZİ MEKANİZMASI ===")

# Öğrenci akademik başarı ve risk durumu simülasyonu
warning_data = {
    'student_number': [101, 102, 103, 104, 105],
    'cumulative_gpa': [3.45, 1.85, 2.10, 1.60, 3.00],
    'registration_renewed': ['evet', 'hayır', 'evet', 'hayır', 'evet']
}

warning_df = pd.DataFrame(warning_data)

# Erken uyarı algoritması: GNO < 2.00 veya kayıt yenilemeyenler riskli kabul edilir
warning_df['risk_status'] = warning_df.apply(
    lambda row: 'YÜKSEK RİSK (Uyarı Gönderildi)' if row['cumulative_gpa'] < 2.0 or row['registration_renewed'] == 'hayır' else 'Normal', 
    axis=1
)

print("\n--- Öğrenci Erken Uyarı ve Risk Tarama Raporu ---")
print(warning_df.to_string(index=False))
print("\n[Bilgi] Riskli öğrenciler tespit edildi ve otomatik bildirim altyapısı simüle edildi.")
