import client from './client';

export const adminApi = {
  resetData: () => client.post('/api/admin/reset-data'),
  generateSampleData: () => client.post('/api/admin/generate-sample-data'),
};
