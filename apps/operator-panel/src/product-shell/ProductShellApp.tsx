import { ProductRouter } from './router/ProductRouter';
import { ProductShellErrorBoundary } from './ProductShellErrorBoundary';

export function ProductShellApp() {
  return (
    <ProductShellErrorBoundary>
      <ProductRouter />
    </ProductShellErrorBoundary>
  );
}
