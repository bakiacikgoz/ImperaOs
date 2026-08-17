import { Workflow } from 'lucide-react';

export function CollectionPage({ title, body }: { title: string; body: string }) {
  return (
    <main className="collection-page">
      <header>
        <span className="collection-icon"><Workflow size={21} /></span>
        <p>OTOMASYONLAR</p>
        <h1>{title}</h1>
        <span>{body}</span>
      </header>
      <section className="collection-list">
        <p className="collection-empty">This view will be populated only from existing governed services; no demo records are rendered.</p>
      </section>
    </main>
  );
}
