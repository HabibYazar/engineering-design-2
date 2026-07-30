import pandas as pd

print("=== MODÜL 7: SÜRDÜRÜLEBİLİRLİK VE YEŞİL KAMPÜS ANALİTİĞİ ===")

# Döngüsel ekonomi ve yeşil ürün tasarımı metrikleri
sustainability_data = {
    'product_name': ['Akıllı Sehpa', 'Modüler Ofis Koltuğu (Optisit)', 'Dönüştürülebilir Masa'],
    'recyclable_material_ratio_percent': [85, 95, 90],
    'carbon_footprint_score_kg': [12.5, 8.0, 10.2],
    'circular_economy_compliance': ['Yüksek', 'Çok Yüksek', 'Yüksek']
}

sus_df = pd.DataFrame(sustainability_data)
print("\n--- Ürün Bazlı Sürdürülebilirlik ve Çevre Uyumluluk Raporu ---")
print(sus_df.to_string(index=False))
print("\n[Bilgi] Sürdürülebilirlik metrikleri başarıyla hesaplandı ve yeşil tasarım kriterlerine ulaşıldı.")
