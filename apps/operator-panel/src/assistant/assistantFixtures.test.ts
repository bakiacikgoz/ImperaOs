import { describe, expect, it } from 'vitest';

import { previewAssistantEvents } from './assistantFixtures';

describe('assistant preview fixtures', () => {
  it('keeps typed artifact events aligned with the v3 contract', () => {
    const event = previewAssistantEvents().find((candidate) => candidate.event === 'artifact_committed');

    expect(event).toMatchObject({
      contractVersion: '3.0',
      eventId: expect.any(String),
      traceId: expect.any(String),
      dataClass: 'internal',
      data: {
        artifactId: 'artifact-preview-document',
        revisionId: 'revision-1',
        kind: 'document',
      },
    });
    expect(event?.data).not.toHaveProperty('artifact_id');
    expect(event?.data).not.toHaveProperty('revision_id');
  });
});
