import { LegacyOperatorApp } from './product-shell/legacy/LegacyOperatorApp';
import { ProductShellApp } from './product-shell/ProductShellApp';
import { resolveProductShellMode } from './product-shell/productShellMode';

export default function ProductShellBootstrap() {
  return resolveProductShellMode(import.meta.env) === 'v2' ? <ProductShellApp /> : <LegacyOperatorApp />;
}
