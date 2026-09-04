"""Override poligonu üretici — YARDIMCI ARAÇ, çalışma zamanı parçası değil.

`build_semantic_map.py` ALGORİTMASINA DOKUNMAZ; onu kütüphane olarak
çağırır. Tek farkı, tohum noktasını otomatik etiket eşlemesi yerine
ELLE verilen bir metin kalıbından almasıdır. Böylece paftada gerçekten
duvarla çevrili olan ama otomatik desene takılmayan odaların sınırı
KAFADAN ÇİZİLMEDEN, gerçek CAD geometrisinden okunur.

Kullanım:
    python tools_extract_override_polygon.py 1 "^21-93" "21 - SINIF-c"
"""
import json, re, sys
sys.path.insert(0, ".")
import pymupdf
import build_semantic_map as B

def cikar(kat: int, pdf: str, kalip: str):
    doc = pymupdf.open(f"../data/infrastructure/raw/{pdf}")
    sayfa = doc[0]
    ham, gw, gh = B.duvar_maskesi(sayfa)
    maske = B.kapi_kapat(ham, gw, gh)
    etiketler = B.etiketleri_topla(sayfa)
    doc.close()
    for e in etiketler:
        if not re.search(kalip, e["t"]):
            continue
        sx, sy = int(e["x"] / B.IZ), int(e["y"] / B.IZ)
        h = B._dolgu(maske, gw, gh, sx, sy, int(B.MAX_ALAN / (B.IZ * B.IZ)))
        if not h:
            return None
        return {"polygon": B._sinir(h, gw), "hucre": len(h), "metin": e["t"]}
    return None

if __name__ == "__main__":
    kat = int(sys.argv[1])
    pdf = {0: "0. Kat.pdf", 1: "1. Kat.pdf", 2: "2. Kat.pdf"}[kat]
    print(json.dumps(cikar(kat, pdf, sys.argv[2]), ensure_ascii=False))
