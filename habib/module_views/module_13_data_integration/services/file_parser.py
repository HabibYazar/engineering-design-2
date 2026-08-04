"""Yüklenen CSV, Excel ve JSON dosyalarını ortak bir sözlük listesine çeviren modül."""

import json
from io import BytesIO
from typing import Any, Dict, List, Tuple

import pandas as pd

# Desteklenen uzantılar. Bu listeyi tek yerde tutmak, yeni bir format eklendiğinde
# sadece burayı ve ilgili okuma fonksiyonunu değiştirmeyi yeterli kılar.
SUPPORTED_EXTENSIONS: Tuple[str, ...] = (".csv", ".xlsx", ".json")


class FileParseError(Exception):
    """Dosya okunurken oluşan, kullanıcıya gösterilebilir hataları temsil eder.

    status_code alanı sayesinde router, hangi HTTP kodunu döndüreceğini bilir.
    Böylece servis katmanı FastAPI'ye bağımlı olmadan hata türünü bildirebiliyor.
    """

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message: str = message
        self.status_code: int = status_code


def detect_file_type(file_name: str) -> str:
    """Dosya adına bakarak uzantıyı belirler, desteklenmiyorsa 415 hatası üretir."""
    lowered: str = (file_name or "").lower().strip()

    for extension in SUPPORTED_EXTENSIONS:
        if lowered.endswith(extension):
            return extension.lstrip(".")

    # 415 Unsupported Media Type: içerik türü desteklenmiyor anlamına gelen standart kod.
    raise FileParseError(
        f"Desteklenmeyen dosya biçimi. Sadece {', '.join(SUPPORTED_EXTENSIONS)} kabul edilir.",
        status_code=415,
    )


def _normalize_key(key: Any) -> str:
    """Sütun adlarını küçük harfe çevirip boşlukları alt çizgiye dönüştürür."""
    # Kullanıcı "Faculty Code", "faculty_code" veya "FACULTY CODE" yazabilir.
    # Hepsini aynı forma getirerek dosya başlıklarındaki küçük farkları tolere ediyoruz.
    return str(key).strip().lower().replace(" ", "_").replace("-", "_")


def _dataframe_to_rows(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    """Pandas DataFrame'i sözlük listesine dönüştürür ve boş değerleri temizler."""
    # Tüm sütunları metin olarak okuyup boşlukları kırpıyoruz.
    # Sayısal doğrulama daha sonra validator katmanında yapılacağı için burada tip dönüşümü yapmıyoruz.
    frame = frame.rename(columns={column: _normalize_key(column) for column in frame.columns})

    rows: List[Dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        cleaned: Dict[str, Any] = {}
        for key, value in record.items():
            # pandas boş hücreleri NaN olarak okur; bunları boş metne çeviriyoruz.
            if value is None or (isinstance(value, float) and pd.isna(value)):
                cleaned[key] = ""
            else:
                cleaned[key] = str(value).strip()
        rows.append(cleaned)
    return rows


def _parse_csv(content: bytes) -> List[Dict[str, Any]]:
    """CSV içeriğini okur."""
    try:
        # dtype=str: kodların başındaki sıfırlar (örn. "007") kaybolmasın.
        # keep_default_na=False: "NA" gibi metinler yanlışlıkla boş değer sayılmasın.
        frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False)
    except Exception as error:
        raise FileParseError(f"CSV dosyası okunamadı: {error}") from error
    return _dataframe_to_rows(frame)


def _parse_excel(content: bytes) -> List[Dict[str, Any]]:
    """Excel (.xlsx) içeriğini okur."""
    try:
        # openpyxl motoru xlsx formatını okumak için kullanılır.
        frame = pd.read_excel(BytesIO(content), dtype=str, engine="openpyxl")
    except Exception as error:
        raise FileParseError(f"Excel dosyası okunamadı: {error}") from error
    return _dataframe_to_rows(frame)


def _parse_json(content: bytes) -> List[Dict[str, Any]]:
    """JSON içeriğini okur; dosya bir kayıt listesi içermelidir."""
    try:
        data: Any = json.loads(content.decode("utf-8"))
    except Exception as error:
        raise FileParseError(f"JSON dosyası okunamadı: {error}") from error

    # Kullanıcı yanlışlıkla tek bir nesne gönderirse bunu tek elemanlı listeye çeviriyoruz.
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        raise FileParseError("JSON dosyası bir kayıt listesi içermelidir.")

    rows: List[Dict[str, Any]] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise FileParseError(f"JSON listesindeki {index}. eleman bir nesne değil.")

        cleaned: Dict[str, Any] = {}
        for key, value in item.items():
            # JSON'da is_active gerçek boolean olarak gelebilir; metne çevirip
            # doğrulama katmanının ortak mantığını kullanmasını sağlıyoruz.
            cleaned[_normalize_key(key)] = "" if value is None else str(value).strip()
        rows.append(cleaned)

    return rows


def parse_file(file_name: str, content: bytes) -> Tuple[str, List[Dict[str, Any]]]:
    """Dosyayı biçimine göre okuyup (dosya_tipi, satır listesi) döndürür."""
    file_type: str = detect_file_type(file_name)

    # Boş dosya kontrolü okuma denemesinden önce yapılır ki
    # kullanıcı teknik bir kütüphane hatası yerine net bir mesaj görsün.
    if not content or len(content.strip()) == 0:
        raise FileParseError("Yüklenen dosya boş.")

    if file_type == "csv":
        rows = _parse_csv(content)
    elif file_type == "xlsx":
        rows = _parse_excel(content)
    else:
        rows = _parse_json(content)

    if not rows:
        raise FileParseError("Dosyada işlenecek satır bulunamadı.")

    return file_type, rows
