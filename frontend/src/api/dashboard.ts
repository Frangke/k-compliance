import client from './client';

export const dashboardApi = {
  overview: () => client.get('/api/dashboard/overview'),
  complianceTrend: () => client.get('/api/dashboard/compliance-trend'),
  evidenceStatus: () => client.get('/api/dashboard/evidence-status'),
  pipaDeadlines: () => client.get('/api/dashboard/pipa-deadlines'),
  prowlerSummary: () => client.get('/api/dashboard/prowler-summary'),
  configSummary: () => client.get('/api/dashboard/config-summary'),
  automatedCoverage: () => client.get('/api/dashboard/automated-coverage'),
  myAssignments: () => client.get('/api/dashboard/my-assignments'),
};
