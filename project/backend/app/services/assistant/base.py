"""Asistan sağlayıcı arayüzü (soyut taban).

Bu dosya bir dil modeli ÇAĞIRMAZ. Yalnızca ileride bir model bağlandığında
uygulanması gereken sözleşmeyi tanımlar.

Neden şimdiden tanımlanıyor: model seçimi henüz yapılmadı. Arayüz önceden
belirlenmezse her modül kendi çağrı biçimini yazar ve sağlayıcı değiştiğinde
uygulamanın her yeri elden geçirilmek zorunda kalır. Bu sözleşme sayesinde
model bağlandığında yalnızca tek bir sınıf yazılacak.
"""

from abc import ABC, abstractmethod
from typing import List

from app.services.assistant.schemas import ContextItem


class AssistantProvider(ABC):
    """Bir dil modeli sağlayıcısının uygulaması gereken arayüz."""

    #: Sağlayıcının adı (ör. yapılandırmada seçilen değer).
    name: str = "tanimsiz"

    @abstractmethod
    def is_available(self) -> bool:
        """Sağlayıcı gerçekten kullanılabilir durumda mı?

        Yapılandırma eksikse veya bağlantı kurulamıyorsa False dönmelidir.
        Uygulama bu değere bakarak kullanıcıya dürüst bir durum gösterir.
        """

    @abstractmethod
    def generate(self, question: str, context: List[ContextItem]) -> str:
        """Soruya, verilen kurumsal bağlamı kullanarak cevap üretir.

        Bu metot şu anda hiçbir sınıf tarafından uygulanmıyor.
        """


class NoProviderConfigured(AssistantProvider):
    """Hiçbir sağlayıcı seçilmediğinde kullanılan varsayılan.

    Bilinçli olarak cevap üretmez. Bunun yerine açık bir hata fırlatır;
    böylece sistem yanlışlıkla uydurma bir metin döndüremez.
    """

    name = "yok"

    def is_available(self) -> bool:
        """Her zaman False: bağlı bir model yok."""
        return False

    def generate(self, question: str, context: List[ContextItem]) -> str:
        """Çağrılırsa hata fırlatır; sessizce sahte cevap döndürmez."""
        raise RuntimeError(
            "Sisteme bagli bir dil modeli yok. Cevap uretilemez. "
            "Bir saglayici baglamak icin .env dosyasindaki LLM_PROVIDER, "
            "LLM_MODEL ve LLM_API_KEY degerlerini doldurun ve "
            "AssistantProvider arayuzunu uygulayan bir sinif yazin."
        )
