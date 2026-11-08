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
} from './api';

export const explorerService = {
  getFileTree,
  getFileDetails,
  getFileContent,
  searchSymbols,
  getDependencyGraph,
};

export {
  getFileTree,
  getFileDetails,
  getFileContent,
  searchSymbols,
  getDependencyGraph,
};
