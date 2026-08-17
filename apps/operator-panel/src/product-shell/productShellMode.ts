export function resolveProductShellMode(environment: ImportMetaEnv): 'legacy' | 'v2' {
  return environment.VITE_IMPERAOS_PRODUCT_SHELL?.trim().toLowerCase() === 'legacy' ? 'legacy' : 'v2';
}
