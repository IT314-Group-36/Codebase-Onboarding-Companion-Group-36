/**
 * Explorer Service
 * Encapsulates file tree navigation, individual file insights, and symbol retrieval.
 */
import {
  getFileTree,
  getFileDetails,
  getFileContent,
  searchSymbols,
  getDependencyGraph,
  getFileExplanation,
  getSymbolExplanation,
} from './api';

export const explorerService = {
  getFileTree,
  getFileDetails,
  getFileContent,
  searchSymbols,
  getDependencyGraph,
  getFileExplanation,
  getSymbolExplanation,
};

export {
  getFileTree,
  getFileDetails,
  getFileContent,
  searchSymbols,
  getDependencyGraph,
  getFileExplanation,
  getSymbolExplanation,
};
