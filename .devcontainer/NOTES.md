# devcontainer.json notları

Yorumlar bu dosyada tutuluyor. `devcontainer.json` **geçerli JSON
olmak zorunda** — `//` yorumları VS Code'un kabul ettiği JSONC
uzantısıdır, ama GitHub Codespaces'in yapılandırma tarayıcısı dosyayı
ayrıştıramayıp sessizce `mcr.microsoft.com/devcontainers/base:alpine`
imajına düşüyor. Sonuç: Dockerfile hiç çalışmıyor, ccx/gmsh/Node yok.

(2026-10-08'de bu yaşandı; creation.log'da `$alpine -c echo Container
started` satırı kanıt. Rebuild ve yeniden oluşturma işe yaramadı,
çünkü sorun seçimde değil ayrıştırmadaydı.)

## Kararların gerekçeleri

- **build.dockerfile**: Hazır image yerine kendi Dockerfile'ımız.
  Sistem bağımlılıkları (CalculiX, gmsh'in libGLU'su) image katmanına
  gömülür ve önbelleklenir. Eskiden postCreateCommand'daydı ve tek bir
  apt hatası hepsini atlıyordu.

- **features**: Taban image ince (python:3.12); Node, gh ve Docker
  buradan geliyor. docker-in-docker: Postgres `docker compose` ile
  ayağa kalkıyor.

- **postCreateCommand**: Proje bağımlılıkları image'a gömülemez
  (çalışma alanı ancak container oluşturulduktan sonra bağlanır).
  `|| true` YOK: bir kurulum patlarsa sessizce devam etmek yerine
  kurulum log'unda görünsün.

- **postStartCommand**: Her başlatmada .env üretir, Postgres/backend/
  frontend'i kaldırır, 5173 ve 8000'i public yapar.

- **forwardPorts YOK**: Önceden kayıtlı port girişleri uyku/uyanma
  döngüsünde bayatlıyor, proxy boş 404 veriyordu. Portlar süreç
  dinlemeye başlayınca otomatik yakalanıyor; etiketler
  portsAttributes'ta.
