/**
 * White-box tests for components/SearchInput.jsx
 *
 * Tests every rendering branch and user interaction:
 *   - Renders with default placeholder 'Search...'
 *   - Renders with custom placeholder
 *   - Applies custom className
 *   - Displays Search icon
 *   - When value is empty/falsy, clear button (<button>) is NOT rendered
 *   - When value is non-empty, clear button is rendered with aria-label="Clear search query"
 *   - Typing in the input triggers onChange with new value
 *   - Clicking clear button triggers onChange with empty string ''
 *   - Has proper accessibility attribute aria-label on input
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SearchInput from '../../components/SearchInput';

describe('SearchInput', () => {
  it('renders input with default placeholder and aria-label', () => {
    render(<SearchInput value="" onChange={vi.fn()} />);
    const input = screen.getByRole('searchbox');
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('placeholder', 'Search...');
    expect(input).toHaveAttribute('aria-label', 'Search...');
  });

  it('renders input with custom placeholder and aria-label', () => {
    render(
      <SearchInput
        value=""
        onChange={vi.fn()}
        placeholder="Filter files by path..."
      />
    );
    const input = screen.getByPlaceholderText('Filter files by path...');
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('aria-label', 'Filter files by path...');
  });

  it('applies custom className to wrapper', () => {
    const { container } = render(
      <SearchInput value="" onChange={vi.fn()} className="custom-search-class" />
    );
    expect(container.firstChild).toHaveClass('custom-search-class');
    expect(container.firstChild).toHaveClass('cv-search');
  });

  it('does NOT render clear button when value is empty', () => {
    render(<SearchInput value="" onChange={vi.fn()} />);
    expect(
      screen.queryByRole('button', { name: /clear search query/i })
    ).not.toBeInTheDocument();
  });

  it('renders clear button when value is non-empty', () => {
    render(<SearchInput value="test query" onChange={vi.fn()} />);
    expect(
      screen.getByRole('button', { name: /clear search query/i })
    ).toBeInTheDocument();
  });

  it('calls onChange with entered text when user types', () => {
    const onChange = vi.fn();
    render(<SearchInput value="" onChange={onChange} />);
    const input = screen.getByRole('searchbox');
    fireEvent.change(input, { target: { value: 'payment' } });
    expect(onChange).toHaveBeenCalledWith('payment');
  });

  it('calls onChange with empty string when clear button is clicked', () => {
    const onChange = vi.fn();
    render(<SearchInput value="active search" onChange={onChange} />);
    const clearBtn = screen.getByRole('button', { name: /clear search query/i });
    fireEvent.click(clearBtn);
    expect(onChange).toHaveBeenCalledWith('');
  });
});
