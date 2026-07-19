import { z } from 'zod';

// The desktop CSP intentionally omits unsafe-eval. Zod's default object-schema
// fast path probes/uses Function(), so configure the shared global instance
// before any application contract modules are evaluated.
z.config({ jitless: true });
