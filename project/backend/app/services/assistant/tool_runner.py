"""Araç çağrılarını doğrular ve çalıştırır.

Modelin ürettiği bir araç çağrısı buradan geçmeden ÇALIŞTIRILMAZ. Sırayla:

1. Araç adı kayıt defterinde var mı?           → yoksa çalıştırma
2. Kullanıcının yetkisi var mı?                → yoksa çalıştırma
3. Parametreler girdi şemasına uyuyor mu?      → uymuyorsa çalıştırma
4. Aynı araç aynı parametrelerle çağrıldı mı?  → çağrıldıysa tekrar çalıştırma
5. Araç kendi süre sınırı içinde bitiyor mu?   → bitmiyorsa iptal
6. Çıktı, çıktı şemasına uyuyor mu?            → uymuyorsa MODELE GÖNDERME

Her adımın başarısızlığı modele "hata" olarak bildirilir; model bunun üzerine
sayı uyduramaz, çünkü sistem yönergesi tool sonucu olmadan sayı üretmeyi
yasaklar.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

#: Veri araçlarının süre tavanı. Tek yerde tanımlıdır ve
#: `chat_service` ile aynı değeri paylaşır (döngüsel içe aktarmayı
#: önlemek için burada da sabit olarak tutulur).
DATA_TOOL_TIMEOUT_SECONDS = 10.0

from app.services.assistant.tool_registry import (
    ToolExecutionError,
    ToolRegistry,
    registry as default_registry,
)

logger = logging.getLogger(__name__)

# Araçlar senkron servis çağrıları yapıyor; süre sınırını uygulayabilmek için
# ayrı bir iş parçacığında çalıştırılıyorlar.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="assistant-tool")


@dataclass
class ToolCallRecord:
    """Bir araç çağrısının sonucu. Cevap metadata'sına ve günlüğe girer."""

    name: str
    arguments: Dict[str, Any]
    success: bool
    #: Modele gönderilecek içerik (JSON metni).
    content: str
    error_kind: Optional[str] = None
    data_source: Optional[str] = None
    #: Aracın döndürdüğü doğrulanmış çıktı. Sunucu içi kullanım için.
    output: Any = None


@dataclass
class ToolSession:
    """Bir sohbet turundaki araç çağrılarının ortak durumu.

    Aynı aracın aynı parametrelerle tekrar çağrılmasını engeller. Model
    döngüye girip aynı sorguyu beş kez çalıştırırsa hem kullanıcı bekler hem
    veritabanı boşuna yorulur.
    """

    db: Session
    permissions: Optional[List[str]] = None
    registry: ToolRegistry = field(default=default_registry)
    records: List[ToolCallRecord] = field(default_factory=list)

    #: Arayüzde SEÇİLİ olan birim ("faculty" / "department" / "program" ->
    #: birim adı). Kullanıcı "Yazılım Mühendisliği" sayfasındayken "doluluk
    #: nedir?" diye sorduğunda, soru hiçbir birim adı içermese bile cevabın
    #: o programa ait olması gerekir.
    #:
    #: NEDEN BURADA: eskiden arayüz birim adını sorunun METNİNE ekliyordu
    #: ("Yazılım Mühendisliği için: doluluk nedir?"). Bu, ad tahminine
    #: dayalı kırılgan bir çözümdü. Artık kapsam YAPISAL olarak taşınıyor
    #: ve araç parametrelerine VARSAYILAN olarak yazılıyor. Kullanıcı
    #: soruda başka bir birim adı geçirirse o kazanır — kapsam yalnızca
    #: BOŞ alanları doldurur, hiçbir zaman üzerine yazmaz.
    ui_scope: Optional[Dict[str, str]] = None

    #: Bu turdaki KULLANICI SORUSUNUN kendisi.
    #:
    #: NEDEN GEREKLİ: kaynak seçimi artık sorudan çıkarılan bir plana
    #: (niyet, metrik ailesi, yıl aralığı, seviye) dayanıyor. Model
    #: keşif aracına yalnızca bir arama terimi veriyor ("taban puan");
    #: o terimde soruda geçen "son 5 yıl" ya da "üniversiteler" bilgisi
    #: yok. Planı yalnızca arama teriminden çıkarmak, sorunun yarısını
    #: atmak olurdu. Soru burada YAPISAL olarak taşınır.
    user_question: Optional[str] = None
    _seen: Dict[str, ToolCallRecord] = field(default_factory=dict)

    def _with_ui_scope(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Eksik kapsam parametrelerini arayüzdeki seçimle doldurur."""
        if not self.ui_scope:
            return args
        try:
            alanlar = set(self.registry.get(name).input_model.model_fields)
        except Exception:  # araç bilinmiyorsa doğrulama zaten reddedecek
            return args

        tamamlanan = dict(args)
        # Dönem kapsamdan bağımsızdır: araç yıl alanı destekliyorsa seçili
        # yıl daima varsayılan olur. Kullanıcının/Modelin açık argümanı
        # korunur; UI seçimi onun üzerine yazılmaz.
        secili_yil = self.ui_scope.get("academic_year")
        if ("academic_year" in alanlar and secili_yil
                and not tamamlanan.get("academic_year")):
            tamamlanan["academic_year"] = secili_yil
        # En dar seviyeden başlanır: program seçiliyse fakülte/bölüm
        # parametresi EKLENMEZ; `resolve_scope` onları programdan türetir
        # ve çelişkili kombinasyon üretme riski ortadan kalkar.
        for anahtar in ("program", "department", "faculty"):
            deger = self.ui_scope.get(anahtar)
            if not deger:
                continue
            if anahtar in alanlar and not tamamlanan.get(anahtar):
                tamamlanan[anahtar] = deger
            break
        return tamamlanan

    def _key(self, name: str, arguments: Dict[str, Any]) -> str:
        # Anahtar sıralı JSON: {"a":1,"b":2} ile {"b":2,"a":1} aynı çağrıdır.
        return name + "|" + json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)

    def already_called(self, name: str, arguments: Dict[str, Any]) -> bool:
        return self._key(name, arguments) in self._seen

    def run(self, name: str, arguments: Optional[Dict[str, Any]]) -> ToolCallRecord:
        """Bir araç çağrısını doğrular ve çalıştırır."""
        args = arguments if isinstance(arguments, dict) else {}
        args = self._with_ui_scope(name, args)
        key = self._key(name, args)

        # 4) Tekrar eden çağrı: eski sonucu döndür, aracı yeniden çalıştırma.
        previous = self._seen.get(key)
        if previous is not None:
            logger.info("Tekrarlanan arac cagrisi atlandi: %s", name)
            repeated = ToolCallRecord(
                name=name,
                arguments=args,
                success=previous.success,
                content=(
                    "Bu araç bu parametrelerle zaten çağrıldı. Önceki sonuç: "
                    + previous.content
                ),
                error_kind="duplicate",
                data_source=previous.data_source,
                output=previous.output,
            )
            logger.info("TOOL CACHE HIT name=%s", name)
            self.records.append(repeated)
            return repeated

        record = self._execute(name, args)
        self._seen[key] = record
        self.records.append(record)
        return record

    def _execute(self, name: str, args: Dict[str, Any]) -> ToolCallRecord:
        def failure(message: str, kind: str, data_source: Optional[str] = None) -> ToolCallRecord:
            return ToolCallRecord(
                name=name,
                arguments=args,
                success=False,
                content=json.dumps({"error": message}, ensure_ascii=False),
                error_kind=kind,
                data_source=data_source,
            )

        # 1) Bilinmeyen araç adı
        try:
            tool = self.registry.get(name)
        except ToolExecutionError as exc:
            logger.warning("Bilinmeyen arac adi reddedildi: %s", name)
            return failure(exc.message, exc.kind)

        # 2) Yetki
        if (
            tool.required_permission is not None
            and self.permissions is not None
            and tool.required_permission not in self.permissions
        ):
            return failure(
                "Bu veriyi görüntüleme yetkiniz yok.", "forbidden", tool.data_source
            )

        # 3) Parametre doğrulama
        try:
            payload = tool.input_model(**args)
        except ValidationError as exc:
            # Modele hangi alanın yanlış olduğu söylenir ki düzeltip tekrar
            # deneyebilsin. Ham Pydantic çıktısı yerine sade bir özet.
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'girdi'}: {e['msg']}"
                for e in exc.errors()[:5]
            )
            return failure(
                f"Geçersiz parametre. {problems}", "invalid_arguments", tool.data_source
            )
        except TypeError as exc:
            return failure(f"Geçersiz parametre: {exc}", "invalid_arguments", tool.data_source)

        # 5) Süre sınırı içinde çalıştır
        if getattr(tool, "needs_session", False):
            future = _executor.submit(tool.handler, self.db, payload, self)
        else:
            future = _executor.submit(tool.handler, self.db, payload)
        # ARAÇ SÜRE TAVANI.
        # Kayıtlı araçların kendi sınırları 10–30 saniye arasındaydı.
        # Hepsi yerel SQLite/CSV okuması yapıyor; 30 saniye bekleyen bir
        # sorgu zaten bir hata belirtisidir ve o süre boyunca kullanıcı
        # bekletilmemeli. Tavan uygulanır, ama KENDİ SINIRI DAHA DÜŞÜK
        # OLAN ARAÇ OLDUĞU GİBİ KALIR: hiçbir aracın süresi uzatılmaz.
        sinir = min(tool.timeout_seconds, DATA_TOOL_TIMEOUT_SECONDS)
        basladi = time.monotonic()
        logger.info("TOOL START name=%s timeout=%.0f", name, sinir)
        try:
            result = future.result(timeout=sinir)
        except FutureTimeout:
            future.cancel()
            logger.warning("TOOL TIMEOUT name=%s duration=%.1f limit=%.0f",
                           name, time.monotonic() - basladi, sinir)
            return failure(
                "Veri kaynağı zamanında yanıt vermedi; bu değer için sonuç üretilemedi.",
                "timeout",
                tool.data_source,
            )
        except ToolExecutionError as exc:
            # Beklenen iş hatası: veri yok, belirsiz birim, geçersiz girdi.
            return failure(exc.message, exc.kind, tool.data_source)
        except Exception:  # noqa: BLE001
            logger.exception("Arac beklenmedik sekilde basarisiz oldu: %s", name)
            return failure(
                "Veri kaynağına erişilirken beklenmeyen bir hata oluştu.",
                "error",
                tool.data_source,
            )

        # 6) Çıktı şema doğrulaması — geçmeyen sonuç modele GÖNDERİLMEZ.
        if not isinstance(result, tool.output_model):
            try:
                result = tool.output_model.model_validate(result)
            except ValidationError:
                logger.error("Arac ciktisi semaya uymadi: %s", name)
                return failure(
                    "Veri kaynağından beklenen biçimde sonuç alınamadı.",
                    "invalid_output",
                    tool.data_source,
                )

        _icerik = result.model_dump_json()
        logger.info("TOOL END name=%s duration=%.2f result_chars=%d",
                    name, time.monotonic() - basladi, len(_icerik))
        return ToolCallRecord(
            name=name,
            arguments=args,
            success=True,
            content=_icerik,
            data_source=tool.data_source,
            output=result,
        )

    # ------------------------------------------------------------------
    # Cevap metadata'sı
    # ------------------------------------------------------------------

    def used_tools(self) -> List[Dict[str, Any]]:
        """Cevapta döndürülecek araç listesi."""
        return [
            {"name": r.name, "success": r.success}
            for r in self.records
            if r.error_kind != "duplicate"
        ]

    def data_sources(self) -> List[str]:
        """Başarılı araçların Türkçe veri kaynağı adları (tekrarsız)."""
        seen: List[str] = []
        for record in self.records:
            if record.success and record.data_source and record.data_source not in seen:
                seen.append(record.data_source)
        return seen

    def scope(self) -> Dict[str, str]:
        """Başarılı araç çıktılarından derlenen kapsam.

        Kapsam MODELİN cümlesinden değil, araç çıktısından okunur; model
        yanlış bir bölüm adı yazsa bile metadata doğru kalır.
        """
        result: Dict[str, str] = {}
        for record in self.records:
            scope = getattr(record.output, "scope", None)
            if scope is None:
                continue
            for key in ("faculty", "department", "program"):
                value = getattr(scope, key, None)
                if value:
                    result[key] = value
        return result

    def academic_year(self) -> Optional[str]:
        """Kullanılan akademik yıl."""
        for record in self.records:
            scope = getattr(record.output, "scope", None)
            if scope is not None and getattr(scope, "academic_year", None):
                return scope.academic_year
        return None

    def any_success(self) -> bool:
        return any(r.success for r in self.records)
