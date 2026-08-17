# Windows Support Implementation Report

Tarih: 2026-05-04

Bu rapor, `windows_support_agent_plan.md` kapsamında uygulanan Windows destek çalışmasını ve aynı çalışma dalında yer alan operator panel UI iyileştirmelerini özetler.

## Kapsam

Bu çalışmanın ana hedefleri:

- Windows ortamında core CLI, operator panel ve bundled runtime akışlarını desteklenebilir hale getirmek.
- Windows tarafında live computer-use otomasyonunu güvenli biçimde fail-closed bırakmak.
- Tauri bridge katmanını Windows path, environment ve bundled Python düzenine uyumlu hale getirmek.
- Windows CI ve release hazırlık süreçlerini tanımlamak.
- Operator panel UI tarafında Mission Control kalitesine yaklaşan daha tutarlı, geniş ve profesyonel bir arayüz sağlamak.

## Platform ve Runtime Katmanı

Yeni `imperaos/runtime/platform.py` modülü eklendi. Bu modül işletim sistemini merkezi olarak algılar ve platforma göre güvenli varsayılanlar üretir:

- `current_platform()`
- `platform_label()`
- `is_windows()`, `is_macos()`, `is_linux()`
- `default_temp_dir()`
- `default_download_dir()`
- `safe_allowed_roots()`

Bu sayede daha önce Unix/macOS varsayımlarına dayanan `os.uname()` ve `/tmp` gibi kullanımlar kaldırıldı. Windows, macOS ve Linux için platform davranışı tek bir yardımcı katmanda toplandı.

## Computer-Use Güvenlik Sınırı

`imperaos/computer_use/runtime.py` Windows uyumluluğu için yeniden düzenlendi.

Önemli davranışlar:

- Windows live computer-use varsayılan olarak etkinleştirilmedi.
- Windows ortamında scaffold/default adapter kullanılıyorsa çalışma `WINDOWS_COMPUTER_USE_NOT_QUALIFIED` reason code ile fail-closed kapanır.
- macOS dışındaki diğer platformlarda da nitelendirme yoksa `COMPUTER_USE_PLATFORM_NOT_QUALIFIED` ile fail-closed davranışı korunur.
- Testlerde kullanılan explicit fake adapter enjeksiyonları kırılmayacak şekilde sınırlandırma adapter bağlamına göre uygulandı.
- Readiness raporu artık platform, desteklenen yüzeyler ve computer-use boundary bilgisi döndürüyor.

Bu karar bilinçlidir: Windows paketleme ve operator panel desteği ilerletildi, fakat Windows live computer-use otomasyonu gerçek qualification raporu olmadan açılmadı.

## CLI ve Contract Güncellemeleri

`imperaos/cli.py` içinde `operator capabilities` çıktısı platform-aware hale getirildi.

Windows çıktısı artık computer-use için şu bilgileri açıkça döndürüyor:

- `enabled: false`
- `stage: not_qualified`
- `platform: windows`
- `scope: core+operator_panel+bundled_runtime`
- `adapterStatus: windows_scaffold`
- `reasonCode: WINDOWS_COMPUTER_USE_NOT_QUALIFIED`

`doctor` komutu `--json` / `--no-json` seçeneklerini kabul edecek şekilde düzenlendi ve varsayılan JSON davranışı korundu.

`imperaos/contracts/operator_panel.py` içinde operator panel capability contract alanları genişletildi:

- `reasonCode`
- `summary`

## Local Search Dayanıklılığı

`imperaos/tools/local_search.py` içinde `rg` çağrısı Windows ortamında `PermissionError` / `OSError` ürettiğinde Python tabanlı fallback aramaya düşecek şekilde iyileştirildi.

Bu değişiklik yerel geliştirme ortamında görülen `rg.exe` erişim engeli problemini tolere eder.

## Team Artifacts Stabilitesi

`imperaos/team/artifacts.py` içindeki `write_status()` işlemi Windows dosya kilidi davranışına karşı güçlendirildi.

Uygulanan değişiklikler:

- Status JSON artık önce geçici dosyaya yazılıyor.
- Sonrasında atomik replace yapılıyor.
- Windows tarafında kısa süreli reader lock durumları için retry uygulanıyor.

Bu, testlerde görülebilecek boş veya kısmi `status.json` okuma riskini azaltır.

## Tauri Bridge Güncellemeleri

`apps/operator-panel/src-tauri/src/bridge.rs` Windows bundled runtime desteği için genişletildi.

Eklenen başlıca davranışlar:

- Windows bundled Python yolu:
  - `imperaos-runtime/python/Scripts/python.exe`
- POSIX bundled Python yolu:
  - `imperaos-runtime/python/bin/python`
- Platform-aware resource directory çözümleme.
- Platform-aware PATH separator.
- `env_clear()` sonrası Windows için gerekli environment değişkenlerinin korunması:
  - `SystemRoot`
  - `WINDIR`
  - `USERPROFILE`
  - `APPDATA`
  - `LOCALAPPDATA`
  - `PROGRAMDATA`
  - `TEMP`
  - `TMP`
  - `ComSpec`
  - `PATHEXT`
  - `PROCESSOR_ARCHITECTURE`
  - `NUMBER_OF_PROCESSORS`

Komut çalıştırma tarafında shell passthrough eklenmedi. Bridge hâlâ executable + args modeliyle çalışıyor.

## Windows Bundled Runtime Scripti

Yeni script eklendi:

- `apps/operator-panel/scripts/build_bundled_runtime_windows.ps1`

Scriptin görevi:

- Wheel yoksa Python wheel build etmek.
- `src-tauri/resources/imperaos-runtime` klasörünü temizlemek.
- `python` altında venv oluşturmak.
- Windows entrypoint olarak `python/Scripts/python.exe` doğrulamak.
- ImperaOS wheel kurmak.
- `python.exe -m imperaos --version` smoke testi çalıştırmak.
- Runtime manifest ve README üretmek.

Script PowerShell parser ile doğrulandı. Yerelde tam çalıştırılmadı; çünkü repo içine büyük bir embedded venv üretir. CI içinde gerçek paketleme ve doğrulama adımı olarak çalışacak şekilde workflow'a eklendi.

## Tauri Platform Config Dosyaları

Yeni platform config dosyaları eklendi:

- `apps/operator-panel/src-tauri/tauri.macos.conf.json`
- `apps/operator-panel/src-tauri/tauri.windows.conf.json`

Windows config tarafında NSIS installer hedefi tanımlandı.

## CI ve Release Workflow'ları

Yeni Windows CI workflow'u eklendi:

- `.github/workflows/windows-ci.yml`

Bu workflow şu kontrolleri içerir:

- Python 3.11 / uv setup
- Ruff
- Pytest
- Core CLI smoke
- Operator panel test, lint ve build
- Rust / Cargo test
- Windows bundled runtime build ve verify
- Tauri debug no-bundle smoke

Yeni Windows release workflow'u eklendi:

- `.github/workflows/operator-panel-release-windows.yml`

Bu workflow:

- Manuel dispatch ve `operator-panel-v*` tag akışıyla çalışır.
- Windows unsigned NSIS artifact üretimini hedefler.
- Signing secret yoksa release imzalı gibi davranmaz; signing gate açıkça blocked status üretir.

## Dokümantasyon Güncellemeleri

Aşağıdaki dokümanlar Windows destek sınırları ve release gate bilgileriyle güncellendi:

- `README.md`
- `INSTALL.md`
- `DEPLOYMENT_GUIDE.md`
- `QUALIFICATION_MATRIX.md`
- `apps/operator-panel/README.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/RELEASE_GATE_v0.5.md`
- `apps/operator-panel/src-tauri/resources/imperaos-runtime/README.txt`

Dokümanlarda özellikle şu sınır açık bırakıldı:

- Windows core/operator panel/bundled runtime/installer smoke desteklenir.
- Windows live computer-use automation qualification tamamlanmadan etkin değildir.

## Operator Panel UI İyileştirmeleri

Bu çalışma dalında daha önce istenen UI iyileştirmeleri de yer alıyor.

Yapılan başlıca değişiklikler:

- Sidebar daraltma butonu çalışır hale getirildi.
- Ana içerik alanı geniş ekranlarda daha verimli kullanılacak şekilde genişletildi.
- Mission Control dışındaki sayfalar için premium component stilleri eklendi.
- Çalıştırmalar, görevler, onaylar, yürütmeler, sistem sağlığı, kaynaklar, bağlantılar, ayarlar, loglar ve raporlar sayfaları daha tutarlı kart, toolbar, liste ve durum bileşenleriyle güçlendirildi.
- Mobil ve dar ekran davranışları için responsive stiller eklendi.

Bu UI değişiklikleri özellikle şu dosyalarda yoğunlaştı:

- `apps/operator-panel/src/App.tsx`
- `apps/operator-panel/src/components/shell/AppShell.tsx`
- `apps/operator-panel/src/components/shell/Sidebar.tsx`
- `apps/operator-panel/src/styles/premium-components.css`
- `apps/operator-panel/src/styles/premium-mission.css`
- `apps/operator-panel/src/styles/premium-shell.css`

## Test Kapsamı

Yeni ve güncellenen testler:

- `tests/test_platform_compat.py`
- `tests/test_computer_use_runtime.py`
- `tests/test_team_cli.py`
- `tests/test_operator_contracts.py`
- Rust bridge unit testleri

Eklenen test kapsamı:

- Windows platform mapping.
- Safe allowed roots davranışı.
- Windows readiness fail-closed raporu.
- Windows scaffold adapter ile live run engelleme.
- `local_search` fallback davranışı.
- Platform-aware operator capabilities contract.
- Tauri bridge bundled Python path çözümleme.
- Platform-aware PATH separator.
- Windows external script spawn davranışı.

## Çalıştırılan Doğrulamalar

Aşağıdaki doğrulamalar başarıyla tamamlandı:

```powershell
uv run ruff check .
uv run python -m pytest -q
corepack pnpm --dir apps/operator-panel test
corepack pnpm --dir apps/operator-panel lint
corepack pnpm --dir apps/operator-panel build
cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
cargo fmt --manifest-path apps/operator-panel/src-tauri/Cargo.toml --check
uv run python -m imperaos --version
uv run python -m imperaos operator capabilities --json
uv run python -m imperaos doctor --profile balanced --json
```

PowerShell script parse kontrolü de başarıyla tamamlandı.

## Bilinen Sınırlar

- Windows bundled runtime scripti yerelde tam çalıştırılmadı; büyük bir embedded venv üreteceği için bu adım CI workflow'una bırakıldı.
- Windows installer signing tamamlanmış gibi işaretlenmedi. Signing secret yoksa release workflow açıkça blocked status üretir.
- Windows live computer-use automation etkin değildir. Qualification raporu ve platform testleri tamamlanmadan açılmamalıdır.

## Sonuç

Windows desteği core/operator panel/bundled runtime hattında güvenli ve testlenebilir bir baseline seviyesine getirildi. Live computer-use tarafı bilinçli olarak kapalı bırakıldı ve ürün/CI/dokümantasyon katmanlarında bu sınır açık şekilde ifade edildi. Operator panel arayüzü de önceki geri bildirimlere uygun biçimde daha geniş, tutarlı ve Mission Control çizgisine yakın bir UI sistemine taşındı.
