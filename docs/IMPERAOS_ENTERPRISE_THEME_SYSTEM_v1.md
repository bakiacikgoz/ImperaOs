# ImperaOS Enterprise Theme System v1

## Amaç

Bu doküman, ImperaOS / ImperaOS arayüz brief'ini üretime uygun bir tema sistemine çevirir. Hedef dil:

- macOS esintili ama birebir kopya olmayan
- premium enterprise control surface hissi veren
- nötr tabanlı, tipografi merkezli, düşük gürültülü
- light/dark parity koruyan
- uzun ömürlü ve ölçeklenebilir

Bu sistemin kod karşılığı ağırlıklı olarak:

- `apps/operator-panel/src/styles/tokens.css`
- `apps/operator-panel/src/styles/themes/light.css`
- `apps/operator-panel/src/styles/themes/dark.css`
- `apps/operator-panel/src/index.css`

## 1. Design Token Set

### 1.1 Core typography tokens

| Token | Değer | Kullanım |
| --- | --- | --- |
| `--font-sans` | SF Pro benzeri sistem stack | Tüm arayüz |
| `--font-mono` | SF Mono / IBM Plex Mono stack | Job ID, log, artifact |
| `--text-caption` | 12px | metadata, badge |
| `--text-label` | 13px | field label, sidebar section |
| `--text-body-sm` | 14px | secondary text |
| `--text-body` | 15px | varsayılan gövde |
| `--text-title-sm` | 17px | panel başlığı |
| `--text-title` | 20px | section başlığı |
| `--text-page` | 30px | sayfa başlığı |

### 1.2 Spacing scale

Tek spacing sistemi 4px tabanlı tutulur.

| Token | px |
| --- | --- |
| `--space-1` | 4 |
| `--space-2` | 8 |
| `--space-3` | 12 |
| `--space-4` | 16 |
| `--space-5` | 20 |
| `--space-6` | 24 |
| `--space-7` | 28 |
| `--space-8` | 32 |
| `--space-10` | 40 |
| `--space-12` | 48 |
| `--space-14` | 56 |
| `--space-16` | 64 |

### 1.3 Radius system

| Token | Değer | Kullanım |
| --- | --- | --- |
| `--radius-sm` | 10px | input, row, button |
| `--radius-md` | 14px | kart, popover |
| `--radius-lg` | 18px | ana yüzeyler |
| `--radius-xl` | 24px | shell konteynerleri |
| `--radius-pill` | 999px | badge, segmented control |

### 1.4 Shadow and elevation

Shadow sistemi derinlik üretir ama dikkat çekmez.

| Token | Amaç |
| --- | --- |
| `--shadow-xs` | input ve inset ayırımlar |
| `--shadow-sm` | standart panel |
| `--shadow-md` | sidebar / detail surface |
| `--shadow-focus` | odak halkası |

### 1.5 Motion

| Token | Değer |
| --- | --- |
| `--duration-fast` | 140ms |
| `--duration-normal` | 220ms |
| `--duration-slow` | 320ms |
| `--ease-standard` | cubic-bezier(0.2, 0.8, 0.2, 1) |
| `--ease-emphasis` | cubic-bezier(0.24, 0.94, 0.32, 1) |

## 2. Light / Dark Color Palette

### 2.1 Light theme

| Rol | Renk |
| --- | --- |
| App background | `#f3f4f6` |
| Canvas | `#f7f7f9` |
| Primary surface | `rgba(255,255,255,0.78)` |
| Elevated surface | `rgba(255,255,255,0.92)` |
| Sidebar surface | `rgba(246,247,249,0.82)` |
| Strong text | `#171a20` |
| Body text | `#2b313c` |
| Secondary text | `#67707f` |
| Muted text | `#8d94a1` |
| Hairline | `rgba(17,24,39,0.07)` |
| Default border | `rgba(17,24,39,0.11)` |
| Accent | `#4d6b98` |
| Accent strong | `#3e5a84` |

### 2.2 Dark theme

| Rol | Renk |
| --- | --- |
| App background | `#13161b` |
| Canvas | `#171b21` |
| Primary surface | `rgba(30,35,42,0.82)` |
| Elevated surface | `rgba(36,42,50,0.94)` |
| Sidebar surface | `rgba(23,27,33,0.8)` |
| Strong text | `#edf1f7` |
| Body text | `#d5dbe4` |
| Secondary text | `#a3adbc` |
| Muted text | `#7f8897` |
| Hairline | `rgba(255,255,255,0.06)` |
| Default border | `rgba(255,255,255,0.1)` |
| Accent | `#8ba2c8` |
| Accent strong | `#a5b7d6` |

### 2.3 State colors

Durum renkleri düşük doygunlukta tutulur.

| Durum | Light | Dark |
| --- | --- | --- |
| Success | `#5d8164` | `#8eb296` |
| Warning | `#9a7648` | `#c39b67` |
| Error | `#9a645d` | `#c48b84` |
| Info | Accent tabanlı | Accent tabanlı |

## 3. Semantic Surface Model

Arayüzde yüzey sayısı bilinçli şekilde sınırlanır:

1. `surface-canvas`
2. `surface-panel`
3. `surface-panel-strong`
4. `surface-sidebar`
5. `surface-field`
6. `surface-selected`

Kural:

- Tüm içerik kart içine kapatılmaz.
- Kart gerekiyorsa tonal ayrım kullanılır, kalın border kullanılmaz.
- Seçili durum renk blokuyla değil, accent destekli ince yüzey farkıyla çözülür.

## 4. Typography Scale

### Page hierarchy

| Seviye | Boyut | Weight | Kullanım |
| --- | --- | --- | --- |
| Page title | 30px | 650 | sayfa giriş alanı |
| Section title | 20px | 620 | panel grubu başlığı |
| Panel title | 17px | 610 | kart/pane başlığı |
| Body | 15px | 450 | normal içerik |
| Supporting | 14px | 450 | açıklama |
| Caption | 12-13px | 560 | label, metadata |

### Uygulama prensipleri

- Metin hiyerarşisi büyüklük farkıyla değil, ağırlık ve ton farkıyla kurulmalı.
- Body metin ve numerik satırlar rahat okunmalı.
- Monospace metinler küçük ama hava alır olmalı.

## 5. Spacing / Radius / Shadow System

### Layout

- Uygulama dış boşluğu: `32px`
- Sidebar iç boşluğu: `24px`
- Ana içerik blok aralığı: `24px`
- Page header alt boşluğu: `24px`
- Form satır aralığı: `16px`
- Panel iç boşluğu: `20px`

### Density guidance

- List row minimum yükseklik: 52-60px
- Toolbar eleman aralığı: 8-12px
- Sidebar item iç boşluğu: 12-14px
- Table row separator: hairline

## 6. Component Spec

### Sidebar

- Ayrı bir premium surface gibi davranmalı.
- Aktif öğe dolu mavi blok olmamalı.
- İkon zorunlu değil; varsa tek ton ve çok sınırlı.
- Aktif durumda:
  - ince accent border
  - hafif tonal dolgu
  - başlık rengi yükselir
  - supporting text görünür kalır

### Topbar

- Sayfayı taşıyan ana başlık burada değil; topbar operasyonel utility katmanı olmalı.
- Sol tarafta durum pill'leri, sağ tarafta düşük yoğunluklu aksiyonlar bulunmalı.
- Alt separator çok hafif olmalı.

### Page Header

- Eyebrow + title + supporting text.
- Sağ tarafta kısa context kartları olabilir.
- Başlık alanı her sayfada aynı iskeleti korumalı.

### Buttons

- Primary: accent tabanlı tonal dolgu, beyaz değil hafif off-white yazı
- Secondary: nötr yüzey + ince border
- Ghost: yüzeysiz, hover'da hafif tonal zemin
- Danger: kırmızı dolgu yerine düşük doygunluklu uyarı yüzeyi

### Inputs

- Field yüzeyi ton farkıyla seçilmeli.
- Focus ring tek belirgin accent kullanımı olmalı.
- Placeholder metni muted text seviyesinde kalmalı.

### Panels

- Varsayılan radius: `--radius-lg`
- Border: hairline/default arası
- Shadow: `--shadow-sm`
- İç boşluk: `20px`

### Lists / Tables

- Zebra çok hafif veya hiç yok
- Row hover: nötr tonal yükselme
- Selected row: accent destekli tonal yüzey
- Metadata satırı muted text

### Toast / Badge / Status

- Kapsül form kullanılabilir ama renk yoğunluğu düşük tutulmalı.
- Renk tek ayırt edici unsur olmamalı; label ve ton farkı da olmalı.

## 7. Örnek Sayfa Kompozisyonları

### 7.1 Dashboard

- Utility topbar
- Page header
- 2 veya 3 kısa metrik kartı
- Bir adet operating posture paneli
- Bir adet capability / diagnostics yüzeyi

Hedef his: "kontrol altında, sakin, denetlenebilir"

### 7.2 Approvals workspace

- Sol: approval queue
- Sağ: selected approval detail
- Üstte düşük yoğunluklu action row
- Kritik aksiyonlar birbirine çok yaklaşmamalı

Hedef his: "onay yüzeyi", "işlem terminali" değil

### 7.3 Runs workspace

- Sol: run list
- Sağ: tabbed detail
- Timeline görünümü liste değil olay akışı gibi davranmalı
- Artifact görünümü mono ama yüksek okunabilirlikte kalmalı

### 7.4 Settings

- Runtime / Interface / Safety olarak gruplandırılmış
- Form alanları geniş ama sıkışık değil
- Toggle ve segmented controls sistem tercihi gibi görünmeli

## 8. Kullanım Kuralları

- Accent rengi sadece seçim, odak, primary ve kritik context için kullan.
- Arayüz hiyerarşisini renk yerine spacing ve tipografiyle kur.
- Büyük dekoratif gradient kullanma.
- Blur varsa çok hafif ve yalnızca üst düzey yüzeylerde kullan.
- Light ve dark mode yalnızca ters renk değil, farklı yüzey hiyerarşisi taşımalı.

## 9. Uygulama Sonucu

Bu sistem, ImperaOS'u tipik bir SaaS dashboard görünümünden uzaklaştırıp:

- kurumsal sistem yazılımı
- güvenlik odaklı kontrol paneli
- premium masaüstü yardımcı uygulaması

çizgisine taşımayı hedefler.
