/**
 * White-box tests for components/StatusBadge.jsx
 *
 * Tests every rendering branch:
 *   - Each known status renders correct CSS class and label text
 *   - "analyzing" status renders pulse animation span
 *   - All other statuses render dot span (not pulse)
 *   - Unknown/undefined status falls back to default and shows raw value
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusBadge from '../../components/StatusBadge';

describe('StatusBadge', () => {
  // ---- Known statuses: correct class + label ----

  it('renders "Connected" label with connected class', () => {
    const { container } = render(<StatusBadge status="connected" />);
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(container.querySelector('.cv-badge--connected')).toBeInTheDocument();
  });

  it('renders "Analyzing" label with analyzing class', () => {
    const { container } = render(<StatusBadge status="analyzing" />);
    expect(screen.getByText('Analyzing')).toBeInTheDocument();
    expect(container.querySelector('.cv-badge--analyzing')).toBeInTheDocument();
  });

  it('renders "Analyzed" label with analyzed class', () => {
    const { container } = render(<StatusBadge status="analyzed" />);
    expect(screen.getByText('Analyzed')).toBeInTheDocument();
    expect(container.querySelector('.cv-badge--analyzed')).toBeInTheDocument();
  });

  it('renders "Error" label with error class', () => {
    const { container } = render(<StatusBadge status="error" />);
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(container.querySelector('.cv-badge--error')).toBeInTheDocument();
  });

  it('renders "Pending" label with pending class', () => {
    const { container } = render(<StatusBadge status="pending" />);
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(container.querySelector('.cv-badge--pending')).toBeInTheDocument();
  });

  // ---- Pulse vs Dot branching ----

  it('shows pulse animation for "analyzing" status', () => {
    const { container } = render(<StatusBadge status="analyzing" />);
    expect(container.querySelector('.cv-badge__pulse')).toBeInTheDocument();
    expect(container.querySelector('.cv-badge__dot')).not.toBeInTheDocument();
  });

  it('shows dot (not pulse) for "connected" status', () => {
    const { container } = render(<StatusBadge status="connected" />);
    expect(container.querySelector('.cv-badge__dot')).toBeInTheDocument();
    expect(container.querySelector('.cv-badge__pulse')).not.toBeInTheDocument();
  });

  it('shows dot (not pulse) for "error" status', () => {
    const { container } = render(<StatusBadge status="error" />);
    expect(container.querySelector('.cv-badge__dot')).toBeInTheDocument();
    expect(container.querySelector('.cv-badge__pulse')).not.toBeInTheDocument();
  });

  // ---- Default / unknown status ----

  it('defaults to "connected" class when no status prop is passed', () => {
    const { container } = render(<StatusBadge />);
    expect(container.querySelector('.cv-badge--connected')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('renders raw status string for unknown statuses', () => {
    render(<StatusBadge status="custom_status" />);
    // The fallback `statusLabels[status] || status` should render the raw value
    expect(screen.getByText('custom_status')).toBeInTheDocument();
  });
});
