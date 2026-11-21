/**
 * White-box tests for components/Button.jsx
 *
 * Tests every rendering branch:
 *   - variant classes (primary, secondary, ghost, danger, outline)
 *   - size classes (sm, md, lg)
 *   - loading state: disabled + spinner shown, icon hidden
 *   - non-loading with icon: icon span rendered
 *   - no icon, no loading: neither spinner nor icon span
 *   - children rendered inside .cv-btn__text
 *   - disabled prop disables the button
 *   - onClick fires when not disabled/loading
 *   - custom className is appended
 *   - type defaults to "button"
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Button from '../../components/Button';

describe('Button', () => {
  // ---- Variant CSS classes ----

  it('applies primary variant class by default', () => {
    render(<Button>Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('cv-btn--primary');
  });

  it('applies secondary variant class', () => {
    render(<Button variant="secondary">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('cv-btn--secondary');
  });

  it('applies ghost variant class', () => {
    render(<Button variant="ghost">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('cv-btn--ghost');
  });

  it('applies danger variant class', () => {
    render(<Button variant="danger">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('cv-btn--danger');
  });

  it('applies outline variant class', () => {
    render(<Button variant="outline">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('cv-btn--outline');
  });

  // ---- Size classes ----

  it('applies md size class by default', () => {
    render(<Button>Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('cv-btn--md');
  });

  it('applies sm size class', () => {
    render(<Button size="sm">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('cv-btn--sm');
  });

  it('applies lg size class', () => {
    render(<Button size="lg">Click</Button>);
    expect(screen.getByRole('button')).toHaveClass('cv-btn--lg');
  });

  // ---- Loading state ----

  it('shows spinner and hides icon when loading', () => {
    const { container } = render(
      <Button loading icon={<span data-testid="icon">★</span>}>Save</Button>
    );
    // Spinner should be rendered
    expect(container.querySelector('.cv-btn__spinner')).toBeInTheDocument();
    // Icon should NOT be rendered
    expect(screen.queryByTestId('icon')).not.toBeInTheDocument();
    // Loading class applied
    expect(screen.getByRole('button')).toHaveClass('cv-btn--loading');
  });

  it('disables the button when loading', () => {
    render(<Button loading>Save</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  // ---- Icon rendering ----

  it('renders icon span when icon is provided and not loading', () => {
    const { container } = render(
      <Button icon={<span data-testid="icon">★</span>}>Action</Button>
    );
    expect(screen.getByTestId('icon')).toBeInTheDocument();
    expect(container.querySelector('.cv-btn__icon')).toBeInTheDocument();
    expect(container.querySelector('.cv-btn__spinner')).not.toBeInTheDocument();
  });

  it('does not render icon span when no icon is provided', () => {
    const { container } = render(<Button>Plain</Button>);
    expect(container.querySelector('.cv-btn__icon')).not.toBeInTheDocument();
  });

  // ---- Children ----

  it('renders children inside .cv-btn__text span', () => {
    const { container } = render(<Button>Hello World</Button>);
    const textSpan = container.querySelector('.cv-btn__text');
    expect(textSpan).toBeInTheDocument();
    expect(textSpan.textContent).toBe('Hello World');
  });

  it('does not render .cv-btn__text span when no children', () => {
    const { container } = render(<Button />);
    expect(container.querySelector('.cv-btn__text')).not.toBeInTheDocument();
  });

  // ---- Disabled ----

  it('disables button via disabled prop', () => {
    render(<Button disabled>No Click</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('is disabled when BOTH disabled and loading are true', () => {
    render(<Button disabled loading>Wait</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  // ---- Click ----

  it('calls onClick when clicked', () => {
    const handler = vi.fn();
    render(<Button onClick={handler}>Click Me</Button>);
    fireEvent.click(screen.getByRole('button'));
    expect(handler).toHaveBeenCalledOnce();
  });

  it('does not call onClick when disabled', () => {
    const handler = vi.fn();
    render(<Button disabled onClick={handler}>Nope</Button>);
    fireEvent.click(screen.getByRole('button'));
    expect(handler).not.toHaveBeenCalled();
  });

  // ---- Custom className ----

  it('appends custom className', () => {
    render(<Button className="my-extra">Test</Button>);
    expect(screen.getByRole('button')).toHaveClass('my-extra');
    expect(screen.getByRole('button')).toHaveClass('cv-btn');
  });

  // ---- Type ----

  it('defaults type to "button"', () => {
    render(<Button>Test</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
  });

  it('allows overriding type to "submit"', () => {
    render(<Button type="submit">Submit</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'submit');
  });
});
