
import { Search, X } from 'lucide-react';
import './SearchInput.css';

/**
 * Reusable search input component.
 *
 * @param {Object} props
 * @param {string} props.value
 * @param {Function} props.onChange
 * @param {string} [props.placeholder='Search...']
 * @param {string} [props.className='']
 */
export default function SearchInput({
  value,
  onChange,
  placeholder = 'Search...',
  className = '',
}) {
  return (
    <div className={`cv-search ${className}`}>
      <Search size={16} className="cv-search__icon" aria-hidden="true" />
      <input
        type="search"
        className="cv-search__input"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={placeholder}
      />
      {value && (
        <button
          type="button"
          className="cv-search__clear"
          onClick={() => onChange('')}
          aria-label="Clear search query"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
