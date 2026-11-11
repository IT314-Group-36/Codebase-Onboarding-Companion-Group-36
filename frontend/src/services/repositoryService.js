/**
 * Repository Service
 * Encapsulates repository lifecycle, registration, specs, and reindexing.
 */
import {
  getRepositories,
  getRepositoryById,
  connectRepository,
  reindexRepository,
  disconnectRepository,
  checkHealth,
} from './api';

export const repositoryService = {
  getRepositories,
  getRepositoryById,
  connectRepository,
  reindexRepository,
  disconnectRepository,
  checkHealth,
};

export {
  getRepositories,
  getRepositoryById,
  connectRepository,
  reindexRepository,
  disconnectRepository,
  checkHealth,
};
