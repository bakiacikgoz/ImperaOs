import { describe, expect, it } from 'vitest';

import { routeGroups, routes } from './routeRegistry';

describe('routeRegistry', () => {
  it('keeps visible navigation routes unique and free of aliases', () => {
    const routeIds = routes.map((route) => route.routeId);
    const labels = routes.map((route) => route.label);
    const ids = routes.map((route) => route.id);

    expect(new Set(routeIds).size).toBe(routeIds.length);
    expect(new Set(labels).size).toBe(labels.length);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('declares every productization navigation group with route headings', () => {
    expect(routeGroups.length).toBeGreaterThan(0);
    for (const group of routeGroups) {
      expect(group.title).toBeTruthy();
      expect(group.routes.length).toBeGreaterThan(0);
      for (const route of group.routes) {
        expect(route.heading).toBeTruthy();
        expect(route.label).toBeTruthy();
        expect(route.routeId).toBeTruthy();
      }
    }
  });

  it('keeps the product journey ahead of administration and internal release tooling', () => {
    expect(routeGroups.map((group) => group.title)).toEqual([
      'WORKSPACE', 'RUNS', 'APPROVALS', 'EVIDENCE', 'ADMINISTRATION', 'ADVANCED / INTERNAL',
    ]);
    expect(routeGroups[0].routes[0].routeId).toBe('workspace');
    expect(routeGroups.at(-1)?.routes.map((route) => route.routeId)).toContain('rc-release-decision');
  });

  it('exposes enterprise workspace onboarding routes', () => {
    const routeIds = routes.map((route) => route.routeId);

    expect(routeIds).toEqual(
      expect.arrayContaining([
        'enterprise-workspace',
        'enterprise-users',
        'enterprise-roles',
        'enterprise-enrollment',
        'enterprise-fleet',
        'enterprise-identity',
      ]),
    );
  });
});
