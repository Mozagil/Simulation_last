# Geliştirme container'ı — sistem bağımlılıkları BURAYA gömülür.
#
# Neden Dockerfile, neden postCreateCommand değil:
#   * Bu katmanlar image'a yazılır ve ÖNBELLEKLENİR. Yeni bir Codespace
#     açıldığında (özellikle prebuild açıksa) tekrar kurulmazlar.
#   * postCreateCommand her container oluşturmada baştan çalışır ve bir
#     adımı patlarsa SONRAKİLERİN HEPSİ ATLANIR.
#
# Neden `universal:2` değil:
#   universal image ~10 GB (torch, conda, her dil için toolchain). Üstüne
#   katman yazınca Codespace diski doluyordu:
#     ERROR: failed to register layer: ... no space left on device
#   ve Codespaces sessizce "recovery container"a düşüyordu — npm/gh/ccx
#   olmayan, port tüneli yarım çalışan bir ortam. Bu projeye Python 3.12 +
#   Node + Docker yetiyor; onlar devcontainer.json'daki `features` ile geliyor.
FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    # CalculiX çözücü (ccx)
    calculix-ccx \
    # gmsh'in Python paketi başsız çalışsa bile bu paylaşımlı kütüphaneleri
    # dlopen eder; eksikse `import gmsh` anında OSError verir:
    #   OSError: libGL.so.1: cannot open shared object file
    # Liste `ldd libgmsh.so` çıktısından; universal image'da hepsi hazırdı,
    # ince python image'da tek tek kurulmalı.
    libgl1 \
    libglu1-mesa \
    libx11-6 \
    libxext6 \
    libxfixes3 \
    libxrender1 \
    libxcursor1 \
    libxinerama1 \
    libxft2 \
    libxi6 \
    libfontconfig1 \
    libfreetype6 \
    # OpenRadioss gf ikilisi (gfortran runtime + zip açmak)
    libgfortran5 \
    libgomp1 \
    unzip \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# OpenRadioss resmi Linux paketi (~80MB). Kaynak derleme yok; lisans sunucusu yok.
COPY .devcontainer/install_openradioss.sh /tmp/install_openradioss.sh
RUN chmod +x /tmp/install_openradioss.sh && /tmp/install_openradioss.sh \
    && rm /tmp/install_openradioss.sh

# Kurulumun gerçekten çalıştığını IMAGE BUILD sırasında doğrula — sessizce
# eksik bir ortamla başlamaktansa build'in patlaması yeğdir.
RUN which ccx \
    && test -x /opt/openradioss/exec/starter_linux64_gf \
    && test -x /opt/openradioss/exec/engine_linux64_gf \
    && ldconfig -p | grep -q libGL.so.1 && ldconfig -p | grep -q libGLU

# python devcontainer image'ının varsayılan kullanıcısı (universal'da `codespace`).
USER vscode
