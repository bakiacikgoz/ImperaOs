import { Component, type PropsWithChildren, type ReactNode } from 'react';

type ProductShellErrorBoundaryState = {
  failed: boolean;
};

export class ProductShellErrorBoundary extends Component<PropsWithChildren, ProductShellErrorBoundaryState> {
  state: ProductShellErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ProductShellErrorBoundaryState {
    return { failed: true };
  }

  render(): ReactNode {
    if (this.state.failed) {
      return (
        <section role="alert" aria-labelledby="product-shell-error-title">
          <h1 id="product-shell-error-title">The product shell could not be displayed.</h1>
          <p>Reload the product shell to try again.</p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload product shell
          </button>
        </section>
      );
    }

    return this.props.children;
  }
}
