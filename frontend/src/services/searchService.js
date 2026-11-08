/**
 * Search Service
 * Encapsulates hybrid vector + keyword search over repository code chunks.
 */
import { searchCode, searchSymbols } from './api';

export const searchService = {
  searchCode,
  searchSymbols,
};

export {
  searchCode,
  searchSymbols,
};
