import {
  ArrowLeft,
  CircleUserRound,
  Moon,
  Search,
  SlidersHorizontal,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';

import { loadSettings, resolveThemeMode, saveSettings, type PanelSettings } from '../../settings';
import { useProductShellStore } from '../state/productShellStore';

const settingGroups = [
  ['Hesap', 'Genel', 'Görünüm', 'Asistan'],
  ['Sistem', 'AI Sağlayıcıları', 'Güvenlik', 'Kısayollar'],
] as const;
const advancedSections = new Set(['AI Sağlayıcıları', 'Güvenlik']);

export function SettingsShell() {
  const [settings, setSettings] = useState<PanelSettings>(() => loadSettings());
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');
  const [activeSection, setActiveSection] = useState('Genel');
  const setTheme = useProductShellStore((state) => state.setTheme);
  const normalizedQuery = query.toLocaleLowerCase('tr-TR');
  const update = <Key extends keyof PanelSettings>(key: Key, value: PanelSettings[Key]) => {
    setSettings((current) => ({ ...current, [key]: value }));
    setStatus('');
  };
  const save = () => {
    saveSettings(settings);
    setTheme(resolveThemeMode(settings.theme));
    setStatus('Settings saved to the governed operator profile.');
  };

  return (
    <div className="settings-shell">
      <aside className="settings-sidebar">
        <a className="back-to-app" href="#/"><ArrowLeft size={16} /> Uygulamaya dön</a>
        <label className="settings-search">
          <Search size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ayarlarda ara" aria-label="Ayarlarda ara" />
          <kbd>Filtre</kbd>
        </label>
        <div className="settings-links">
          {settingGroups.map(([group, ...items]) => {
            const visibleItems = items.filter((item) => item.toLocaleLowerCase('tr-TR').includes(normalizedQuery));
            return visibleItems.length ? (
              <section key={group}>
                <span>{group}</span>
                {visibleItems.map((item) => (
                  advancedSections.has(item)
                    ? <a key={item} href="#/system/settings" title={`${item} gelişmiş sistem ayarlarında yönetilir.`}>{item}</a>
                    : <button type="button" key={item} className={activeSection === item ? 'is-active' : ''} onClick={() => setActiveSection(item)}>
                        {item}
                      </button>
                ))}
              </section>
            ) : null;
          })}
        </div>
        <div className="settings-account">
          <span className="avatar">{settings.operatorId.trim().slice(0, 2).toUpperCase() || 'IO'}</span>
          <div><strong>{settings.operatorId.trim() || 'ImperaOS operator'}</strong><small>Governed workspace</small></div>
        </div>
      </aside>
      <main className="settings-content">
        <form className="settings-page" onSubmit={(event) => { event.preventDefault(); save(); }}>
          <header>
            <span className="settings-page-icon">{activeSection === 'Genel' ? <CircleUserRound size={20} /> : activeSection === 'Görünüm' ? <Moon size={20} /> : <SlidersHorizontal size={20} />}</span>
            <div>
              <h1>{activeSection === 'Genel' ? 'Operatör ayarları' : activeSection}</h1>
              <p>ImperaOS çalışma alanı ve governed operator tercihlerini yönetin.</p>
            </div>
          </header>
          {activeSection === 'Genel' ? <>
              <SettingsBlock title="Operatör profili">
                <SettingsRow title="Operatör kimliği" description="Onay kararlarında kullanılan doğrulanmış kimlik.">
                  <input aria-label="Operator identity" value={settings.operatorId} onChange={(event) => update('operatorId', event.target.value)} />
                </SettingsRow>
              </SettingsBlock>
              <SettingsBlock title="Çalışma alanı">
                <SettingsRow title="Dil" description="Arayüz ve asistan yanıtları için tercih edilen dil.">
                  <select aria-label="Language" value={settings.locale} onChange={(event) => update('locale', event.target.value as PanelSettings['locale'])}>
                    <option value="auto">Automatic</option><option value="en">English</option><option value="tr">Türkçe</option>
                  </select>
                </SettingsRow>
              </SettingsBlock>
              <SettingsBlock title="Gelişmiş">
                <SettingsRow title="Legacy sistem ayarları" description="Gelişmiş sistem yapılandırmasına izole legacy rotadan erişin.">
                  <a href="#/system/settings">Open advanced legacy settings</a>
                </SettingsRow>
              </SettingsBlock>
            </> : null}
          {activeSection === 'Görünüm' ? <SettingsBlock title="Görünüm">
              <SettingsRow title="Tema" description="UI Lab açık veya koyu renk modu.">
                <select aria-label="Theme" value={settings.theme} onChange={(event) => update('theme', event.target.value as PanelSettings['theme'])}>
                  <option value="system">System</option><option value="dark">Dark</option><option value="light">Light</option>
                </select>
              </SettingsRow>
            </SettingsBlock> : null}
          {activeSection === 'Asistan' ? <SettingsBlock title="Asistan runtime">
              <SettingsRow title="Asistan profili" description="Yeni görevlerde kullanılan varsayılan runtime profili.">
                <input aria-label="Assistant profile" value={settings.profile} onChange={(event) => update('profile', event.target.value)} />
              </SettingsRow>
              <SettingsRow title="Birincil sağlayıcı" description="Kayıtlı veya yerel asistan sağlayıcı kimliği.">
                <input aria-label="Assistant provider" value={settings.assistantProvider} onChange={(event) => update('assistantProvider', event.target.value)} />
              </SettingsRow>
              <SettingsRow title="Model" description="Seçilen sağlayıcı için model kimliği.">
                <input aria-label="Assistant model" value={settings.assistantModel} onChange={(event) => update('assistantModel', event.target.value)} />
              </SettingsRow>
              <SettingsRow title="Onay profili" description="Yürütme politikası genişletilmeden uygulanacak onay davranışı.">
                <select aria-label="Default approval profile" value={settings.approvalProfile} onChange={(event) => update('approvalProfile', event.target.value as PanelSettings['approvalProfile'])}>
                  <option value="always_ask">Her zaman onay iste</option>
                  <option value="risk_based">Riske göre onay iste</option>
                  <option value="policy_automatic">Politika içinde otomatik</option>
                </select>
              </SettingsRow>
            </SettingsBlock> : null}
          {activeSection === 'Kısayollar' ? <SettingsBlock title="Kısayollar">
              <SettingsRow title="Global arama" description="Product Shell genelinde proje, görev, artifact ve onay aramasını açar.">
                <kbd>⌘/Ctrl K</kbd>
              </SettingsRow>
              <SettingsRow title="Ayar arama" description="Ayar filtresi yalnızca yukarıdaki arama alanına tıklanarak kullanılır.">
                <kbd>Doğrudan filtre</kbd>
              </SettingsRow>
            </SettingsBlock> : null}
          <div className="settings-actions">
            <button type="submit">Save settings</button>
            {status ? <p role="status">{status}</p> : null}
          </div>
        </form>
      </main>
    </div>
  );
}

function SettingsBlock({ title, children }: { title: string; children: ReactNode }) {
  return <section className="settings-block"><h2>{title}</h2><div>{children}</div></section>;
}

function SettingsRow({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <div className="settings-row"><div><strong>{title}</strong><p>{description}</p></div>{children}</div>;
}
