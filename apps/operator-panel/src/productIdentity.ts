import canonicalProductIdentity from "../../../branding/identity.json" with { type: "json" };

export type ProductIdentity = Readonly<{
  displayName: string;
  slug: string;
  pythonDistribution: string;
  pythonPackage: string;
  cliName: string;
  envPrefix: string;
  stateRoot: string;
  operatorProductName: string;
  operatorBundleId: string;
  runtimeResourceDir: string;
  domain: string;
  repository: string;
  metricPrefix: string;
}>;

export const PRODUCT_IDENTITY: ProductIdentity = Object.freeze(canonicalProductIdentity);
