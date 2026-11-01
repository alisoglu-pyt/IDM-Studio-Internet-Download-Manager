<p align="center">
  <img src="packaging/idm-studio.svg" width="88" alt="IDM Studio simgesi">
</p>

<h1 align="center">IDM Studio</h1>

<p align="center">
  <b>Türkçe</b> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <b>Material 3 görünümlü, çok bağlantılı masaüstü indirme yöneticisi</b><br>
  Python 3.10+ · Tkinter · Sıfır harici bağımlılık · 16 dil
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+"></a>
  <img src="https://img.shields.io/badge/Tkinter-Material%203-FF6F00?logo=python&logoColor=white" alt="Tkinter ve Material 3">
  <img src="https://img.shields.io/badge/ba%C4%9F%C4%B1ml%C4%B1l%C4%B1k-s%C4%B1f%C4%B1r-2E7D32" alt="Sıfır harici bağımlılık">
  <img src="https://img.shields.io/badge/diller-16-6750A4" alt="16 dil">
  <a href="LICENSE"><img src="https://img.shields.io/badge/lisans-MIT-8A2BE2" alt="MIT Lisansı"></a>
</p>

<p align="center">
  IDM Studio; büyük dosyaları birden fazla bağlantıyla indiren, indirmeleri duraklatıp kaldığı yerden sürdürebilen
  ve tüm süreci canlı istatistiklerle gösteren bir masaüstü uygulamasıdır.<br>
  Arayüzü Material Design 3 paletinden ilham alır; indirme motoru yalnızca Python standart kütüphanesini kullanır.
</p>

> **Kısaca:** 1–10 arası eşzamanlı parça, güvenli duraklat/devam, otomatik kurtarma, açık/koyu tema,
> 16 dilli arayüz ve hazır Linux paketleri.

## İçindekiler

- [Ekran görüntüleri](#ekran-görüntüleri)
- [Öne çıkan özellikler](#öne-çıkan-özellikler)
- [Hızlı başlangıç](#hızlı-başlangıç)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Klavye kısayolları](#klavye-kısayolları)
- [Proje yapısı](#proje-yapısı)
- [Nasıl çalışır?](#nasıl-çalışır)
- [Paket üretimi](#paket-üretimi)
- [Sorun giderme](#sorun-giderme)
- [Bilinen sınırlamalar](#bilinen-sınırlamalar)
- [Katkı](#katkı)
- [Lisans](#lisans)

## Ekran görüntüleri

### İndirme sırasında canlı istatistikler

<p align="center">
  <img src="docs/screenshots/download-progress.png" width="900" alt="IDM Studio'da devam eden indirme; ilerleme çubuğu, hız, boyut ve kalan süre">
  <br>
  <sub>Aktif indirme kartında hız, yüzde, indirilen/toplam boyut ve tahmini kalan süre anlık olarak güncellenir.</sub>
</p>

### Açık ve koyu tema

<table align="center">
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/main-light.png" width="440" alt="Açık temada IDM Studio ana penceresi">
      <br>
      <sub><b>Açık tema</b></sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/main-dark.png" width="440" alt="Koyu temada IDM Studio ana penceresi">
      <br>
      <sub><b>Koyu tema</b></sub>
    </td>
  </tr>
</table>

<p align="center">
  <sub>Tema, üst çubuktaki güneş/ay simgesiyle tek tıkla değiştirilir ve tercih sonraki açılışta korunur.</sub>
</p>

### Yeni indirme penceresi

<p align="center">
  <img src="docs/screenshots/new-download-dark.png" width="620" alt="IDM Studio yeni indirme penceresi; URL, dosya adı, kayıt klasörü ve parça sayısı">
  <br>
  <sub>Bağlantı, isteğe bağlı dosya adı, kayıt klasörü ve 1–10 arası parça sayısı tek pencerede seçilir.</sub>
</p>

## Öne çıkan özellikler

### Hızlı ve dayanıklı indirme motoru

- **Çok parçalı indirme:** Büyük dosyalar 1–10 eşzamanlı parçaya bölünür. Varsayılan 4 bağlantıdır; son seçilen değer hatırlanır.
- **Sunucu yeteneğini doğrulama:** İndirme başlamadan önce `HEAD` isteği ve 1 baytlık `Range` denemesiyle sunucunun aralıklı indirmeyi gerçekten destekleyip desteklemediği kontrol edilir.
- **Duraklat / devam ettir:** Kısmi veriler `.idm-*.part` dosyalarında tutulur; devam ederken yalnızca eksik bayt aralığı istenir.
- **Otomatik kurtarma:** Uygulama kapanırsa yarım kalan indirmeler bir sonraki açılışta duraklatılmış olarak geri gelir.
- **Güvenli birleştirme:** Parçalar önce geçici bir dosyada birleştirilir, ardından `os.replace` ile hedefe taşınır. Böylece yarım kalan birleştirme mevcut dosyanızı bozmaz.
- **Tek akışa geri dönüş:** Sunucu `Range` desteklemiyorsa veya dosya parçalamak için çok küçükse indirme tek bağlantıyla tamamlanır.
- **Anlaşılır hatalar:** HTTP hataları, zaman aşımı, bağlantı kopması ve disk hataları kullanıcıya sade mesajlarla gösterilir; hatalı indirmeler kart üzerinden yeniden denenebilir.

### Material 3 arayüz

- **Açık ve koyu tema:** Material 3 renk paletleri arasında tek tıkla geçiş.
- **Canlı istatistikler:** Hız, yüzde, boyut, kalan süre ve durum bilgisi kartlarda anlık güncellenir.
- **Kütüphane filtreleri:** Tüm indirmeler, indiriliyor, tamamlananlar ve bekleyenler için sol kenar çubuğu.
- **Modern bileşenler:** Yuvarlatılmış kartlar, Canvas ile çizilmiş vektörel ikonlar, snackbar bildirimleri, özel metin alanları ve ince kaydırma çubuğu.
- **Kart eylemleri:** Duraklat, devam ettir, iptal et, klasörü aç, listeden kaldır veya tamamlanan dosyayı çift tıklayarak aç.
- **Hakkında penceresi:** Sürüm, geliştirici ve iletişim bilgileri; `F1` ile açılır.

### Dil, kalıcılık ve günlük kullanım

- **16 dilli arayüz:** Türkçe, İngilizce, Almanca, Fransızca, İtalyanca, Portekizce, İspanyolca, Azerice, Türkmence, Rusça, Ukraynaca, Fince, İsveççe, Japonca, Korece ve Çince. Dil, üst çubuktaki dünya simgesinden veya `Ctrl+L` ile değiştirilir.
- **Sistem dilini algılama:** Kayıtlı bir tercih yoksa sistem yerel ayarına uygun dil seçilir.
- **Hatırlanan tercihler:** Tema, dil, son kayıt klasörü ve parça sayısı `~/.config/idm-studio/state.json` içinde saklanır.
- **Çevrimdışı çeviriler:** Tüm arayüz metinleri uygulamanın içine gömülüdür; sistemde ilgili dil paketi kurulu olmasa da arayüz eksiksiz görüntülenir.

## Hızlı başlangıç

Tek gereksinim **Python 3.10+** ve **Tkinter**'dır. Harici Python paketi kurmanız gerekmez.

```bash
cd internet-download-manager
./run.sh
```

Alternatif olarak doğrudan Python ile başlatın:

```bash
python3 main.py
```

`run.sh` çalışmıyorsa:

```bash
chmod +x run.sh
./run.sh
```

> Linux'ta Tkinter ayrı bir paket olabilir. Tek satırlık kurulum komutları için
> [Kurulum](#kurulum) bölümüne bakın. Uygulama grafik bir masaüstü oturumu gerektirir;
> SSH üzerinden çalıştırırken X11 yönlendirmesi veya sanal ekran kullanılmalıdır.

## Kurulum

### Gereksinimler

| Bileşen | Gereksinim |
| --- | --- |
| Python | 3.10 veya üzeri |
| Arayüz | Tkinter (Windows/macOS resmî Python kurulumlarıyla birlikte gelir) |
| İşletim sistemi | Linux, Windows veya macOS |
| Harici Python paketi | Yok |

### Linux'ta Tkinter

Debian / Ubuntu / Linux Mint:

```bash
sudo apt install python3-tk
```

Fedora:

```bash
sudo dnf install python3-tkinter
```

Arch / Manjaro:

```bash
sudo pacman -S tk
```

### Kaynaktan çalıştırma

Depoyu klonlayın veya ZIP olarak indirin, ardından proje klasöründe:

```bash
./run.sh
```

veya:

```bash
python3 main.py
```

### Hazır Linux paketleri

Hazır çıktılar `dist/` klasöründe bulunur.

| Paket | Dosya | Not |
| --- | --- | --- |
| Debian / Ubuntu | `dist/idm-studio_1.0.0_all.deb` | `python3-tk` ve `xdg-utils` bağımlılıklarını otomatik kurar, masaüstü menüsüne ekler. |
| AppImage | `dist/IDM-Studio-1.0.0-x86_64.AppImage` | Python ve Tkinter çalışma zamanını içinde taşır; kurulum gerektirmez. |

#### Debian / Ubuntu (.deb)

```bash
sudo apt install ./dist/idm-studio_1.0.0_all.deb
idm-studio
```

Kurulumdan sonra uygulama, masaüstü menüsünde **IDM Studio** adıyla da görünür.

#### AppImage

```bash
chmod +x dist/IDM-Studio-1.0.0-x86_64.AppImage
./dist/IDM-Studio-1.0.0-x86_64.AppImage
```

Sistemde FUSE yoksa:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./dist/IDM-Studio-1.0.0-x86_64.AppImage
```

#### Paket bütünlüğünü doğrulama

```bash
cd dist
sha256sum -c SHA256SUMS
```

## Kullanım

### İlk indirme

1. Sağ üstteki **Yeni İndirme** düğmesine tıklayın (veya `Ctrl+N`).
2. Bir `http://` veya `https://` bağlantısı yapıştırın. Şema yoksa `https://` otomatik eklenir.
3. İsterseniz dosya adını ve kayıt klasörünü değiştirin.
4. Parça sayısını seçin (1–10 arası; son seçim hatırlanır).
5. **İndirmeyi Başlat**'a tıklayın.

### İndirme kartı

İndirme kartındaki düğmelerle işlemi duraklatabilir, devam ettirebilir, iptal edebilir,
tamamlanan dosyanın klasörünü açabilir veya kaydı listeden kaldırabilirsiniz.
Tamamlanmış bir karta çift tıklamak dosyayı varsayılan uygulamada açar.

Hata durumunda kartta **Tekrar dene** düğmesi görünür. İptal edilen indirmelerin geçici
parça dosyaları temizlenir; duraklatılan indirmelerin parçaları korunur.

### Dil ve tema

- Üst çubuktaki dünya simgesi (veya `Ctrl+L`) 16 dilli menüyü açar.
- Güneş/ay simgesi açık ve koyu tema arasında geçiş yapar.
- Seçimler anında uygulanır; tüm pencereler, kart durumları, birimler ve tarihler yeni dile uyarlanır.

### Hakkında

Sol alt köşedeki **Hakkında** öğesi (veya `F1`), sürüm, geliştirici ve iletişim bilgilerini
gösteren pencereyi açar.

## Klavye kısayolları

| Kısayol | İşlev |
| --- | --- |
| `Ctrl+N` | Yeni indirme penceresi |
| `Ctrl+L` | Dil menüsü |
| `Esc` | Yeni indirme penceresini kapat |
| `Enter` | Bağlantı alanındayken indirmeyi başlat |
| `F1` | Hakkında penceresi |

## Proje yapısı

```text
internet-download-manager/
├── main.py                  # Giriş noktası ve Tkinter kontrolü
├── idm_studio/
│   ├── app.py               # Ana pencere, tema, filtreler, durum yönetimi
│   ├── downloader.py        # Parçalı indirme motoru (thread + Range)
│   ├── cards.py             # İndirme kartlarının Canvas çizimi
│   ├── dialogs.py           # Yeni indirme ve hakkında diyalogları
│   ├── i18n.py              # 16 dilli arayüz metinleri ve dil seçimi
│   ├── widgets.py           # Material buton, giriş alanı, snackbar, scrollbar…
│   ├── draw.py              # Yuvarlatılmış şekiller ve vektörel ikonlar
│   ├── theme.py             # Material 3 renk paleti ve fontlar
│   ├── utils.py             # Biçimlendirme ve dosya yardımcıları
│   └── __init__.py          # Sürüm bilgisi
├── packaging/
│   ├── build_deb.sh         # Debian paketi üretimi
│   ├── build_appimage.sh    # PyInstaller + AppImage üretimi
│   ├── build_all.sh         # İki paketi birlikte üretir
│   ├── idm-studio.desktop   # Masaüstü kısayolu
│   ├── idm-studio.svg       # Vektörel uygulama simgesi
│   └── idm-studio-256.png   # PNG uygulama simgesi
├── docs/
│   └── screenshots/         # Türkçe ve İngilizce README görselleri
├── dist/                    # Üretilen .deb, AppImage ve SHA256SUMS
├── requirements.txt         # Harici bağımlılık yok
├── run.sh                   # Hızlı başlatma betiği
├── LICENSE                  # MIT lisansı
├── README.md                # Türkçe README
└── README.en.md             # İngilizce README
```

## Nasıl çalışır?

### 1. Sunucu keşfi

İndirme motoru önce `HEAD` isteğiyle dosya boyutunu, dosya adını (`Content-Disposition`),
içerik türünü ve yönlendirilmiş nihai URL'yi öğrenir. Ardından `Range: bytes=0-0` isteğiyle
sunucunun gerçekten `206 Partial Content` döndürüp döndürmediğini doğrular. Bu sayede
`Accept-Ranges` başlığına körü körüne güvenilmez.

### 2. Parçalama ve indirme

Sunucu aralıklı indirmeyi destekliyorsa ve dosya yeterince büyükse içerik, seçilen bağlantı
sayısına göre en fazla 10 parçaya bölünür. Her parça kendi iş parçacığında `Range` başlığıyla
indirilir ve 256 KB'lık parçalar hâlinde diske yazılır. Dosya 1 MB'ın altındaysa veya sunucu
`Range` desteklemiyorsa tek akış kullanılır.

### 3. Duraklatma ve kurtarma

Her parça, indirme klasöründe `.idm-<görev-id>.part<N>` biçiminde saklanır. Duraklatıldığında
bu dosyalar korunur; devam edildiğinde mevcut boyut okunur ve `Range: bytes=mevcut-...` ile
kaldığı yerden sürdürülür. Uygulama kapanırsa görev listesi `state.json` içinden yüklenir ve
yarım kalan indirmeler duraklatılmış durumda geri gelir.

### 4. Birleştirme

Tamamlanan parçalar `.idm-<görev-id>.merged` adlı geçici bir dosyada birleştirilir. Birleştirme
başarıyla biterse dosya `os.replace` ile hedef konuma taşınır. Birleştirme sırasında uygulama
kapanır veya iptal edilirse hedef dosya değişmez.

### 5. Arayüz ve kalıcılık

Tüm ağ işlemleri arka plan iş parçacıklarında yapılır. Görevlerden gelen güncellemeler bir `queue`
üzerinden ana Tkinter iş parçacığına aktarılır; böylece arayüz donmaz. İndirme listesi, tema, dil,
son klasör ve parça sayısı atomik olarak `~/.config/idm-studio/state.json` dosyasına yazılır.

### 6. Bağımlılıksız yapı

Projede üçüncü taraf Python paketi kullanılmaz. İndirme işlemleri `urllib`, `http.client` ve
`threading`; arayüz ise yalnızca Tkinter ve standart kütüphane ile geliştirilmiştir.
`requirements.txt` bu nedenle yalnızca bilgilendirme amaçlıdır.

## Paket üretimi

Debian/Ubuntu derleme ortamında iki paketi birlikte üretmek için:

```bash
./packaging/build_all.sh
```

Yalnızca bir paket üretmek için:

```bash
./packaging/build_deb.sh
./packaging/build_appimage.sh
```

- `.deb` paketi yalnızca `dpkg-deb` ile, root yetkisi gerektirmeden üretilir.
- AppImage, PyInstaller ile Python/Tkinter çalışma zamanını paketler.
- Derleme sisteminde Tkinter veya PyInstaller yoksa `build_appimage.sh`, Debian/Ubuntu üzerinde
  gerekli paketleri `.build/` altına indirip yerel araç zinciri kurar; `sudo` gerekmez.
  İnternet bağlantısı gerekir veya `sudo apt install python3-tk pyinstaller` ile sistem kurulumu
  yapılabilir.
- Çıktılar ve SHA256 özetleri `dist/` altında oluşur.

## Sorun giderme

| Sorun | Çözüm |
| --- | --- |
| `ModuleNotFoundError: No module named 'tkinter'` | Dağıtımınıza uygun Tkinter paketini kurun: `sudo apt install python3-tk`, `sudo dnf install python3-tkinter` veya `sudo pacman -S tk`. |
| `Grafik ekranı bulunamadı (DISPLAY değişkeni yok)` | Uygulamayı grafik masaüstü oturumunda çalıştırın; SSH kullanıyorsanız `ssh -X` veya `xvfb-run` deneyin. |
| AppImage açılmıyor | Dosyaya çalıştırma izni verin: `chmod +x dist/IDM-Studio-1.0.0-x86_64.AppImage`. FUSE hatası varsa `APPIMAGE_EXTRACT_AND_RUN=1` ile başlatın. |
| "Sunucu aralıklı indirmeyi desteklemiyor" | Parça sayısını 1 yaparak tek bağlantıyla indirin. Sunucu `Range` başlığını desteklemiyor olabilir. |
| İndirme 0 B/s'de kalıyor | Sunucu bağlantıyı kapatmış veya ağ kesilmiş olabilir. Karttaki **Tekrar dene** düğmesini kullanın. |
| Ayarlar bozuldu / eski indirmeler görünmüyor | `~/.config/idm-studio/state.json` dosyasını yedekleyip silin; uygulama temiz bir durumla açılır. |

## Bilinen sınırlamalar

- Yalnızca HTTP ve HTTPS desteklenir; FTP, BitTorrent veya video platformu entegrasyonu yoktur.
- Tarayıcı eklentisi, panodan otomatik bağlantı yakalama veya zamanlanmış indirme özelliği yoktur.
- Otomatik yeniden deneme yoktur; hatalı indirmeler kart üzerindeki **Tekrar dene** ile sürdürülür.
- Hazır `.deb` ve AppImage paketleri Linux içindir. Windows ve macOS'ta uygulama kaynaktan
  çalıştırılabilir; bu platformlar için hazır paket üretilmemiştir.
- Arayüz Tkinter tabanlıdır; platformlar arasında küçük görsel farklılıklar görülebilir.

## Katkı

Katkılar memnuniyetle karşılanır.

1. Depoyu çatallayın (fork) ve yeni bir dal oluşturun.
2. Değişikliğinizi mevcut kod stiline uygun şekilde yapın.
3. Arayüz metni ekliyorsanız `idm_studio/i18n.py` içindeki dil sözlüklerine karşılık gelen çevirileri ekleyin.
4. Arayüzü elle çalıştırıp test edin; ardından anlaşılır bir commit mesajıyla pull request açın.

Hızlı sözdizimi kontrolü:

```bash
python3 -m compileall idm_studio main.py
```

## Lisans

Bu proje MIT Lisansı ile sunulmuştur; ayrıntılar için [`LICENSE`](LICENSE) dosyasına bakın.

İndirdiğiniz içeriklerin telif haklarına ve hedef sunucunun kullanım koşullarına uymak
sizin sorumluluğunuzdadır.

---

<p align="center">
  <sub>Geliştirici: <b>Bekir Alişoğlu</b> · <a href="mailto:alisoglu@yahoo.com">alisoglu@yahoo.com</a></sub>
</p>
