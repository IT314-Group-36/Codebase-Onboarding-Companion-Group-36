// One list of page names, used by the sidebar, the top bar and the "connect a repository first" page,
// so the same page is never called two different things.
export const NAV = {
  home: 'Home',
  connect: 'Connect a repo',
  overview: 'Overview',
  explore: 'Explore code',
  deps: 'Dependency Map',
  ask: 'Ask a question',
  tasks: 'Tasks',
  history: 'Git History',
  settings: 'Settings',
};

// URL section -> page name (every section also has a version without a repository id)
export const SECTION_LABEL = {
  repository: NAV.overview,
  explorer: NAV.explore,
  dependencies: NAV.deps,
  qa: NAV.ask,
  onboarding: NAV.tasks,
  history: NAV.history,
};
