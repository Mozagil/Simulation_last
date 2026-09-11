# Geliştirme container'ı — sistem bağımlılıkları BURAYA gömülür.
#
# Neden Dockerfile, neden postCreateCommand değil:
#   * Bu katmanlar image'a yazılır ve ÖNBELLEKLENİR. Yeni bir Codespace
#     açıldığında (özellikle prebuild açıksa) tekrar kurulmazlar.
#   * postCreateCommand her container oluşturmada baştan çalışır ve bir
#     adımı patlarsa SONRAKİLERİN HEPSİ ATLANIR. Gerçekte yaşandı: universal
#     image'daki yarn deposunun GPG anahtarı doğrulanamayınca `apt-get update`
#     exit 100 döndü, CalculiX hiç kurulmadı ve hata ancak solver
#     çalıştırılmaya kalkışıldığında fark edildi.
FROM mcr.microsoft.com/devcontainers/universal:2

USER root

# Universal image'da bozuk üçüncü parti apt depoları bulunabiliyor (yarn
# deposunun imzası doğrulanamıyor). Bunlar projeyle ilgisiz; `apt-get update`
# komutunun tamamını düşürmemeleri için temizleniyor.
RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn.sources || true

RUN apt-get update && apt-get install -y --no-install-recommends \
    # CalculiX çözücü (ccx)
    calculix-ccx \
    # gmsh'in Python paketi başsız çalışsa bile bu paylaşımlı kütüphaneleri
    # dlopen eder; eksikse `import gmsh` anında OSError verir:
    #   OSError: libGLU.so.1: cannot open shared object file
    libglu1-mesa \
    libxcursor1 \
    libxinerama1 \
    libxft2 \
    libxrender1 \
    libxi6 \
    && rm -rf /var/lib/apt/lists/*

# Kurulumun gerçekten çalıştığını IMAGE BUILD sırasında doğrula — sessizce
# eksik bir ortamla başlamaktansa build'in patlaması yeğdir.
RUN which ccx && ldconfig -p | grep -q libGLU

USER codespace
