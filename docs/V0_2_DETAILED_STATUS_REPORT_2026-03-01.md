# ImperaOS AI v0.2 — Kapsamlı Güncel Durum Raporu

**Tarih:** 1 Mart 2026  
**Rapor türü:** Uygulama sonrası teknik durum raporu (CLI-first reliability beta)  
**Sürüm hedefi:** v0.2.0

---

## 1. Yönetici Özeti

Bu güncelleme ile ImperaOS AI, v0.1 çalışan çekirdekten v0.2 güvenilir beta seviyesine yükseltildi.

Bu rapor döneminde tamamlanan ana hedefler:

1. Config çözümleme davranışı deterministik hale getirildi (`defaults < profile < env < CLI`).
2. Planner adversarial dayanıklılığı güçlendirildi (strict schema + repair + deterministic reason code).
3. Expert çıktı kontratları runtime’da doğrulanır hale getirildi (invalid payload -> `partial` failover).
4. `balanced` profilde aktif router `rule`, shadow router `sltc` olacak şekilde yeni ürün varsayılanı uygulandı.
5. Fast-path için regret izleme metrikleri eklendi.
6. Benchmark katmanı `smoke/quality` ayrımıyla üretimleştirildi; quality set 120 görevle eklendi.
7. Energy raporlama şeması measured/estimated ayrımı net olacak şekilde genişletildi.
8. Makine-okunur artifact standardı devreye alındı (`artifacts/*.json`).
9. Privacy & safety regression kapsamı güçlendirildi.
10. CLI structured output modları eklendi (`--json`, `--json-stream`, `--stdio-json`).
11. Dokümantasyon ve CI v0.2 release gate ile hizalandı.

Mevcut teknik sonuç:

- `ruff` temiz.
- Test seti geçti (59 test).
- `doctor`, benchmark ve research uçları çalışır.
- Quality ablation 120 görevle koşulabilir.

---

## 2. v0.2 Scope Kararlarının Uygulanma Durumu

Bu sürümde kilitlenen kararların uygulama karşılığı:

1. **CLI-first / UI defer**: Uygulandı. Desktop thin-shell UI v0.2 kapsamı dışına alındı.
2. **Balanced router politikası**: Uygulandı. `rule` aktif, `sltc` shadow.
3. **120 task quality gate**: Uygulandı. `benchmarks/tasks/quality/quality_tasks.jsonl` içinde 120 görev tanımlı.

---

## 3. Mimari Akış (Güncel)

### 3.1 Ürün yolu (default)

1. CLI user input alır.
2. Kısa/greeting mesajlarda fast-path aday kontrolü yapılır.
3. Fast-path uygunsa tek çağrı (isteğe bağlı token stream) ile cevap üretilir.
4. Normal path’te planner strict JSON üretir.
5. Aktif router (balanced: rule) karar verir.
6. Shadow router (balanced: sltc) paralel karar üretir (telemetry-only).
7. Expert çağrıları guardrail’lerle yürütülür (timeout/retry/tool budget/recursion/circuit breaker).
8. LLM synthesis/adjudication final yanıtı üretir.
9. Memory gate kalıcı yazım kararını verir.
10. Telemetry + artifact özetleri güncellenir.

### 3.2 Araştırma yolu

- Router dataset JSONL, train/eval scriptleriyle işlenebilir.
- Product runtime stabilitesini bozmadan ayrı hat olarak çalışır.

---

## 4. Uygulanan Değişiklikler (Workstream Bazlı)

## 4.1 Config Resolve + Deterministic Precedence

### Yapılanlar

- `RuntimeConfig` alanları genişletildi:
  - `shadow_router_enabled`
  - `shadow_router_mode`
  - `fast_path_regret_window`
  - `fast_path_regret_threshold`
  - `env_prefix`
- `resolve_runtime_config(...)` eklendi.
- `IMPERAOS_*` env mapping eklendi.
- Kaynak izleme (`source_map`) eklendi.
- Config redaksiyon yardımcıları eklendi (`redact_config_payload`).
- CLI’ye `imperaos config resolve` komutu eklendi.

### Etkilenen dosyalar

- `imperaos/runtime/config.py`
- `imperaos/cli.py`
- `config/default.toml`
- `config/lite.toml`
- `config/balanced.toml`
- `config/research.toml`

### Sonuç

Aynı input ile aynı resolved config üretilir. Config davranışı gözlemlenebilir ve denetlenebilir hale geldi.

---

## 4.2 Planner Adversarial Hardening

### Yapılanlar

- Planner parse aşaması iki katmanlı hale getirildi:
  - JSON extraction
  - one-shot strict repair
- Unknown field reddi eklendi.
- Enum/type coercion güvenli hale getirildi.
- Reason code’lar genişletildi:
  - `PLANNER_REPAIR_APPLIED`
  - `PLANNER_SCHEMA_INVALID`

### Etkilenen dosyalar

- `imperaos/core/planner.py`
- `imperaos/schemas/reason_codes.py`

### Sonuç

Malformed/markdown/trailing/extra-key/invalid enum vakalarında planner deterministic fallback davranışı veriyor, sistem düşmüyor.

---

## 4.3 Expert Contract Validation ve Partial Failover

### Yapılanlar

- `ExpertStatus.PARTIAL` eklendi.
- Orchestrator içine expert payload validator registry eklendi.
- Expert payload invalid olduğunda:
  - status `partial`
  - error code `EXPERT_SCHEMA_INVALID`
  - kontrollü fallback
- Expert telemetry’ye schema validity sinyali eklendi.

### Etkilenen dosyalar

- `imperaos/schemas/models.py`
- `imperaos/core/orchestrator.py`
- `imperaos/schemas/reason_codes.py`

### Sonuç

Expert output bozuk olduğunda crash yerine degrade/fallback davranışı sağlanıyor.

---

## 4.4 Router Shadow Mode + Fast-Path Regret

### Yapılanlar

- Orchestrator’a `shadow_router` desteği eklendi.
- Active/shadow kararları telemetry’ye birlikte yazılıyor.
- Metrikler eklendi:
  - `active_router_choice`
  - `shadow_router_choice`
  - `router_shadow_agreement`
  - `fast_path_taken`
  - `fast_path_candidate_reason`
  - `fast_path_regret_flag`
  - `expert_needed_after_fast_path`
  - `followup_correction_rate`
- Session bazlı regret state takibi eklendi.

### Etkilenen dosyalar

- `imperaos/core/orchestrator.py`
- `imperaos/cli.py`
- `benchmarks/run_smoke.py`

### Sonuç

Canlı akışı bozmadan shadow karşılaştırma yapılabiliyor; fast-path kalite riskleri ölçülebilir hale geldi.

---

## 4.5 Benchmark Standardizasyonu + 120 Task Quality Gate

### Yapılanlar

- Benchmark suite ayrımı eklendi:
  - `smoke`
  - `quality`
- 120 görevlik quality set eklendi:
  - chat 30
  - code 30
  - research 20
  - plan 20
  - mixed 20
- `benchmark ablation` için `--suite` eklendi.
- Geniş metrik seti eklendi:
  - planner/router/expert/fast-path/shadow odaklı oranlar

### Etkilenen dosyalar

- `benchmarks/run_smoke.py`
- `benchmarks/run_ablation.py`
- `benchmarks/eval/report.py`
- `benchmarks/tasks/quality/quality_tasks.jsonl`
- `imperaos/cli.py`

### Sonuç

Smoke dışında kaliteyi ölçen, raporlanabilir ve tekrarlanabilir benchmark katmanı hazırlandı.

---

## 4.6 Energy Report Schema v0.2

### Yapılanlar

- `EnergyMeasurement` genişletildi:
  - `confidence`
  - `error_reason`
  - `notes`
- Energy payload alanları standardize edildi:
  - `measurement_mode`
  - `is_privileged`
  - `sampling_window_s`
  - `tool_name`
  - `confidence`
  - `error_reason`
  - `fallback_estimation_method`
  - `platform_info`
  - `notes`

### Etkilenen dosyalar

- `benchmarks/energy/macos_powermetrics.py`
- `benchmarks/run_ablation.py`

### Sonuç

Measured/estimated ayrımı açık, deterministic fail reason üretimi mevcut.

---

## 4.7 Machine-Readable Artifacts

### Yapılanlar

- Artifact writer modülü eklendi.
- Aşağıdaki dosyalar standartlaştırıldı:
  - `artifacts/status.json`
  - `artifacts/test_summary.json`
  - `artifacts/benchmark_summary.json`
  - `artifacts/router_shadow_summary.json`
  - `artifacts/research_summary.json`
- CLI komutları ilgili artifact’i güncelliyor.
- `.gitignore` içine `artifacts/` eklendi.

### Etkilenen dosyalar

- `imperaos/telemetry/artifacts_writer.py`
- `imperaos/cli.py`
- `.gitignore`

### Sonuç

CI/otomasyon/dashboards için makine-okunur sabit çıktı yüzeyi oluşturuldu.

---

## 4.8 Privacy & Safety Regression

### Yapılanlar

- Memory disabled modda store yoksa SQLite dokunmama davranışı eklendi.
- Privacy modda tracer persistence yok davranışı testlendi.
- Allowlist/prompt-injection-benzeri komut yolları testlendi.
- Fault injection testleri eklendi.

### Etkilenen dosyalar

- `imperaos/memory/manager.py`
- test paketleri (privacy/fault/security kapsamı)

### Sonuç

Varsayılan güvenlik ve gizlilik davranışı regresyona karşı test koruması altına alındı.

---

## 4.9 CLI Structured Output

### Yapılanlar

- Chat komutuna eklendi:
  - `--json`
  - `--json-stream`
  - `--stdio-json`
- Stream event tipi üretimi:
  - `token`, `status`, `router_decision`, `expert_start`, `expert_end`, `final`

### Etkilenen dosyalar

- `imperaos/cli.py`
- `imperaos/core/orchestrator.py`

### Sonuç

UI defer edilmesine rağmen IPC/desktop entegrasyonu için sağlam structured output yüzeyi hazırlandı.

---

## 4.10 Dokümantasyon + CI + Release Gate

### Yapılanlar

- README tamamen v0.2 durumuna güncellendi.
- Yeni dokümanlar eklendi:
  - `docs/ARCHITECTURE.md`
  - `docs/CONFIGURATION.md`
  - `docs/PRIVACY_MODEL.md`
  - `docs/RELEASE_GATE_v0.2.md`
  - `docs/UI_STRATEGY_v0.2.md`
- CI’ye `config resolve gate` ve `test_summary` üretimi eklendi.

### Etkilenen dosyalar

- `.github/workflows/ci.yml`
- `README.md`
- `docs/*`

### Sonuç

Release süreci daha tekrarlanabilir ve audit edilebilir hale getirildi.

---

## 5. Eklenen Testler (Yeni)

Yeni test dosyaları:

1. `tests/test_config_resolve.py`
2. `tests/test_planner_adversarial.py`
3. `tests/test_expert_schema_failover.py`
4. `tests/test_router_shadow_mode.py`
5. `tests/test_fast_path_regret.py`
6. `tests/test_benchmark_quality_suite.py`
7. `tests/test_energy_schema.py`
8. `tests/test_artifact_outputs.py`
9. `tests/test_privacy_regression.py`
10. `tests/test_fault_injection.py`
11. `tests/test_cli_structured_output.py`

Mevcut testler de v0.2 davranışına göre güncellendi (örn. `balanced` router varsayımı, orchestrator payload şekilleri).

---

## 6. Doğrulama Sonuçları (Bu Gün)

Bu rapor sürecinde çalıştırılan ana doğrulamalar:

1. `uv run ruff check .` -> geçti.
2. `uv run pytest -q` -> geçti (59 test).
3. `uv run imperaos doctor --profile balanced` -> geçti.
4. `uv run imperaos config resolve --profile balanced --json` -> geçti.
5. `uv run imperaos chat --profile lite --once "selam" --json-stream --stream` -> geçti.
6. `uv run imperaos benchmark ablation --mode all --profile balanced --suite quality --provider transformers` -> geçti (120 görev).
7. `uv run imperaos benchmark energy --profile balanced --energy-mode measured` -> deterministic permission-fail payload üretti (beklenen).
8. `uv run imperaos research train-router ...` + `eval-router ...` -> geçti.

---

## 7. Public API/Interface Güncel Durum

CLI’de aktif yeni/ek davranışlar:

- `imperaos config resolve --profile <x> [--provider ...] [--fallback-provider ...] [--json]`
- `imperaos chat --json`
- `imperaos chat --json-stream`
- `imperaos chat --stdio-json`
- `imperaos benchmark smoke --suite smoke|quality`
- `imperaos benchmark ablation --suite smoke|quality`

Schema/type güncellemeleri:

- `RuntimeConfig`: shadow/regret/env alanları
- `ExpertStatus`: `partial`
- `ReasonCode`: planner repair/schema invalid + expert schema invalid

---

## 8. Bilinen Sınırlar (v0.2)

1. `transformers` fallback süreklilik içindir, kalite eşdeğeri garantilemez.
2. Energy measured modu OS izinlerine bağlıdır.
3. Shadow agreement oranı görev dağılımına göre değişkenlik gösterebilir.
4. Fast-path regret şu an heuristik tabanlıdır; model tabanlı regret scorer yok.
5. UI thin-shell bilinçli olarak defer edilmiştir.

---

## 9. v0.3’e Hazır Zemin

Bu sürümün v0.3 için bıraktığı güçlü temel:

1. Structured chat event akışı UI için hazır.
2. Config/telemetry/artifact yüzeyi stabilize edildi.
3. Shadow-mode ile router defaultlaştırma kararları kanıtlanabilir hale geldi.
4. Quality benchmark standardı ve release gate zemini kuruldu.

---

## 10. Sonuç

v0.2 hedefi olan “özellik genişlemesinden çok güvenilirlik, ölçülebilirlik ve deterministik davranış” yaklaşımı kod seviyesinde uygulanmıştır.

Sistem artık:

- daha katı sözleşmelerle çalışıyor,
- hata senaryolarında daha kontrollü degrade oluyor,
- benchmark/energy/research çıktıları daha raporlanabilir,
- CLI katmanı UI’ya hazırlıklı ama UI’dan bağımsız stabil bir çekirdek sunuyor.
