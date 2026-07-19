import { screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { renderOperatorPanel } from '../../test/render';
import { ArtifactExportDialog } from './ArtifactExportDialog';

describe('ArtifactExportDialog', () => {
  it('confirms a format without collecting or displaying an export path', async () => {
    const onConfirm = vi.fn();
    const { user } = renderOperatorPanel(
      <ArtifactExportDialog
        artifactTitle="Launch plan"
        formats={[{ value: 'markdown', label: 'Markdown' }, { value: 'html', label: 'HTML' }]}
        suggestedFilename="launch-plan.md"
        revisionNumber={7}
        dataClass="confidential"
        policyState="allowed"
        estimatedSizeBytes={2048}
        securityWarning="Exported files leave workspace governance."
        onCancel={vi.fn()}
        onConfirm={onConfirm}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Export Launch plan' })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/path/i)).not.toBeInTheDocument();
    expect(screen.getByText('launch-plan.md')).toBeInTheDocument();
    expect(screen.getByText('Revision 7')).toBeInTheDocument();
    expect(screen.getByText('confidential')).toBeInTheDocument();
    expect(screen.getByText('allowed')).toBeInTheDocument();
    expect(screen.getByText('2 KB')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('leave workspace governance');
    await user.selectOptions(screen.getByLabelText('Export format'), 'html');
    await user.click(screen.getByRole('button', { name: 'Choose destination and export' }));

    expect(onConfirm).toHaveBeenCalledWith('html');
  });

  it('keeps focus in the dialog and returns it to the invoking control on cancel', async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return <>
        <button type="button" onClick={() => setOpen(true)}>Open export</button>
        {open ? <ArtifactExportDialog
          artifactTitle="Launch plan"
          formats={[{ value: 'markdown', label: 'Markdown' }]}
          onCancel={() => setOpen(false)}
          onConfirm={vi.fn()}
        /> : null}
      </>;
    }
    const { user } = renderOperatorPanel(
      <Harness />,
    );

    await user.click(screen.getByRole('button', { name: 'Open export' }));
    const cancel = screen.getByRole('button', { name: 'Cancel export' });
    expect(screen.getByRole('button', { name: 'Choose destination and export' })).toHaveFocus();
    await user.click(cancel);
    expect(screen.getByRole('button', { name: 'Open export' })).toHaveFocus();
  });
});
