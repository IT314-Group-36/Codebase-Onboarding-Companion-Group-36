/**
 * White-box tests for components/ConfirmDialog.jsx
 *
 * Tests every rendering branch and interaction path:
 *   - open={false}: renders nothing
 *   - open={true}: renders overlay, dialog with title/message, two buttons
 *   - variant="danger": shows AlertTriangle icon
 *   - variant other than "danger": shows AlertCircle icon
 *   - onConfirm callback fires when confirm button is clicked
 *   - onCancel callback fires when cancel button is clicked
 *   - onCancel fires when overlay is clicked
 *   - Escape key calls onCancel (when open and not loading)
 *   - Escape key does NOT call onCancel when loading
 *   - loading disables the cancel button
 *   - Custom confirmLabel and cancelLabel are rendered
 *   - ARIA attributes: role="alertdialog", aria-modal, aria-labelledby, aria-describedby
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ConfirmDialog from '../../components/ConfirmDialog';

const baseProps = {
  open: true,
  title: 'Delete Item?',
  message: 'This action cannot be undone.',
  onConfirm: vi.fn(),
  onCancel: vi.fn(),
};

describe('ConfirmDialog', () => {
  // ---- open={false}: renders nothing ----

  it('renders nothing when open is false', () => {
    const { container } = render(<ConfirmDialog {...baseProps} open={false} />);
    expect(container.innerHTML).toBe('');
  });

  // ---- open={true}: renders the dialog ----

  it('renders the dialog with title and message when open', () => {
    render(<ConfirmDialog {...baseProps} />);
    expect(screen.getByText('Delete Item?')).toBeInTheDocument();
    expect(screen.getByText('This action cannot be undone.')).toBeInTheDocument();
  });

  it('renders two buttons (cancel and confirm)', () => {
    render(<ConfirmDialog {...baseProps} />);
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(2);
  });

  // ---- ARIA attributes ----

  it('has role="alertdialog" with aria-modal', () => {
    render(<ConfirmDialog {...baseProps} />);
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'dialog-title');
    expect(dialog).toHaveAttribute('aria-describedby', 'dialog-desc');
  });

  // ---- Variant icon branching ----

  it('shows AlertTriangle icon for variant="danger"', () => {
    const { container } = render(<ConfirmDialog {...baseProps} variant="danger" />);
    expect(container.querySelector('.cv-dialog__icon--danger')).toBeInTheDocument();
  });

  it('shows icon element for non-danger variant (e.g. "warning")', () => {
    const { container } = render(<ConfirmDialog {...baseProps} variant="warning" />);
    expect(container.querySelector('.cv-dialog__icon--warning')).toBeInTheDocument();
  });

  // ---- Custom labels ----

  it('renders custom confirmLabel and cancelLabel', () => {
    render(
      <ConfirmDialog {...baseProps} confirmLabel="Yes, Delete" cancelLabel="No, Keep" />
    );
    expect(screen.getByText('Yes, Delete')).toBeInTheDocument();
    expect(screen.getByText('No, Keep')).toBeInTheDocument();
  });

  it('uses default labels when not provided', () => {
    render(<ConfirmDialog {...baseProps} />);
    expect(screen.getByText('Confirm')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  // ---- Confirm callback ----

  it('calls onConfirm when confirm button is clicked', () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog {...baseProps} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByText('Confirm'));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  // ---- Cancel callback ----

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...baseProps} onCancel={onCancel} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('calls onCancel when overlay is clicked', () => {
    const onCancel = vi.fn();
    const { container } = render(<ConfirmDialog {...baseProps} onCancel={onCancel} />);
    const overlay = container.querySelector('.cv-dialog-overlay');
    fireEvent.click(overlay);
    expect(onCancel).toHaveBeenCalled();
  });

  it('does NOT call onCancel when dialog body is clicked (stopPropagation)', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...baseProps} onCancel={onCancel} />);
    const dialog = screen.getByRole('alertdialog');
    fireEvent.click(dialog);
    expect(onCancel).not.toHaveBeenCalled();
  });

  // ---- Escape key ----

  it('calls onCancel when Escape is pressed and not loading', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...baseProps} onCancel={onCancel} loading={false} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('does NOT call onCancel on Escape when loading', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...baseProps} onCancel={onCancel} loading={true} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).not.toHaveBeenCalled();
  });

  // ---- Loading state ----

  it('disables cancel button when loading', () => {
    render(<ConfirmDialog {...baseProps} loading={true} />);
    const cancelBtn = screen.getByText('Cancel').closest('button');
    expect(cancelBtn).toBeDisabled();
  });
});
